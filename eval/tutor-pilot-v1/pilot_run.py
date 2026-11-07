"""Single-purpose frozen eight-turn pilot. Default: read-only preparation, no credentials or DB."""

import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-python-contract-v1"))
import contract_check as contract  # noqa: E402
from lecturelens_real_eval.tutor.python_runtime import PythonTutorRuntime  # noqa: E402
from public_bridge import execution_counts, legacy  # noqa: E402
from public_dataset import digest, expected_rows, read, write  # noqa: E402
from public_mock import reconcile  # noqa: E402

MODEL = "deepseek-flash"
PRICING = HERE / "pricing-observation-20261107.json"
ADAPTER_FILES = {"pilot_run.py", "test_pilot_run.py", "pricing-observation-20261107.json"}


def verify_adapter():
    lock = read(HERE / "adapter-lock.json")
    if set(lock["files"]) != ADAPTER_FILES:
        raise ValueError("PILOT_ADAPTER_FILE_SET_CHANGED")
    if any(digest(HERE / name) != sha for name, sha in lock["files"].items()):
        raise ValueError("PILOT_ADAPTER_CHANGED")
    return digest(HERE / "adapter-lock.json")


def check_pricing(path):
    value = read(path)
    if any(
        value.get(k) != v
        for k, v in {
            "source_url": "https://api-docs.deepseek.com/quick_start/pricing/",
            "verified_on": datetime.now(timezone.utc).date().isoformat(),
            "currency": "USD",
            "unit_tokens": 1_000_000,
            "requested_model": MODEL,
            "input_cache_miss_peak": "0.30",
            "output_peak": "1.20",
        }.items()
    ):
        raise ValueError("PILOT_PRICING_STALE_OR_INCOMPATIBLE_WITH_LEDGER")
    return value


class TutorOnlyChannel(legacy.RecordedChannel):
    def request(self, *args, **kwargs):
        # Reject before reservation, credential lookup or egress, even if a caller regresses.
        if kwargs.get("purpose", "tutor") != "tutor":
            raise legacy.EvalError("PILOT_REVIEWER_DISABLED")
        return super().request(*args, **kwargs)


def preflight(args):
    adapter = verify_adapter()
    plan, scripts, snapshot = contract.load_plan(args.plan)
    if (
        args.agent != contract.CANDIDATE
        or args.model != MODEL
        or args.concurrency != 1
        or args.reviewer != "off"
    ):
        raise ValueError("PILOT_AGENT_OR_MODEL_MISMATCH")
    if args.mock and os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
        raise ValueError("PILOT_MOCK_SOCKET_FENCE_REQUIRED")
    if args.live:
        if not args.ack_ledger_not_billing_cap or not args.pricing:
            raise ValueError("PILOT_LIVE_REQUIRES_PRICING_AND_CAP_ACKNOWLEDGEMENT")
        check_pricing(args.pricing)
    if args.mock or args.live:
        if args.max_calls is None or args.max_usd is None or not args.output:
            raise ValueError("PILOT_EXECUTION_REQUIRES_EXPLICIT_CAPS_AND_NEW_OUTPUT")
        if not 1 <= args.max_calls <= 40:
            raise ValueError("PILOT_TOTAL_CALL_CAP_INVALID")
        policy = legacy.TutorPolicy(
            live=args.live,
            max_calls=args.max_calls,
            max_nano_usd=legacy.usd_to_nano(args.max_usd),
            candidate_sha256=plan["candidate_manifest_sha256"],
        )
        policy.validate()  # Includes the independent live opt-in; no key lookup here.
    else:
        policy = None
    return plan, scripts, snapshot, adapter, policy


def run(args, *, dsn=None, transport=None):
    plan, scripts, snapshot, adapter, policy = preflight(args)
    if policy is None:
        return dict(
            mode="PREPARE_ONLY_NO_EGRESS",
            agent=contract.CANDIDATE,
            runtime_entrypoint=contract.ENTRYPOINT,
            model=MODEL,
            reviewer="DISABLED_NOT_RUN",
            concurrency=1,
            counts=plan["counts"],
            plan_sha256=digest(args.plan),
            candidate_sha256=plan["candidate_manifest_sha256"],
            adapter_sha256=adapter,
            normal_requests=16,
            optional_second_search_requests=24,
            maximum_requests=40,
            transport_retries=0,
            sdk_retries=0,
            application_transport_retries=0,
            money_cap="UNCONFIRMED_LEDGER_ONLY_NOT_SUPPLIER_BILL_CAP",
            real_calls="NOT_RUN",
            real_quality="NOT_RUN",
            real_cost="NOT_RUN",
        )
    out = Path(args.output)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,50}", out.name):
        raise ValueError("PILOT_RUN_NAME_INVALID")
    out.mkdir(parents=True, exist_ok=False)  # Single-use; never resume/replay unknown requests.
    planned = expected_rows(snapshot, scripts)
    config = dict(
        data_kind="REAL" if args.live else "MOCK",
        live=args.live,
        code_sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
        agent=contract.CANDIDATE,
        runtime_entrypoint=contract.ENTRYPOINT,
        candidate_sha256=plan["candidate_manifest_sha256"],
        adapter_sha256=adapter,
        dataset_version=plan["dataset_version"],
        dataset_lock_sha256=plan["dataset_lock_sha256"],
        plan_sha256=digest(args.plan),
        selected_dialogue_ids=[d["dialogue_id"] for d in scripts],
        requested_model=MODEL,
        reviewer="DISABLED_NOT_RUN",
        concurrency=1,
        transport_retries=0,
        sdk_retries=0,
        application_transport_retries=0,
        max_calls=policy.max_calls,
        max_ledger_nano_usd=policy.max_nano_usd,
        max_output_tokens=1200,
        supplier_bill_hard_cap="UNVERIFIED",
        pricing_sha256=digest(args.pricing) if args.live else None,
    )
    write(out / "config.json", config)
    write(out / "expected-turns.json", dict(plan_sha256=digest(args.plan), turns=planned))
    ledger = legacy.Ledger(dsn or legacy.DSN, out / "ledger.jsonl", "pilot-" + out.name, policy)
    runtime, results, failures, accounting = None, [], [], None
    try:
        ledger.install()  # One GLOBAL ledger, shared by both sequential sessions.
        inner = (
            transport
            if transport is not None
            else (
                legacy.httpx.HTTPTransport(trust_env=False, retries=0)
                if args.live
                else legacy.mock_transport(scripts)
            )
        )
        channel = TutorOnlyChannel(
            ledger,
            records=out / "calls.jsonl",
            pricing_source=read(args.pricing) if args.live else None,
            transport=legacy.MetadataTransport(inner),
        )
        authority = legacy.SnapshotAuthority(snapshot)
        provider = legacy.TutorProvider(channel, authority)
        store = legacy.TutorStore(ledger.dsn)
        runtime = PythonTutorRuntime(store, authority, provider)  # Never inherit legacy default identity.
        runtime.initialize()
        for script in scripts:
            scope = dict(owner_id=811011, course_id=f"pilot-{out.name}-{script['dialogue_id']}", revision=1)
            authority.register(scope, script["lecture_id"])
            session = runtime.command(legacy.Command(**scope, operation="CREATE", request_key="session"))[
                "session"
            ]
            scope["session_id"] = session["session_id"]
            provider.scope = scope
            for ordinal, task in enumerate(script["turns"], 1):
                channel.turn_key = f"{script['dialogue_id']}:{ordinal}"
                channel.turn_calls, provider.proposals = [], []
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
                turn.update(next(p for p in planned if p["turn_key"] == channel.turn_key))
                turn.update(
                    proposals=provider.proposals,
                    review=None,
                    review_status="DISABLED_NOT_RUN",
                    calls=channel.turn_calls.copy(),
                )
                results.append(turn)
                legacy.append(out / "partial-turns.jsonl", turn)
                state = ledger.check()
                if turn["status"] != "completed" or state["blocked"] or state["pending"]:
                    raise legacy.EvalError("PILOT_STOPPED_ON_FAILURE_OR_UNKNOWN_OUTCOME")
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- only fixed codes cross this boundary
        failures.append(
            dict(
                error=error.code if isinstance(error, legacy.EvalError) else "PILOT_ABORTED",
                error_type=type(error).__name__,
            )
        )
    finally:
        if runtime:
            runtime.close()
        try:
            accounting = ledger.check()
        except Exception:  # noqa: BLE001 -- unknown accounting is never zero
            failures.append(dict(error="PILOT_ACCOUNTING_UNKNOWN"))
    rows = reconcile(planned, results)
    for row in rows:
        legacy.append(out / "turns.jsonl", row)
    counts = execution_counts(rows)
    summary = dict(
        data_kind=config["data_kind"],
        **counts,
        failures=failures,
        mechanics_status="COMPLETE" if counts["completed_turns"] == 8 and not failures else "INCOMPLETE",
        reviewer="DISABLED_NOT_RUN",
        reviewer_calls=0,
        quality_status="NOT_RUN",
        human_agreement_status="NOT_RUN",
        real_cost_status="NOT_RUN",
        ledger_accounting=accounting,
        billing_hard_cap="UNVERIFIED",
    )
    write(out / "summary.json", summary)
    return summary


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true")
    mode.add_argument("--live", action="store_true")
    p.add_argument("--plan", required=True)
    p.add_argument("--agent", required=True, choices=[contract.CANDIDATE])
    p.add_argument("--model", required=True, choices=[MODEL])
    p.add_argument("--reviewer", choices=["off"], default="off")
    p.add_argument("--concurrency", type=int, choices=[1], default=1)
    p.add_argument("--max-calls", type=int)
    p.add_argument("--max-usd")
    p.add_argument("--pricing")
    p.add_argument("--ack-ledger-not-billing-cap", action="store_true")
    p.add_argument("--output")
    return p


if __name__ == "__main__":
    try:
        result = run(parser().parse_args())
        print(json.dumps(result))
        raise SystemExit(0 if result.get("mechanics_status") != "INCOMPLETE" else 1)
    except Exception:  # noqa: BLE001 -- no provider/DB/config bodies in CLI errors
        print(json.dumps(dict(error="PILOT_PREFLIGHT_OR_STARTUP_REJECTED", real_calls="NOT_RUN_OR_UNKNOWN")))
        raise SystemExit(2) from None
