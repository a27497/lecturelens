#!/usr/bin/env python3
"""Repeated approval decisions after SIGKILL before/after waiting and publication."""

import argparse
import collections
import importlib.util
import json
import os
import signal
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "crash_matrix", Path(__file__).with_name("check-study-crash-matrix.py")
)
MATRIX = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MATRIX)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=3)
    args = parser.parse_args()
    os.environ["STUDY_FEEDBACK_ENABLED"] = "true"
    store = MATRIX.StudyStore(os.environ["AGENT_TEST_DATABASE_URL"])
    if MATRIX.conninfo_to_dict(store.dsn)["dbname"] != "lecturelens_agent_test":
        raise ValueError("Separate PostgreSQL test database required")
    with store.connect() as conn:
        schema = conn.execute(
            "SELECT to_regclass('study_run') AS run, "
            "to_regclass('checkpoints') AS checkpoints"
        ).fetchone()
        if not schema["run"] or not schema["checkpoints"]:
            raise ValueError(
                "Evaluation schema missing: first run check-study-crash-matrix.py "
                "--smoke --trials 1 --output NEW_DIRECTORY on this test database"
            )
        # This audit table belongs to the evaluator, not the production schema.
        conn.execute(
            "CREATE TABLE IF NOT EXISTS eval_remote_call"
            "(run_id text,method text,operation_key text)"
        )
    args.output.mkdir(parents=True, exist_ok=False)
    work = args.output / "work"
    work.mkdir()
    rows = []
    for feedback in (False, True):
        for decision in ("approve", "edit", "reject"):
            for boundary in ("waiting", "decision_committed", "publication_committed"):
                for trial in range(args.trials):
                    run, scope = MATRIX.fresh(store, gate=True, feedback=feedback)
                    path, points = work / "run.json", work / "points.txt"
                    code, _ = MATRIX.process(
                        run,
                        path,
                        points=points,
                        kill="worker.return:0:after" if boundary == "waiting" else "",
                    )
                    waiting = MATRIX.snapshot(store, run)
                    assert waiting["status"] == "awaiting_approval"
                    checks = {
                        "unpublished_while_waiting": waiting["effects"][
                            "study_artifact"
                        ]
                        == waiting["effects"]["study_feedback"]
                        == 0
                    }
                    if boundary == "waiting":
                        checks["injection_reached"] = code == -signal.SIGKILL
                    command = MATRIX.StudyCommand(
                        **scope,
                        run_id=run["run_id"],
                        operation="DECIDE_APPROVAL",
                        request_key="decision",
                        approval_decision=decision,
                        approval_edit="Human publication edit for recovery test."
                        if decision == "edit"
                        else None,
                    )
                    started = time.monotonic()
                    store.command(command, "mock")
                    store.command(command, "mock")
                    if boundary != "waiting":
                        code, _ = MATRIX.process(
                            run,
                            path,
                            points=points,
                            kill="approval.publish:0:before"
                            if boundary == "decision_committed"
                            else "approval.publish:0:after",
                        )
                        checks["injection_reached"] = code == -signal.SIGKILL
                        started = time.monotonic()
                    code, _ = MATRIX.process(run, path, points=points)
                    elapsed = round((time.monotonic() - started) * 1000, 3)
                    final = MATRIX.snapshot(store, run)
                    checks.update(MATRIX.assertions(final, decision))
                    checks["clean_restart"] = code == 0
                    checks["budgets_unchanged"] = all(
                        final[k] == waiting[k]
                        for k in ("model_calls", "tool_calls", "reserved_tokens")
                    )
                    checks["no_repeated_provider"] = (
                        final["remote_calls"] == waiting["remote_calls"]
                    )
                    checks["decision_once"] = (
                        sum(
                            e["event_type"] == "approval_decided"
                            for e in final["events"]
                        )
                        == 1
                    )
                    row = {
                        "kind": "feedback" if feedback else "practice",
                        "decision": decision,
                        "point": "termination_committed"
                        if decision == "reject" and boundary == "publication_committed"
                        else boundary,
                        "trial": trial + 1,
                        "run_id": run["run_id"],
                        "passed": all(checks.values()),
                        "checks": checks,
                        "recovery_ms": elapsed,
                        "after": final,
                    }
                    rows.append(row)
                    with (args.output / "raw.jsonl").open("a") as out:
                        out.write(json.dumps(row, default=str) + "\n")
                print(
                    "feedback" if feedback else "practice",
                    decision,
                    boundary,
                    flush=True,
                )
    grouped = collections.defaultdict(list)
    for row in rows:
        grouped[(row["kind"], row["decision"], row["point"])].append(row)
    summary = []
    for (kind, decision, point), group in grouped.items():
        values = sorted(r["recovery_ms"] for r in group)
        summary.append(
            {
                "kind": kind,
                "decision": decision,
                "point": point,
                "n": len(group),
                "passed": sum(r["passed"] for r in group),
                "recovery_p50_ms": values[(len(values) - 1) // 2],
                "recovery_p95_ms": values[-1],
            }
        )
    (args.output / "summary.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps({"n": len(rows), "passed": sum(r["passed"] for r in rows)}))


if __name__ == "__main__":
    main()
