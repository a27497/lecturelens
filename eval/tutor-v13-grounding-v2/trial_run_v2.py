"""Frozen sixteen-position v13 new-development trial; preparation-only unless explicitly budgeted."""

import argparse
import hashlib
import json
import os
import re
import subprocess
from pathlib import Path

import httpx
import v13_v2_contract as contract
from lecturelens_real_eval.tutor.claim_grounding_runtime import (
    ClaimGroundingTutorRuntime,
    LessonAuthority,
)
from lecturelens_real_eval.tutor.observed_channel import DecodedMetadataTransport

bridge, data = contract.bridge, contract.data


def preflight(args):
    plan, scripts, snapshot, expected, protocol = contract.verify()
    if (args.agent, args.model, args.reviewer, args.concurrency) != (
        contract.CANDIDATE,
        "deepseek-flash",
        "off",
        1,
    ):
        raise ValueError("RERUN_EXPLICIT_V13_MODEL_SETTINGS_REQUIRED")
    policy = None
    if args.mock or args.live:
        if args.max_calls is None or args.max_usd is None or not args.output:
            raise ValueError("RERUN_NEW_EXPLICIT_CAPS_AND_OUTPUT_REQUIRED")
        if type(args.max_calls) is not int or not 1 <= args.max_calls <= 80:
            raise ValueError("RERUN_CALL_CAP_INVALID")
        money = bridge.legacy.usd_to_nano(args.max_usd)
        policy = bridge.legacy.TutorPolicy(
            live=args.live,
            max_calls=args.max_calls,
            max_nano_usd=money,
            candidate_sha256=contract.verify_candidate(),
        )
        policy.validate()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,38}", Path(args.output).name):
            raise ValueError("RERUN_SINGLE_USE_NAME_INVALID")
        if args.mock and os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
            raise ValueError("RERUN_MOCK_SOCKET_FENCE_REQUIRED")
        if args.live:
            if os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1":
                raise ValueError("RERUN_LIVE_FORBIDDEN_INSIDE_OFFLINE_FENCE")
            if (
                not args.ack_new_batch_authorization
                or not args.ack_ledger_not_billing_cap
                or not args.pricing
            ):
                raise ValueError("RERUN_NEW_AUTHORIZATION_PRICING_AND_BILLING_ACK_REQUIRED")
            bridge.repair_run.check_pricing(args.pricing)
    return plan, scripts, snapshot, expected, protocol, policy


def accounting_safe(state):
    return (
        isinstance(state, dict)
        and "blocked" in state
        and state["blocked"] is None
        and type(state.get("pending")) is int
        and state["pending"] == 0
        and type(state.get("calls")) is int
        and state["calls"] >= 0
        and type(state.get("nano_usd")) is int
        and state["nano_usd"] >= 0
    )


def classify(turn, state, policy, protocol):
    if not accounting_safe(state):
        return "STOP_ALL", "ACCOUNTING_UNSAFE_OR_UNKNOWN"
    # Channel failures dominate even a nominally local runtime code. Failed sends
    # may retain a full reservation with unknown usage while pending is already zero.
    for call in turn.get("calls", []):
        if call.get("status") != "SUCCEEDED" or call.get("anomalies"):
            return "STOP_ALL", "CHANNEL_OR_USAGE_PROTOCOL_FAILURE"
        usage = call.get("usage")
        if not isinstance(usage, dict) or any(
            type(usage.get(k)) is not int or usage[k] < 0 for k in ("prompt_tokens", "completion_tokens")
        ):
            return "STOP_ALL", "USAGE_UNKNOWN_OR_INVALID"
    if state["calls"] >= policy.max_calls or state["nano_usd"] >= policy.max_nano_usd:
        return "STOP_ALL", "GLOBAL_CAP_REACHED"
    if turn["status"] == "completed":
        return "CONTINUE", "COMPLETED"
    if turn["status"] == "failed" and turn.get("error_code") in protocol["local_terminal_errors"]:
        return "STOP_SESSION", turn["error_code"]
    return "STOP_ALL", "SAFETY_OR_UNCLASSIFIED_TERMINAL_FAILURE"


class RerunChannel(bridge.repair_run.TutorOnlyChannel):
    """Stop decoded accounting anomalies before the runtime can make another decision."""

    def request(self, *args, **kwargs):
        result = super().request(*args, **kwargs)
        if self.turn_calls[-1].get("anomalies"):
            self.ledger.block("RERUN_USAGE_METADATA_INCONSISTENT")
            raise bridge.legacy.EvalError("RERUN_USAGE_METADATA_INCONSISTENT")
        return result


class WireEvidence(httpx.BaseTransport):
    """Observe exact request bodies only; ledger reservation still precedes this layer."""

    def __init__(self, inner, output, cap):
        self.inner, self.output, self.cap, self.count = inner, output, cap, 0

    def handle_request(self, request):
        if (
            self.count >= self.cap
            or request.method != "POST"
            or str(request.url) != "https://api.deepseek.com/chat/completions"
        ):
            raise ValueError("RERUN_TRANSPORT_ROUTE_OR_CAP")
        sequence = self.count + 1
        raw = request.content
        with (self.output / "wire" / f"{sequence:03d}-request.json").open("xb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        self.count = sequence
        row = {
            "sequence": self.count,
            "wire_sha256": hashlib.sha256(raw).hexdigest(),
            "http_status": None,
            "transport_error": None,
        }
        try:
            response = self.inner.handle_request(request)
            row["http_status"] = response.status_code
            return response
        except Exception as error:
            row["transport_error"] = type(error).__name__
            raise
        finally:
            bridge.legacy.append(self.output / "wire-events.jsonl", row)

    def close(self):
        self.inner.close()


def capture(store, candidate, scope, script, expected, channel, provider, authority):
    with store.connect() as conn:
        session, turn = store.rows(conn, candidate["turn_id"])
    if any(session[k] != scope[k] for k in ("owner_id", "course_id", "revision", "session_id")):
        raise ValueError("RERUN_CAPTURE_SCOPE_MISMATCH")
    # Evaluation-only read of this newly created synthetic turn survives an
    # authority failure. It never publishes a result or authorizes a source.
    sources = {e["evidence_id"]: e for e in authority.snapshot["lectures"][script["lecture_id"]]["evidence"]}
    turn["citations"] = [sources[c["evidence_id"]] for c in turn["citations"]]
    turn.update(
        expected,
        calls=channel.turn_calls.copy(),
        proposals=provider.proposals.copy(),
        stored_scope=scope.copy(),
    )
    return turn


def counts(rows):
    completed = sum(r["status"] == "completed" for r in rows)
    skipped = sum(r["status"] == "SKIPPED" for r in rows)
    missing = sum(r["status"] == "MISSING" for r in rows)
    return dict(
        expected=16,
        completed=completed,
        failed=16 - completed - skipped - missing,
        skipped=skipped,
        missing=missing,
        attempted=16 - skipped - missing,
        scorable=completed,
        semantically_scored=0,
        unknown_attempts=sum(r["status"] in {"UNKNOWN", "queued", "running"} for r in rows),
        unexecuted_including_skipped=skipped + missing,
    )


def run(args, *, dsn=None, transport=None):
    plan, scripts, snapshot, expected, protocol, policy = preflight(args)
    identity = dict(
        candidate=contract.CANDIDATE,
        candidate_sha256=contract.verify_candidate(),
        plan_sha256=contract.digest(contract.HERE / "run-plan.json"),
        adapter_lock_sha256=data.digest(contract.HERE / "adapter-lock.json"),
        protocol=protocol["version"],
    )
    if policy is None:
        return dict(
            mode="PREPARE_ONLY_NO_EGRESS",
            **identity,
            counts=plan["counts"],
            settings=plan["settings"],
            normal_requests=32,
            maximum_requests=80,
            max_usd="NEW_USER_AUTHORIZATION_REQUIRED",
            max_calls="NEW_USER_AUTHORIZATION_REQUIRED",
            real_quality="NOT_RUN",
            real_cost="NOT_RUN",
        )
    if (args.mock and transport is not None and not isinstance(transport, httpx.MockTransport)) or (
        args.live and transport is not None
    ):
        raise ValueError("RERUN_TRANSPORT_MODE_MISMATCH")
    # All source/identity/settings/pricing/cap checks precede creation, DB and transport.
    isolated = bridge.legacy.Ledger(
        dsn or bridge.legacy.DSN,
        Path(args.output) / "ledger.jsonl",
        "ground-v13-" + Path(args.output).name,
        policy,
    )
    out = Path(args.output)
    out.mkdir(parents=True, exist_ok=False, mode=0o700)
    (out / "wire").mkdir(mode=0o700)
    config = dict(
        **identity,
        execution_code_sha=subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=contract.ROOT, text=True
        ).strip(),
        data_kind="REAL" if args.live else "MOCK_NOT_MODEL_QUALITY",
        live=args.live,
        settings=plan["settings"],
        original_inputs=plan["original_inputs"],
        max_calls=policy.max_calls,
        max_local_nano_usd=policy.max_nano_usd,
        allocation="ONE_NEW_GLOBAL_LEDGER",
        authorization="USER_ACKNOWLEDGED_NEW_BATCH" if args.live else "MOCK_ONLY_NO_PAID_AUTHORITY",
        supplier_bill_hard_cap="UNVERIFIED",
        immutable_model_version="UNKNOWN_MOVING_ALIAS",
        pricing_sha256=data.digest(args.pricing) if args.live else None,
    )
    data.write(out / "config.json", config)
    data.write(out / "expected-turns.json", dict(turns=expected))
    ledger, runtime, channel = isolated, None, None
    results, attempts, stops = {}, {}, []
    active = None
    global_reason = None
    try:
        ledger.install()
        inner = (
            transport
            if transport is not None
            else (
                bridge.legacy.mock_transport(scripts)
                if args.mock
                else httpx.HTTPTransport(trust_env=False, retries=0)
            )
        )
        wire = WireEvidence(inner, out, policy.max_calls)
        channel = RerunChannel(
            ledger,
            records=out / "calls.jsonl",
            pricing_source=data.read(args.pricing) if args.live else None,
            transport=DecodedMetadataTransport(wire),
        )
        authority = LessonAuthority(snapshot)
        provider = bridge.legacy.TutorProvider(channel, authority)
        store = bridge.legacy.TutorStore(ledger.dsn)
        runtime = ClaimGroundingTutorRuntime(store, authority, provider)
        runtime.initialize()
        for script in scripts:
            scope = dict(owner_id=811012, course_id=f"{out.name}-{script['dialogue_id']}", revision=1)
            authority.register(scope, script["lecture_id"])
            scope["session_id"] = runtime.command(
                bridge.legacy.Command(**scope, operation="CREATE", request_key="session")
            )["session"]["session_id"]
            provider.scope = scope
            for ordinal, task in enumerate(script["turns"], 1):
                key = f"{script['dialogue_id']}:{ordinal}"
                planned = next(e for e in expected if e["turn_key"] == key)
                channel.turn_key, channel.turn_calls, provider.proposals = key, [], []
                submitted = runtime.command(
                    bridge.legacy.Command(
                        **scope,
                        operation="TURN",
                        client_turn_id=f"turn-{ordinal}",
                        text=task["text"],
                        socratic=task["socratic"],
                    )
                )
                candidate = dict(turn_id=submitted["turns"][-1]["turn_id"], session_id=scope["session_id"])
                attempts[key] = candidate
                active = (key, candidate, scope.copy(), script, planned)
                bridge.legacy.append(out / "attempted-turns.jsonl", dict(turn_key=key, **candidate))
                runtime.execute(candidate)
                turn = capture(store, candidate, scope, script, planned, channel, provider, authority)
                results[key] = turn
                active = None
                bridge.legacy.append(out / "partial-turns.jsonl", turn)
                action, reason = classify(turn, ledger.check(), policy, protocol)
                if action == "CONTINUE":
                    continue
                stops.append(
                    dict(turn_key=key, action=action, reason=reason, error_code=turn.get("error_code"))
                )
                if action == "STOP_ALL":
                    global_reason = reason
                else:
                    for following in expected:
                        if (
                            following["dialogue_id"] != script["dialogue_id"]
                            or following["ordinal"] <= ordinal
                        ):
                            continue
                        blockers = [
                            f"{script['dialogue_id']}:{n}"
                            for n in following["script"]["depends_on_turns"]
                            if results[f"{script['dialogue_id']}:{n}"]["status"] != "completed"
                        ]
                        results[following["turn_key"]] = dict(
                            **following,
                            status="SKIPPED",
                            answer=None,
                            outcome=None,
                            citations=[],
                            calls=[],
                            skip_code="DEPENDENCY_FAILED_OR_SKIPPED"
                            if blockers
                            else "SESSION_CLOSED_AFTER_LOCAL_FAILURE",
                            blocked_by=blockers,
                            root_failure=key,
                        )
                break
            if global_reason:
                break
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- fixed safe codes, preserve every scheduled outcome
        global_reason = (
            "BATCH_INTERRUPTED"
            if isinstance(error, KeyboardInterrupt)
            else "BATCH_EXECUTION_OR_ACCOUNTING_EXCEPTION"
        )
        stops.append(dict(action="STOP_ALL", reason=global_reason, error_type=type(error).__name__))
        if active is not None:
            key, candidate, scope, script, planned = active
            try:
                results[key] = capture(store, candidate, scope, script, planned, channel, provider, authority)
            except Exception:  # noqa: BLE001 -- preserve attempted identity even when DB/authority evidence cannot be read
                results[key] = dict(
                    **planned,
                    **candidate,
                    status="UNKNOWN",
                    answer=None,
                    citations=[],
                    calls=channel.turn_calls.copy(),
                    error_code="ATTEMPTED_RESULT_UNAVAILABLE",
                )
    finally:
        if runtime:
            runtime.close()
    try:
        accounting = ledger.check()
    except Exception:  # noqa: BLE001 -- no accounting reset, repair or resend
        accounting = None
        global_reason = "ACCOUNTING_UNKNOWN"
        stops.append(dict(action="STOP_ALL", reason=global_reason))
    rows = [
        results.get(
            e["turn_key"],
            dict(
                **e,
                status="MISSING",
                answer=None,
                outcome=None,
                citations=[],
                calls=[],
                missing_code="GLOBAL_STOP_BEFORE_TURN",
                stop_reason=global_reason or "RESULT_UNAVAILABLE",
            ),
        )
        for e in expected
    ]
    for row in rows:
        bridge.legacy.append(out / "turns.jsonl", row)
    execution = counts(rows)
    summary = dict(
        **identity,
        **execution,
        stops=stops,
        ledger=accounting,
        reviewer_calls=0,
        wire_requests=wire.count if channel else 0,
        mechanics_status="COMPLETE"
        if execution["completed"] == 16
        and accounting_safe(accounting)
        and global_reason in (None, "GLOBAL_CAP_REACHED")
        else "INCOMPLETE",
        quality_status="NOT_RUN",
        real_quality="NOT_RUN",
        actual_supplier_cost="UNKNOWN_NOT_QUERIED" if args.live else "NOT_RUN",
        comparison=dict(
            scheduled_task_denominator=16,
            completed_answer_denominator=execution["completed"],
            expected_answer_coverage_denominator=12,
            citation_pair_denominator="ALL_ANNOTATED_PAIRS_IN_COMPLETED_PUBLISHED_ANSWERS_INCLUDING_UNCERTAIN",
            claim_coverage_denominator="ALL_CITATION_REQUIRING_ASSERTIONS_IN_COMPLETED_PUBLISHED_ANSWERS_INCLUDING_OPTIONAL",
            candidate_and_stop_protocol_changed=True,
            old_answers_reused=False,
        ),
    )
    data.write(out / "summary.json", summary)
    return summary


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true")
    mode.add_argument("--live", action="store_true")
    p.add_argument("--agent", required=True, choices=[contract.CANDIDATE])
    p.add_argument("--model", required=True, choices=["deepseek-flash"])
    p.add_argument("--reviewer", choices=["off"], default="off")
    p.add_argument("--concurrency", type=int, choices=[1], default=1)
    p.add_argument("--max-calls", type=int)
    p.add_argument("--max-usd")
    p.add_argument("--output")
    p.add_argument("--pricing")
    p.add_argument("--ack-new-batch-authorization", action="store_true")
    p.add_argument("--ack-ledger-not-billing-cap", action="store_true")
    return p


if __name__ == "__main__":
    os.umask(0o077)
    try:
        result = run(parser().parse_args())
        print(json.dumps(result))
        raise SystemExit(1 if result.get("mechanics_status") == "INCOMPLETE" else 0)
    except Exception:  # noqa: BLE001 -- never echo provider, DB or credential details
        print(
            json.dumps(
                dict(error="V13_GROUNDING_PREFLIGHT_OR_STARTUP_REJECTED", real_calls="NOT_RUN_OR_UNKNOWN")
            )
        )
        raise SystemExit(2) from None
