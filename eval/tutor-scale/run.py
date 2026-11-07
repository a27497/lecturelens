"""Additive dataset driver reusing the frozen P8 runtime, authority, channel and reviewer."""

import argparse
import json
import os
import subprocess
import time
from collections import Counter
from pathlib import Path

import httpx
from dataset import HERE, ROOT, digest, load, write
from lecturelens_real_eval.runner import SnapshotAuthority
from lecturelens_real_eval.tutor.contracts import ABSTENTION, Command
from lecturelens_real_eval.tutor.runtime import MockTutor, TutorRuntime
from lecturelens_real_eval.tutor.store import TutorStore
from lecturelens_real_eval.tutor_channel import (
    Channel,
    EvalError,
    Ledger,
    TutorPolicy,
    usd_to_nano,
)
from lecturelens_real_eval.tutor_runner import (
    TutorProvider,
    append,
    review_turn,
    verify_inputs,
)

DSN = "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"


def mock_transport(scripts, fault=None):
    model = MockTutor()
    negatives = {t["text"] for d in scripts for t in d["turns"] if t["expected_insufficient"]}
    attempts = 0

    def send(request):
        nonlocal attempts
        attempts += 1
        data = json.loads(request.content)
        body = json.loads(data["messages"][-1]["content"])
        if fault and attempts == 1:
            if fault == "timeout":
                raise httpx.ReadTimeout("SYNTHETIC_TIMEOUT")
            return httpx.Response(200, json={"SYNTHETIC_MALFORMED": True})
        if data["model"] == "deepseek-v4-pro":
            # Oracle labels test serialization and accounting only, never semantic quality.
            name, args = (
                "review_tutor_turn",
                dict(
                    answer_supported=True,
                    context_retained=True,
                    socratic_compliant=True,
                    abstention_clean=True,
                ),
            )
        else:
            response = model.decide(data["messages"], data["tools"], 20)
            name, args = response["name"], response["arguments"]
            if body["observations"] and body["learner_text"] in negatives:
                name, args = (
                    "finish_tutor_turn",
                    dict(outcome="insufficient_evidence", text=ABSTENTION),
                )
        return httpx.Response(
            200,
            json={
                "model": "MOCK_SYNTHETIC_V1",
                "usage": {"prompt_tokens": 120, "completion_tokens": 80},
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": name,
                                        "arguments": json.dumps(args),
                                    },
                                }
                            ]
                        },
                    }
                ],
            },
        )

    return httpx.MockTransport(send)


class MetadataTransport(httpx.BaseTransport):
    """Tee bounded response metadata without changing the frozen channel parser."""

    def __init__(self, inner):
        self.inner, self.metadata = inner, {}

    def handle_request(self, request):
        self.metadata = {}
        response = self.inner.handle_request(request)
        if response.is_stream_consumed:
            self.record_metadata(response.content)
        original = response.stream
        owner = self

        class Stream(httpx.SyncByteStream):
            def __iter__(self):
                captured = bytearray()
                for chunk in original:
                    if len(captured) + len(chunk) <= 128 * 1024:
                        captured.extend(chunk)
                    yield chunk
                owner.record_metadata(captured)

            def close(self):
                original.close()

        response.stream = Stream()
        return response

    def record_metadata(self, body):
        if len(body) > 128 * 1024:
            return
        try:
            data = json.loads(body)
            for source, target in (
                ("model", "returned_model_version"),
                ("system_fingerprint", "system_fingerprint"),
            ):
                value = data.get(source)
                if isinstance(value, str) and len(value) <= 128:
                    self.metadata[target] = value
        except (ValueError, TypeError, AttributeError):
            pass  # Channel owns schema validation; missing metadata stays explicit.

    def close(self):
        self.inner.close()


class RecordedChannel(Channel):
    def __init__(self, *args, records, pricing_source=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.pricing_source = pricing_source
        self.records, self.turn_key = records, None
        self.turn_calls = []

    def request(self, *args, **kwargs):
        purpose = kwargs.get("purpose", "tutor")
        row = dict(
            turn_key=self.turn_key,
            purpose=purpose,
            live=self.policy.live,
            requested_model="deepseek-flash" if purpose == "tutor" else "deepseek-v4-pro",
            returned_model_version=None,
            version_status="MISSING_FROM_RESPONSE",
            system_fingerprint=None,
            usage_source="PROVIDER" if self.policy.live else "MOCK_NOT_BILLABLE",
            prompt_tokens=None,
            completion_tokens=None,
            status="FAILED",
            error=None,
            pricing_source=self.pricing_source,
            cost_status="NOT_RUN",
            billed_usd=None,
        )
        started = time.monotonic()
        try:
            result = super().request(*args, **kwargs)
            row.update(status="SUCCEEDED", **result["usage"])
            return result
        except Exception as exc:
            row["error"] = exc.code if isinstance(exc, EvalError) else "CHANNEL_EXCEPTION"
            raise
        finally:
            if row["status"] == "SUCCEEDED":
                row.update(self.transport.metadata)
            if row["returned_model_version"]:
                row["version_status"] = (
                    "MOCK" if not self.policy.live else "PROVIDER_REPORTED_ALIAS_OR_VERSION"
                )
            row["latency_s"] = time.monotonic() - started
            self.turn_calls.append(row)
            append(self.records, row)


def reconcile(scripts, records):
    expected = [(d, i, t) for d in scripts for i, t in enumerate(d["turns"], 1)]
    by_key = {r["turn_key"]: r for r in records}
    if len(by_key) != len(records):
        raise ValueError("DUPLICATE_TURN_RESULT")
    keys = {f"{d['dialogue_id']}:{i}" for d, i, _ in expected}
    if not by_key.keys() <= keys:
        raise ValueError("UNEXPECTED_TURN_RESULT")
    result = []
    for d, i, task in expected:
        key = f"{d['dialogue_id']}:{i}"
        result.append(
            by_key.get(key)
            or dict(
                turn_key=key,
                dialogue_id=d["dialogue_id"],
                ordinal=i,
                course_id=d["course_id"],
                split="holdout" if d["course_id"] == "energy" else "development",
                script=task,
                status="MISSING",
                error_code="RESULT_MISSING",
                answer="",
                evaluation="",
                outcome=None,
                citations=[],
                calls=[],
            )
        )
    return result


def preflight(live, pricing):
    verify_inputs()  # All historical candidate pins remain unchanged.
    load()
    frozen = json.loads((HERE / "candidate.json").read_text())
    for path, expected in frozen["files"].items():
        if digest(ROOT / path) != expected:
            raise ValueError("SCALE_CANDIDATE_CHANGED")
    if live:
        if os.environ.get("LECTURELENS_REAL_EVAL") != "1" or not pricing:
            raise ValueError("LIVE_REQUIRES_OPT_IN_AND_PRICING")
        p = json.loads(Path(pricing).read_text())
        # Legacy channel ceilings must be explicitly revalidated before a future trial.
        if (
            p.get("rates_usd_per_million")
            != {"deepseek-flash": [0.30, 1.20], "deepseek-v4-pro": [1.74, 3.96]}
            or not p.get("source_url", "").startswith("https://")
            or not p.get("verified_at")
            or p.get("currency") != "USD"
        ):
            raise ValueError("PRICING_NOT_COMPATIBLE_WITH_FROZEN_CHANNEL")
    return frozen


def accounting_totals(shards):
    known = [s for s in shards if s is not None]
    values = dict(
        reserved_calls=sum(s["calls"] for s in known),
        settled_calls=sum(s["calls"] - s["pending"] for s in known),
        pending_calls=sum(s["pending"] for s in known),
    )
    unknown = len(shards) - len(known)
    return dict(
        **{k: None if unknown else v for k, v in values.items()},
        unknown_accounting_shards=unknown,
        known_accounting=values,
    )


def run(args):
    frozen = preflight(args.live, args.pricing)
    snapshot, groups, counts = load()
    scripts = [d for ds in groups.values() for d in ds]
    if args.smoke:
        scripts = [next(d for d in scripts if d["course_id"] == c) for c in snapshot["lectures"]]
    courses = list(snapshot["lectures"])
    per_calls, per_nano = (
        args.max_calls // len(courses),
        usd_to_nano(args.max_usd) // len(courses),
    )
    identity = digest(HERE / "candidate.json")
    policy = TutorPolicy(
        live=args.live,
        max_calls=per_calls,
        max_nano_usd=per_nano,
        candidate_sha256=identity,
    )
    policy.validate()
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False)
    config = dict(
        data_kind="REAL" if args.live else "MOCK",
        quality_status="NOT_RUN",
        code_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        candidate_sha256=identity,
        dataset_version=frozen["dataset_version"],
        dataset_lock_sha256=digest(HERE / "dataset-lock.json"),
        smoke=args.smoke,
        fault=args.fault,
        max_calls=args.max_calls,
        max_usd=args.max_usd,
        shards=len(courses),
        per_shard_calls=per_calls,
        per_shard_nano_usd=per_nano,
        pricing_sha256=digest(args.pricing) if args.pricing else None,
        invocation={k: v for k, v in vars(args).items() if k != "dsn"},
        counts=counts,
    )
    write(out / "config.json", config)
    all_rows, failures = [], []
    accountings = []
    for course in courses:
        subset = [d for d in scripts if d["course_id"] == course]
        shard = out / course
        shard.mkdir()
        ledger = Ledger(DSN, shard / "ledger.jsonl", f"{out.name}-{course}", policy)
        runtime = None
        rows = []
        try:
            ledger.install()
            channel = RecordedChannel(
                ledger,
                records=shard / "calls.jsonl",
                pricing_source=json.loads(Path(args.pricing).read_text()) if args.pricing else None,
                transport=MetadataTransport(
                    httpx.HTTPTransport(trust_env=False, retries=0)
                    if args.live
                    else mock_transport(subset, args.fault)
                ),
            )
            authority = SnapshotAuthority(snapshot)
            provider = TutorProvider(channel, authority)
            store = TutorStore(ledger.dsn)
            runtime = TutorRuntime(store, authority, provider)
            runtime.initialize()
            for script in subset:
                scope = dict(
                    owner_id=811007,
                    course_id=f"scale-{out.name}-{script['dialogue_id']}"[:128],
                    revision=1,
                )
                authority.register(scope, script["lecture_id"])
                session = runtime.command(Command(**scope, operation="CREATE", request_key="session"))[
                    "session"
                ]
                scope["session_id"] = session["session_id"]
                provider.scope = scope
                history = []
                for ordinal, task in enumerate(script["turns"], 1):
                    channel.turn_key = f"{script['dialogue_id']}:{ordinal}"
                    channel.turn_calls = []
                    provider.proposals = []
                    runtime.command(
                        Command(
                            **scope,
                            operation="TURN",
                            client_turn_id=f"turn-{ordinal}",
                            text=task["text"],
                            socratic=task["socratic"],
                        )
                    )
                    runtime.execute(
                        next(c for c in store.candidates() if c["session_id"] == session["session_id"])
                    )
                    turn = runtime.command(Command(**scope, operation="GET"))["turns"][-1]
                    canonical = {e["evidence_id"]: e for e in authority.rows(scope)}
                    turn["citations"] = [canonical[c["evidence_id"]] for c in turn["citations"]]
                    turn.update(
                        turn_key=channel.turn_key,
                        dialogue_id=script["dialogue_id"],
                        ordinal=ordinal,
                        course_id=course,
                        split=snapshot["lectures"][course]["split"],
                        script=task,
                        proposals=provider.proposals,
                        review=None,
                    )
                    if turn["status"] == "completed":
                        try:
                            turn["review"] = review_turn(channel, history, task, turn)
                        except Exception:  # noqa: BLE001 -- preserve failed review without provider exception text
                            turn["review"] = {"error": "REVIEW_FAILED"}
                    turn["calls"] = channel.turn_calls.copy()
                    rows.append(turn)
                    append(shard / "turns.jsonl", turn)
                    history = [
                        *history,
                        dict(
                            learner=task["text"],
                            tutor=turn["answer"],
                            status=turn["status"],
                            outcome=turn["outcome"],
                        ),
                    ][-6:]
                    if ledger.check()["blocked"]:
                        raise EvalError(ledger.check()["blocked"])
        except Exception as exc:  # noqa: BLE001 -- preserve failed shard without secrets
            failures.append(
                dict(
                    course_id=course,
                    error_type=type(exc).__name__,
                    error=exc.code if isinstance(exc, EvalError) else "SHARD_FAILED",
                )
            )
        finally:
            if runtime:
                runtime.close()
            try:
                accounting = ledger.check()
            except Exception:  # noqa: BLE001 -- unknown accounting must not become zero calls
                accounting = None
                failures.append(dict(course_id=course, error="ACCOUNTING_UNKNOWN"))
            accountings.append(accounting)
            write(
                shard / "accounting.json",
                dict(
                    legacy_reservation_accounting=accounting,
                    note="MOCK arithmetic is not billing; failed/unknown calls retain reservations.",
                ),
            )
        all_rows.extend(reconcile(subset, rows))
    for row in all_rows:
        append(out / "turns.jsonl", row)
    statuses = Counter(r["status"] for r in all_rows)
    review_failed = sum(
        r.get("review", {}).get("error") is not None if r.get("review") else True for r in all_rows
    )
    complete = (
        len(all_rows) == sum(len(d["turns"]) for d in scripts)
        and not failures
        and not review_failed
        and all(r["status"] == "completed" for r in all_rows)
    )
    summary = dict(
        data_kind=config["data_kind"],
        quality_status="NOT_RUN",
        cost_status="NOT_RUN",
        real_tokens_status="NOT_RUN",
        human_scores_status="NOT_RUN",
        mechanics_status="COMPLETE" if complete else "INCOMPLETE",
        courses=len(courses),
        sessions=len(scripts),
        scheduled_turns=len(all_rows),
        statuses=dict(statuses),
        review_failed_or_missing=review_failed,
        failures=failures,
        recorded_calls=sum(len(r["calls"]) for r in all_rows),
        **accounting_totals(accountings),
        failure_reasons=dict(Counter(r.get("error_code") for r in all_rows if r["status"] != "completed")),
    )
    write(out / "summary.json", summary)
    print(json.dumps(summary))
    return 0 if complete else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--output", required=True)
    p.add_argument("--smoke", action="store_true")
    p.add_argument("--fault", choices=["timeout", "malformed"])
    p.add_argument("--max-calls", type=int, default=1200)
    p.add_argument("--max-usd", default="2.80")
    p.add_argument("--live", action="store_true")
    p.add_argument("--pricing")
    a = p.parse_args()
    if a.live and (a.fault or a.smoke):
        p.error("Live trials must use full frozen scope and no synthetic faults")
    return run(a)


if __name__ == "__main__":
    raise SystemExit(main())
