"""Execute only the explicitly frozen 20-turn queue through the existing P8 channel."""

import argparse
import json
import re
import subprocess
from collections import Counter
from pathlib import Path

import httpx
from plan import expected_rows, load_queue
from shared import BASE, ROOT, digest, legacy, object_hash, read, write


def run(args):
    queue, scripts, snapshot, identity = load_queue(args.queue)
    legacy.preflight(args.live, args.pricing)
    courses = list(dict.fromkeys(d["course_id"] for d in scripts))
    policy = legacy.TutorPolicy(
        live=args.live,
        max_calls=args.max_calls // 2,
        max_nano_usd=legacy.usd_to_nano(args.max_usd) // 2,
        candidate_sha256=identity,
    )
    policy.validate()
    out = Path(args.output)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,60}", out.name):
        raise ValueError("PILOT_RUN_NAME_INVALID")
    out.mkdir(parents=True, exist_ok=False)
    expected = expected_rows(scripts)
    write(out / "expected-turns.json", dict(queue_sha256=digest(args.queue), turns=expected))
    config = dict(
        schema="tutor-scale-v2",
        data_kind="REAL" if args.live else "MOCK",
        code_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        candidate_sha256=identity,
        queue_sha256=digest(args.queue),
        queue_version=queue["queue_version"],
        dataset_version=queue["dataset_version"],
        dataset_lock_sha256=digest(BASE / "dataset-lock.json"),
        expected_turns_sha256=object_hash(expected),
        scope="frozen_development_queue",
        selected_dialogue_ids=[d["dialogue_id"] for d in scripts],
        course_ids=courses,
        max_calls=args.max_calls,
        max_usd=args.max_usd,
        per_shard_calls=policy.max_calls,
        per_shard_nano_usd=policy.max_nano_usd,
        live=args.live,
        fault=args.fault,
        pricing_sha256=digest(args.pricing) if args.pricing else None,
        quality_status="NOT_RUN",
        cost_status="NOT_RUN",
    )
    write(out / "config.json", config)
    all_rows, failures, accountings = [], [], []
    for course in courses:
        subset = [d for d in scripts if d["course_id"] == course]
        shard = out / course
        shard.mkdir()
        ledger = legacy.Ledger(legacy.DSN, shard / "ledger.jsonl", f"{out.name}-{course}", policy)
        rows = []
        runtime = None
        try:
            ledger.install()
            channel = legacy.RecordedChannel(
                ledger,
                records=shard / "calls.jsonl",
                pricing_source=read(args.pricing) if args.pricing else None,
                transport=legacy.MetadataTransport(
                    httpx.HTTPTransport(trust_env=False, retries=0)
                    if args.live
                    else legacy.mock_transport(subset, args.fault)
                ),
            )
            authority = legacy.SnapshotAuthority(snapshot)
            provider = legacy.TutorProvider(channel, authority)
            store = legacy.TutorStore(ledger.dsn)
            runtime = legacy.TutorRuntime(store, authority, provider)
            runtime.initialize()
            for script in subset:
                scope = dict(
                    owner_id=811008, course_id=f"pilot-{out.name}-{script['dialogue_id']}", revision=1
                )
                authority.register(scope, script["lecture_id"])
                session = runtime.command(legacy.Command(**scope, operation="CREATE", request_key="session"))[
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
                        legacy.Command(
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
                    turn = runtime.command(legacy.Command(**scope, operation="GET"))["turns"][-1]
                    sources = {e["evidence_id"]: e for e in authority.rows(scope)}
                    turn["citations"] = [sources[c["evidence_id"]] for c in turn["citations"]]
                    turn.update(
                        turn_key=channel.turn_key,
                        dialogue_id=script["dialogue_id"],
                        ordinal=ordinal,
                        course_id=course,
                        split="development",
                        script=task,
                        proposals=provider.proposals,
                        review=None,
                    )
                    if turn["status"] == "completed":
                        try:
                            turn["review"] = legacy.review_turn(channel, history, task, turn)
                        except Exception:  # noqa: BLE001 -- only constant codes, no provider bodies
                            turn["review"] = {"error": "REVIEW_FAILED"}
                    turn["calls"] = channel.turn_calls.copy()
                    rows.append(turn)
                    legacy.append(shard / "turns.jsonl", turn)
                    history = [
                        *history,
                        dict(
                            learner=task["text"],
                            tutor=turn["answer"],
                            status=turn["status"],
                            outcome=turn["outcome"],
                        ),
                    ][-6:]
                    blocked = ledger.check()["blocked"]
                    if blocked:
                        raise legacy.EvalError(blocked)
        except Exception as exc:  # noqa: BLE001 -- retain failed shard without secrets
            failures.append(
                dict(
                    course_id=course,
                    error=exc.code if isinstance(exc, legacy.EvalError) else "SHARD_FAILED",
                    error_type=type(exc).__name__,
                )
            )
        finally:
            if runtime:
                runtime.close()
            try:
                accounting = ledger.check()
            except Exception:  # noqa: BLE001 -- unknown is never zero usage
                accounting = None
                failures.append(dict(course_id=course, error="ACCOUNTING_UNKNOWN"))
            accountings.append(accounting)
            write(
                shard / "accounting.json",
                dict(legacy_reservation_accounting=accounting, cost_status="NOT_RUN"),
            )
        all_rows.extend(legacy.reconcile(subset, rows))
    for row in all_rows:
        legacy.append(out / "turns.jsonl", row)
    statuses = Counter(r["status"] for r in all_rows)
    reviews_missing = sum(not r.get("review") or bool(r["review"].get("error")) for r in all_rows)
    complete = statuses == {"completed": 20} and not failures and not reviews_missing
    summary = dict(
        data_kind=config["data_kind"],
        scope=config["scope"],
        quality_status="NOT_RUN",
        cost_status="NOT_RUN",
        human_scores_status="NOT_RUN",
        real_tokens_status="NOT_RUN",
        mechanics_status="COMPLETE" if complete else "INCOMPLETE",
        courses=2,
        sessions=4,
        scheduled_turns=20,
        statuses=dict(statuses),
        review_failed_or_missing=reviews_missing,
        failures=failures,
        recorded_calls=sum(len(r["calls"]) for r in all_rows),
        **legacy.accounting_totals(accountings),
    )
    write(out / "summary.json", summary)
    print(json.dumps(summary))
    return 0 if complete else 1


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queue", required=True, help="Explicit frozen queue file; no full-scope fallback")
    p.add_argument("--output", required=True)
    p.add_argument("--live", action="store_true")
    p.add_argument("--pricing")
    p.add_argument("--max-calls", type=int)
    p.add_argument("--max-usd", help="Explicit live cap; Mock default is historical reservation arithmetic")
    p.add_argument("--fault", choices=["timeout", "malformed"])
    args = p.parse_args()
    if args.live and args.fault:
        p.error("Synthetic faults are Mock only")
    if args.live and (args.max_calls is None or args.max_usd is None):
        p.error("Live requires explicit call and USD caps; no inherited spending authorization")
    if args.max_calls is None:
        args.max_calls = 160
    if args.max_usd is None:
        args.max_usd = "1.40"
    if not 2 <= args.max_calls <= 160:
        p.error("Pilot call cap must be between 2 and 160")
    return run(args)


if __name__ == "__main__":
    raise SystemExit(main())
