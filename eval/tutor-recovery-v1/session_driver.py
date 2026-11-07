"""Offline-only session-isolated batch protocol; never inherits spending authority."""

import os
import subprocess
from pathlib import Path

import contract
import httpx
from lecturelens_real_eval.tutor.grounded_runtime import (
    GroundedTutorRuntime,
    PassageAuthority,
)
from lecturelens_real_eval.tutor.observed_channel import DecodedMetadataTransport
from lecturelens_real_eval.tutor.repair_context_runtime import RepairContextTutorRuntime

bridge = contract.bridge
data = contract.data
LOCAL_FAILURES = frozenset(
    {
        "TUTOR_REPAIR_BUDGET_UNAVAILABLE",
        "TUTOR_BUDGET_EXHAUSTED",
        "TUTOR_FINISH_FORMAT_INVALID",
        "TUTOR_SOCRATIC_CONTRACT",
        "TUTOR_DEADLINE",
    }
)
PROTOCOL = "session-isolated-v1"


def disposition(turn, accounting, policy):
    # Unknown/global accounting always dominates a local content/turn failure.
    if (
        not isinstance(accounting, dict)
        or accounting.get("blocked")
        or accounting.get("pending") != 0
        or type(accounting.get("calls")) is not int
        or type(accounting.get("nano_usd")) is not int
        or accounting["calls"] >= policy.max_calls
        or accounting["nano_usd"] >= policy.max_nano_usd
    ):
        return "STOP_ALL"
    if turn["status"] == "completed":
        return "CONTINUE"
    if turn["status"] == "failed" and turn.get("error_code") in LOCAL_FAILURES:
        return "STOP_SESSION"
    return "STOP_ALL"


def run(output, dsn, transport, *, legacy=False, max_calls=80, max_nano_usd=700_000_000):
    """Explicit Mock transport only. A future live adapter requires a separate freeze/grant."""
    if not isinstance(transport, httpx.MockTransport):
        raise ValueError("OFFLINE_MOCK_TRANSPORT_REQUIRED")
    if os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
        raise ValueError("OFFLINE_SOCKET_FENCE_REQUIRED")
    if not 1 <= max_calls <= 80 or not 1 <= max_nano_usd <= 700_000_000:
        raise ValueError("OFFLINE_CAP_INVALID")
    identity = contract.verify_candidate()
    batch, scripts, snapshot = data.load()
    ordered = [
        next(s for s in scripts if s["dialogue_id"] == spec["dialogue_id"])
        for ref in batch["parts"]
        for spec in data.read(data.HERE / ref["path"])["sessions"]
    ]
    output = Path(output)
    output.mkdir(parents=True, exist_ok=False)
    planned = bridge.module.expected_rows(snapshot, ordered)
    config = {
        "candidate": bridge.repair_check.CANDIDATE if legacy else contract.CANDIDATE,
        "candidate_sha256": contract.PARENT if legacy else identity,
        "protocol": "legacy-stop-all-on-first-failure" if legacy else PROTOCOL,
        "execution_code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=contract.ROOT, text=True
        ).strip(),
        "batch_plan_sha256": data.digest(data.HERE / "batch-plan.json"),
        "data_kind": "OFFLINE_FIXED_OR_SYNTHETIC_RESPONSES_NOT_QUALITY",
        "live": False,
        "max_calls": max_calls,
        "max_nano_usd": max_nano_usd,
        "real_quality": "NOT_RUN",
        "real_cost": "NOT_RUN",
    }
    data.write(output / "config.json", config)
    data.write(output / "expected-turns.json", {"turns": planned})
    policy = bridge.legacy.TutorPolicy(
        live=False,
        max_calls=max_calls,
        max_nano_usd=max_nano_usd,
        candidate_sha256=config["candidate_sha256"],
    )
    ledger = bridge.legacy.Ledger(dsn, output / "ledger.jsonl", "recovery-" + output.name, policy)
    channel = bridge.repair_run.TutorOnlyChannel(
        ledger,
        records=output / "calls.jsonl",
        transport=DecodedMetadataTransport(transport),
    )
    authority = PassageAuthority(snapshot)
    provider = bridge.legacy.TutorProvider(channel, authority)
    store = bridge.legacy.TutorStore(ledger.dsn)
    runtime = (GroundedTutorRuntime if legacy else RepairContextTutorRuntime)(store, authority, provider)
    results, stops = [], []
    try:
        ledger.install()
        runtime.initialize()
        stop_all = False
        for script in ordered:
            scope = dict(
                owner_id=811012,
                course_id=f"{output.name}-{script['dialogue_id']}",
                revision=1,
            )
            authority.register(scope, script["lecture_id"])
            session = runtime.command(
                bridge.legacy.Command(**scope, operation="CREATE", request_key="session")
            )["session"]
            scope["session_id"] = session["session_id"]
            provider.scope = scope
            for ordinal, task in enumerate(script["turns"], 1):
                key = f"{script['dialogue_id']}:{ordinal}"
                channel.turn_key, channel.turn_calls, provider.proposals = key, [], []
                runtime.command(
                    bridge.legacy.Command(
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
                turn = runtime.command(bridge.legacy.Command(**scope, operation="GET"))["turns"][-1]
                sources = {e["evidence_id"]: e for e in authority.rows(scope)}
                turn["citations"] = [sources[c["evidence_id"]] for c in turn["citations"]]
                turn.update(next(p for p in planned if p["turn_key"] == key))
                turn.update(calls=channel.turn_calls.copy(), proposals=provider.proposals.copy())
                results.append(turn)
                bridge.legacy.append(output / "partial-turns.jsonl", turn)
                action = disposition(turn, ledger.check(), policy)
                if legacy and turn["status"] != "completed":
                    action = "STOP_ALL"
                if action != "CONTINUE":
                    stops.append(
                        dict(
                            turn_key=key,
                            action=action,
                            error_code=turn.get("error_code"),
                        )
                    )
                    stop_all = action == "STOP_ALL"
                    # Never synthesize an antecedent or execute the remaining turns of
                    # this failed conversation; later sessions start with empty history.
                    break
            if stop_all:
                break
    except Exception as error:  # noqa: BLE001 -- retain missing outcomes; never expose provider/DB text
        stops.append(
            dict(
                action="STOP_ALL",
                error_code="OFFLINE_BATCH_ACCOUNTING_OR_EXECUTION_FAILED",
                error_type=type(error).__name__,
            )
        )
    finally:
        runtime.close()
    try:
        accounting = ledger.check()
    except Exception:  # noqa: BLE001 -- unknown accounting is not zero or permission to continue
        accounting = None
        stops.append(dict(action="STOP_ALL", error_code="OFFLINE_ACCOUNTING_UNKNOWN"))
    rows = bridge.reconcile(planned, results)
    for row in rows:
        bridge.legacy.append(output / "turns.jsonl", row)
    summary = {
        **bridge.execution_counts(rows),
        "stops": stops,
        "ledger": accounting,
        "mechanics_status": "COMPLETE"
        if all(r["status"] == "completed" for r in rows)
        and accounting is not None
        and not accounting["blocked"]
        and accounting["pending"] == 0
        else "INCOMPLETE",
        "real_requests": 0,
        "real_quality": "NOT_RUN",
        "real_cost": "NOT_RUN",
    }
    data.write(output / "summary.json", summary)
    return summary
