#!/usr/bin/env python3
"""SIGKILL real worker processes at journal, graph, RPC and publication boundaries.

Requires an isolated PostgreSQL database named lecturelens_agent_test. No provider
credentials or real learner text are used. Model/Java stubs are deterministic;
PostgresSaver, runtime, budgets, approval commands and cleanup are real.
"""

import argparse
import collections
import hashlib
import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-service/tests"))

import test_study
from langgraph.checkpoint.postgres import PostgresSaver
from lecturelens_agent.store import VectorStore
from lecturelens_agent.study import approval, call_journal, telemetry
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyStore
from psycopg.conninfo import conninfo_to_dict


def snapshot(store, run):
    with store.connect() as conn:
        row = conn.execute(
            "SELECT * FROM study_run WHERE run_id=%s", (run["run_id"],)
        ).fetchone()
        if not row:
            return {"deleted": True}
        events = conn.execute(
            "SELECT sequence,event_type,payload FROM study_event WHERE run_id=%s ORDER BY sequence",
            (run["run_id"],),
        ).fetchall()
        models = conn.execute(
            "SELECT count(*) AS n,COALESCE(sum(reserved_tokens),0) AS tokens FROM study_model_call WHERE run_id=%s",
            (run["run_id"],),
        ).fetchone()
        reservations = conn.execute(
            "SELECT count(*) AS n FROM study_reservation WHERE run_id=%s AND kind='tool'",
            (run["run_id"],),
        ).fetchone()["n"]
        effects = {}
        for table in ("study_artifact", "study_feedback", "study_approval"):
            effects[table] = conn.execute(
                f"SELECT count(*) AS n FROM {table} WHERE run_id=%s", (run["run_id"],)
            ).fetchone()["n"]
        remote = conn.execute(
            "SELECT method,operation_key,count(*) AS n FROM eval_remote_call WHERE run_id=%s GROUP BY method,operation_key",
            (run["run_id"],),
        ).fetchall()
    retries = sum(e["event_type"] == "tool_retry_started" for e in events)
    return {
        "status": row["status"],
        "error_code": row["error_code"],
        "model_calls": row["model_calls"],
        "tool_calls": row["tool_calls"],
        "reserved_tokens": row["reserved_tokens"],
        "model_rows": models["n"],
        "journal_tokens": models["tokens"],
        "tool_reservations": reservations,
        "retry_charges": retries,
        "effects": effects,
        "events": events,
        "remote_calls": remote,
    }


def worker(args):
    import lecturelens_agent.study.runtime as runtime_module

    manifest = os.environ.get("STUDY_CRASH_MANIFEST")
    if manifest:
        identity = json.loads(Path(manifest).read_text().splitlines()[-1])
        if any(
            hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != digest
            for path, digest in identity["source_sha256"].items()
        ):
            raise RuntimeError("Candidate source changed during the matrix")
        if (
            hashlib.sha256(Path(test_study.__file__).read_bytes()).hexdigest()
            != identity["authority_fixture_sha256"]
        ):
            raise RuntimeError("Authority fixture changed during the matrix")
        if (
            hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
            != identity["driver_sha256"]
        ):
            raise RuntimeError("Matrix driver changed during the matrix")
    store = StudyStore(os.environ["AGENT_TEST_DATABASE_URL"])
    run = json.loads(Path(args.run).read_text())
    counters = collections.Counter()

    def hit(point):
        with Path(args.points).open("a") as out:
            out.write(point + "\n")
        if point == args.kill:
            os.kill(os.getpid(), signal.SIGKILL)

    def wrap(obj, name, prefix, key=None):
        original = getattr(obj, name)

        def called(*pos, **kw):
            part = key(*pos, **kw) if key else str(counters[prefix])
            counters[prefix] += 1
            hit(f"{prefix}:{part}:before")
            result = original(*pos, **kw)
            hit(f"{prefix}:{part}:after")
            return result

        setattr(obj, name, called)

    provider = MockProvider()
    for name in ("decide", "review", "feedback"):
        original = getattr(provider, name)

        def remote(*pos, _method=name, _original=original, **kw):
            identity = (telemetry._span.get() or {}).get("model_key") or hashlib.sha256(
                json.dumps([_method, pos[0]], sort_keys=True).encode()
            ).hexdigest()
            with store.connect() as conn:
                conn.execute(
                    "INSERT INTO eval_remote_call(run_id,method,operation_key) VALUES (%s,%s,%s)",
                    (run["run_id"], _method, identity),
                )
            return _original(*pos, **kw)

        setattr(provider, name, remote)
        wrap(provider, name, f"provider.{name}")
    authority = test_study.Authority()
    original_read = authority.read

    def read(scope, action="CHECK", **kwargs):
        counter = counters["authority." + action]
        counters["authority." + action] += 1
        hit(f"authority.{action}:{counter}:before")
        if action == args.fault:
            from lecturelens_agent.study.store import StudyError

            raise StudyError("MCP_TIMEOUT", 503)
        result = original_read(scope, action, **kwargs)
        hit(f"authority.{action}:{counter}:after")
        return result

    authority.read = read
    for name in ("claim", "reserve", "save_tool", "finish", "reserve_read_attempt"):
        wrap(store, name, "store." + name)
    for name in ("begin", "complete"):
        wrap(call_journal, name, "model_journal." + name)
    for name in ("pause", "publish"):
        wrap(approval, name, "approval." + name)
    for name in ("put", "put_writes", "delete_thread"):
        wrap(PostgresSaver, name, "checkpoint." + name)
    original_node = telemetry.traced_node

    def traced(store, run, token, name, function):
        def node(state):
            ordinal = counters["node." + name]
            counters["node." + name] += 1
            hit(f"node.{name}:{ordinal}:before")
            result = function(state)
            hit(f"node.{name}:{ordinal}:after")
            return result

        return original_node(store, run, token, name, node)

    telemetry.traced_node = runtime_module.traced_node = traced
    runtime = StudyRuntime(store, authority, provider, seconds=300)
    runtime.execute(run)
    if args.purge:
        runtime.purge_deleted()
    hit("worker.return:0:after")


def fresh(store, *, gate=False, feedback=False):
    scope = {"owner_id": 42, "course_id": "matrix-" + uuid.uuid4().hex, "revision": 1}
    session = store.command(
        StudyCommand(**scope, operation="CREATE_SESSION", request_key="session"), "mock"
    )["session_id"]
    scope["session_id"] = session
    result = store.command(
        StudyCommand(
            **scope,
            operation="START",
            request_key="practice",
            goal="Explain stopping conditions",
            approval_required=gate and not feedback,
        ),
        "mock",
    )
    run = next(r for r in store.candidates() if r["run_id"] == result["run"]["run_id"])
    if feedback:
        StudyRuntime(
            store, test_study.Authority(), MockProvider(), seconds=300
        ).execute(run)
        result = store.command(
            StudyCommand(**scope, run_id=run["run_id"], operation="READ"), "mock"
        )
        source = dict(
            **scope,
            run_id=run["run_id"],
            artifact_id=result["artifact"]["artifact_id"],
            question_index=0,
        )
        attempt = store.command(
            StudyCommand(
                **source,
                operation="SAVE_ATTEMPT",
                request_key="answer",
                expected_version=0,
                answer_text="A stopping condition is required.",
            ),
            "mock",
        )["attempt"]
        result = store.command(
            StudyCommand(
                **source,
                operation="START_FEEDBACK",
                request_key="feedback",
                attempt_id=attempt["attempt_id"],
                approval_required=gate,
            ),
            "mock",
        )
        run = next(
            r for r in store.candidates() if r["run_id"] == result["run"]["run_id"]
        )
    return run, scope


def process(run, path, *, kill="", points, fault="", purge=False):
    path.write_text(json.dumps(run, default=str))
    started = time.monotonic()
    result = subprocess.run(
        [
            sys.executable,
            __file__,
            "--worker",
            "--run",
            str(path),
            "--kill",
            kill,
            "--points",
            str(points),
            "--fault",
            fault,
            *(["--purge"] if purge else []),
        ],
        capture_output=True,
        check=False,
        timeout=45,
    )
    return result.returncode, round((time.monotonic() - started) * 1000, 3)


def resume(store, run, scope, path, points, decision="approve"):
    state = snapshot(store, run)
    if state["status"] == "awaiting_approval":
        store.command(
            StudyCommand(
                **scope,
                run_id=run["run_id"],
                operation="DECIDE_APPROVAL",
                request_key="decision",
                approval_decision=decision,
            ),
            "mock",
        )
    code, elapsed = process(run, path, points=points)
    state = snapshot(store, run)
    if state["status"] == "awaiting_approval":
        store.command(
            StudyCommand(
                **scope,
                run_id=run["run_id"],
                operation="DECIDE_APPROVAL",
                request_key="decision",
                approval_decision=decision,
            ),
            "mock",
        )
        code, extra = process(run, path, points=points)
        elapsed += extra
    return code, elapsed, snapshot(store, run)


def assertions(state, decision):
    events = state["events"]
    types = collections.Counter(e["event_type"] for e in events)
    checks = {
        "continuous_sequence": [e["sequence"] for e in events]
        == list(range(1, len(events) + 1)),
        "model_budget_once": state["model_calls"] == state["model_rows"],
        "model_budget_matches_control": state["model_calls"] == 4
        if state["status"] == "succeeded"
        else state["model_calls"] <= 4,
        "tokens_once": state["reserved_tokens"] == state["journal_tokens"],
        "tool_budget_once": state["tool_calls"]
        == state["tool_reservations"] + state["retry_charges"],
        "no_duplicate_provider_request": all(
            row["n"] == 1 for row in state["remote_calls"]
        ),
        "single_publication": types["artifact_created"] <= 1
        and types["feedback_created"] <= 1,
        "single_terminal": types["run_finished"] == 1,
        "bounded_attempts": all(
            1 <= e["payload"]["attempt"] <= 3
            for e in events
            if e["event_type"] == "read_attempt_reserved"
        ),
    }
    uncertain = state["error_code"] == "MODEL_OUTCOME_UNKNOWN"
    expected = "failed" if uncertain or decision == "reject" else "succeeded"
    checks["terminal_correct"] = state["status"] == expected
    checks["unpublished_failure"] = (
        state["status"] != "failed"
        or state["effects"]["study_artifact"] + state["effects"]["study_feedback"] == 0
    )
    return checks


def main(args):
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    if conninfo_to_dict(dsn)["dbname"] != "lecturelens_agent_test":
        raise ValueError("A separate lecturelens_agent_test database is required")
    os.environ["STUDY_FEEDBACK_ENABLED"] = "true"
    store = StudyStore(dsn)
    VectorStore(dsn).initialize()
    StudyRuntime(store, test_study.Authority(), MockProvider()).initialize()
    with store.connect() as conn:
        conn.execute(
            "CREATE TABLE IF NOT EXISTS eval_remote_call(run_id text,method text,operation_key text)"
        )
    if args.resume:
        if (
            not (args.output / "raw.jsonl").is_file()
            or (args.output / "summary.json").exists()
        ):
            raise ValueError(
                "Resume only an incomplete batch with retained raw records"
            )
    else:
        args.output.mkdir(parents=True, exist_ok=False)
    work = args.output / "work"
    work.mkdir(exist_ok=args.resume)
    rows = (
        [
            json.loads(line)
            for line in (args.output / "raw.jsonl").read_text().splitlines()
        ]
        if args.resume
        else []
    )
    completed = {(row["profile"], row["point"], row["trial"]) for row in rows}
    import importlib.metadata
    from datetime import datetime, timezone

    identity = {
        "started_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": sys.version,
        "versions": {
            name: importlib.metadata.version(name)
            for name in ("langgraph", "langgraph-checkpoint-postgres", "psycopg")
        },
        "source_sha256": {
            str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest()
            for p in (ROOT / "agent-service/src/lecturelens_agent/study").glob("*.py")
        },
        "authority_fixture_sha256": hashlib.sha256(
            Path(test_study.__file__).read_bytes()
        ).hexdigest(),
        "driver_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
    }
    with (args.output / "identities.jsonl").open("a") as out:
        out.write(json.dumps(identity) + "\n")
    os.environ["STUDY_CRASH_MANIFEST"] = str(
        (args.output / "identities.jsonl").resolve()
    )
    profiles = [
        ("practice", False, False),
        ("practice_approval", True, False),
        ("feedback_approval", True, True),
    ]
    for profile, gate, feedback in profiles:
        run, scope = fresh(store, gate=gate, feedback=feedback)
        capture = work / f"{profile}-capture.txt"
        code, _ = process(run, work / "run.json", points=capture)
        assert code == 0
        _, _, control = resume(
            store, run, scope, work / "run.json", work / "resume.txt"
        )
        assert control["status"] == "succeeded", control["error_code"]
        with (args.output / "controls.jsonl").open("a") as out:
            out.write(
                json.dumps(
                    {"profile": profile, "run_id": run["run_id"], "state": control},
                    default=str,
                )
                + "\n"
            )
        points = list(dict.fromkeys(capture.read_text().splitlines()))
        # Exercise publication after the authentic durable decision too.
        if gate:
            points += [
                p
                for p in (work / "resume.txt").read_text().splitlines()
                if p.startswith("approval.publish")
            ]
        points = list(
            dict.fromkeys(p for p in points if gate or p != "worker.return:0:after")
        )
        if args.smoke:
            points = [
                p
                for p in points
                if p.startswith(
                    (
                        "provider.decide",
                        "model_journal.complete:0",
                        "store.save_tool:2",
                        "approval.",
                    )
                )
            ]
        for point in points:
            for trial in range(args.trials):
                if (profile, point, trial + 1) in completed:
                    continue
                run, scope = fresh(store, gate=gate, feedback=feedback)
                path = work / "run.json"
                if point.startswith("approval.publish"):
                    process(run, path, points=work / "prep.txt")
                    store.command(
                        StudyCommand(
                            **scope,
                            run_id=run["run_id"],
                            operation="DECIDE_APPROVAL",
                            request_key="decision",
                            approval_decision="approve",
                        ),
                        "mock",
                    )
                code, _ = process(run, path, kill=point, points=work / "injected.txt")
                before = snapshot(store, run)
                decision = (
                    "reject"
                    if gate and point.startswith("approval.pause") and trial % 2
                    else "approve"
                )
                recovered_code, elapsed, state = resume(
                    store, run, scope, path, work / "recovered.txt", decision
                )
                checks = assertions(state, decision)
                checks["injection_reached"] = code == -signal.SIGKILL
                checks["restart_clean"] = recovered_code == 0
                row = {
                    "profile": profile,
                    "point": point,
                    "trial": trial + 1,
                    "run_id": run["run_id"],
                    "decision": decision,
                    "recovery_ms": elapsed,
                    "passed": all(checks.values()),
                    "checks": checks,
                    "before": {k: v for k, v in before.items() if k != "events"},
                    "after": state,
                }
                rows.append(row)
                with (args.output / "raw.jsonl").open("a") as out:
                    out.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
            print(
                profile,
                point,
                sum(r["passed"] for r in rows[-args.trials :]),
                "/",
                args.trials,
                flush=True,
            )
    if not args.smoke:
        from lecturelens_agent.contracts import SyncRequest

        for gate in (False, True):
            point = "worker.return:0:after" if gate else "authority.SEARCH:0:before"
            for lifecycle in ("cancel", "delete", "delete_checkpoint_crash"):
                for trial in range(args.trials):
                    run, scope = fresh(store, gate=gate)
                    code, _ = process(
                        run,
                        work / "run.json",
                        kill=point,
                        points=work / "lifecycle.txt",
                    )
                    before = snapshot(store, run)
                    checks = {"injection_reached": code == -signal.SIGKILL}
                    if lifecycle == "cancel":
                        store.command(
                            StudyCommand(
                                **scope, run_id=run["run_id"], operation="CANCEL"
                            ),
                            "mock",
                        )
                        _, elapsed = process(
                            run, work / "run.json", points=work / "lifecycle.txt"
                        )
                        after = snapshot(store, run)
                        checks.update(
                            {
                                "cancelled": after["status"] == "cancelled",
                                "budgets_unchanged": all(
                                    before[k] == after[k]
                                    for k in (
                                        "tool_calls",
                                        "model_calls",
                                        "reserved_tokens",
                                    )
                                ),
                                "remote_unchanged": before["remote_calls"]
                                == after["remote_calls"],
                                "no_publication": after["effects"]["study_artifact"]
                                == after["effects"]["study_feedback"]
                                == 0,
                            }
                        )
                    else:
                        VectorStore(dsn).delete(
                            SyncRequest(
                                request_id="delete",
                                owner_id=scope["owner_id"],
                                course_id=scope["course_id"],
                                revision=1,
                                sequence=1,
                                operation="DELETE",
                            ),
                            "matrix",
                        )
                        # Real Java would reject this tombstoned course; cleanup is exercised in a fresh worker.
                        store.command(
                            StudyCommand(
                                **scope, run_id=run["run_id"], operation="CANCEL"
                            ),
                            "mock",
                        )
                        if lifecycle == "delete_checkpoint_crash":
                            killed, _ = process(
                                run,
                                work / "run.json",
                                kill="checkpoint.delete_thread:0:after",
                                points=work / "lifecycle.txt",
                                purge=True,
                            )
                            checks["cleanup_injection_reached"] = (
                                killed == -signal.SIGKILL
                            )
                        _, elapsed = process(
                            run,
                            work / "run.json",
                            points=work / "lifecycle.txt",
                            purge=True,
                        )
                        with store.connect() as conn:
                            tables = [
                                "study_run",
                                "study_event",
                                "study_artifact",
                                "study_feedback",
                                "study_approval",
                                "study_reservation",
                                "study_model_call",
                            ]
                            remaining = {
                                t: conn.execute(
                                    f"SELECT count(*) AS n FROM {t} WHERE run_id=%s",
                                    (run["run_id"],),
                                ).fetchone()["n"]
                                for t in tables
                            }
                            remaining["study_session"] = conn.execute(
                                "SELECT count(*) AS n FROM study_session WHERE session_id=%s",
                                (run["session_id"],),
                            ).fetchone()["n"]
                            for t in (
                                "checkpoints",
                                "checkpoint_writes",
                                "checkpoint_blobs",
                            ):
                                remaining[t] = conn.execute(
                                    f"SELECT count(*) AS n FROM {t} WHERE thread_id=%s",
                                    (run["session_id"],),
                                ).fetchone()["n"]
                        checks["all_state_deleted"] = all(
                            n == 0 for n in remaining.values()
                        )
                        after = {
                            "status": "deleted",
                            "error_code": None,
                            "remaining": remaining,
                        }
                    row = {
                        "profile": "approval_lifecycle" if gate else "lifecycle",
                        "point": lifecycle + ":" + point,
                        "trial": trial + 1,
                        "run_id": run["run_id"],
                        "recovery_ms": elapsed,
                        "passed": all(checks.values()),
                        "checks": checks,
                        "after": after,
                    }
                    rows.append(row)
                    with (args.output / "raw.jsonl").open("a") as out:
                        out.write(json.dumps(row, default=str) + "\n")
        for trial in range(args.trials):
            run, scope = fresh(store)
            codes = []
            for _ in range(3):
                code, _ = process(
                    run,
                    work / "run.json",
                    kill="authority.SEARCH:0:before",
                    points=work / "retry-cap.txt",
                    fault="SEARCH",
                )
                codes.append(code)
            _, elapsed = process(
                run, work / "run.json", points=work / "retry-cap.txt", fault="SEARCH"
            )
            after = snapshot(store, run)
            checks = assertions(after, "approve")
            checks["terminal_correct"] = (
                after["status"] == "failed"
                and after["error_code"] == "READ_CHECKPOINT_REPLAY"
            )
            checks["three_injections"] = codes == [-signal.SIGKILL] * 3
            checks["persistent_cap"] = (
                after["tool_calls"] == 3 and after["model_calls"] == 1
            )
            row = {
                "profile": "retry_cap",
                "point": "SEARCH:three_crashes",
                "trial": trial + 1,
                "run_id": run["run_id"],
                "recovery_ms": elapsed,
                "passed": all(checks.values()),
                "checks": checks,
                "after": after,
            }
            rows.append(row)
            with (args.output / "raw.jsonl").open("a") as out:
                out.write(json.dumps(row, default=str) + "\n")
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["profile"], row["point"])].append(row)
    summary = []
    for (profile, point), group in grouped.items():
        times = sorted(r["recovery_ms"] for r in group)
        summary.append(
            {
                "profile": profile,
                "point": point,
                "n": len(group),
                "passed": sum(r["passed"] for r in group),
                "recovery_p50_ms": times[(len(times) - 1) // 2],
                "recovery_p95_ms": times[-1],
                "outcomes": dict(
                    collections.Counter(
                        r["after"]["error_code"] or r["after"]["status"] for r in group
                    )
                ),
            }
        )
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(
        json.dumps(
            {
                "n": len(rows),
                "passed": sum(r["passed"] for r in rows),
                "points": len(summary),
            }
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--smoke", action="store_true")
    parser.add_argument("--resume", action="store_true")
    parser.add_argument("--worker", action="store_true")
    parser.add_argument("--run")
    parser.add_argument("--kill", default="")
    parser.add_argument("--points")
    parser.add_argument("--fault", default="")
    parser.add_argument("--purge", action="store_true")
    args = parser.parse_args()
    worker(args) if args.worker else main(args)
