#!/usr/bin/env python3
"""Generate synthetic real runtime Runs and keep them in an isolated temporary PG.

Unlike the frozen P0-1 runner, no Run/checkpoint cleanup is performed. Export only
public metadata, never replay detail or private provider messages. This fixture
uses an internal authority stub, not a live Java endpoint or real model.
"""

import argparse
import hashlib
import importlib.util
import json
import os
import time
import uuid
from pathlib import Path

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "p0_fault_provider", ROOT / "eval/tool-resilience-20261014/run.py"
)
FAULTS = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(FAULTS)
SCENARIOS = (
    "healthy",
    "unavailable_once",
    "integer_overflow",
    "unknown_tool",
    "illegal_call_shape",
)


class Authority:
    transport = "internal"

    def __init__(self, scenario):
        self.scenario, self.faults = scenario, 0

    def read(self, scope, action="CHECK", **arguments):
        if (
            self.scenario == "unavailable_once"
            and action == "SEARCH"
            and not self.faults
        ):
            self.faults += 1
            raise StudyError("MCP_AUTHORITY_UNAVAILABLE", 503)
        ids = arguments.get("evidence_ids", ["e1", "e2"])
        return {k: scope[k] for k in ("owner_id", "course_id", "revision")} | {
            "evidence": []
            if action == "CHECK"
            else [
                {
                    "evidence_id": key,
                    "text": "An algorithm needs a stopping condition.",
                    "start_ms": i * 1000,
                    "end_ms": (i + 1) * 1000,
                    "source_type": "SUBTITLE",
                }
                for i, key in enumerate(ids)
            ]
        }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=3)
    args = parser.parse_args()
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    if "127.0.0.1" not in dsn or "lecturelens_agent_test" != dsn.rsplit("/", 1)[-1]:
        parser.error("Use a dedicated temporary localhost PostgreSQL test container")
    if args.samples < 1:
        parser.error("samples must be positive")
    store = StudyStore(dsn)
    runtime = StudyRuntime(store, Authority("healthy"), FAULTS.FaultProvider("healthy"))
    runtime.initialize()
    with store.connect() as conn:
        if conn.execute("SELECT count(*) AS n FROM study_run").fetchone()["n"]:
            parser.error(
                "Refuse to mix with existing Runs; use a new temporary database"
            )
    fixture_hash = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    ids = []
    with args.output.open("x") as output:
        for scenario in SCENARIOS:
            runtime.authority.authority = Authority(scenario)
            for trial in range(args.samples):
                runtime.authority.authority = Authority(scenario)
                runtime.provider = FAULTS.FaultProvider(scenario)
                scope = {
                    "owner_id": 42,
                    "course_id": "metrics-synthetic-" + uuid.uuid4().hex,
                    "revision": 1,
                }
                scope["session_id"] = store.command(
                    StudyCommand(
                        **scope, operation="CREATE_SESSION", request_key="session"
                    ),
                    "mock",
                )["session_id"]
                run_id = store.command(
                    StudyCommand(
                        **scope,
                        operation="START",
                        request_key="run",
                        goal="解释停止条件并出两道题",
                    ),
                    "mock",
                )["run"]["run_id"]
                run = next(r for r in store.candidates() if r["run_id"] == run_id)
                started = time.monotonic()
                runtime.execute(run)
                elapsed_ms = round((time.monotonic() - started) * 1000, 3)
                result = store.command(StudyCommand(**scope, operation="READ"), "mock")
                events = store.command(
                    StudyCommand(**scope, operation="EVENTS"), "mock"
                )["events"]
                output.write(
                    json.dumps(
                        {
                            "label": "persisted-runtime",
                            "scenario": scenario,
                            "trial": trial,
                            "fixture_sha256": fixture_hash,
                            "run": result["run"],
                            "elapsed_ms": elapsed_ms,
                            "artifact_kind": (result.get("artifact") or {}).get("kind"),
                            "public_events": events,
                        },
                        ensure_ascii=False,
                        default=str,
                    )
                    + "\n"
                )
                ids.append(run_id)
    with store.connect() as conn:
        count = conn.execute(
            "SELECT count(*) AS n FROM study_run WHERE run_id=ANY(%s)", (ids,)
        ).fetchone()["n"]
        event_count = conn.execute(
            "SELECT count(*) AS n FROM study_event WHERE run_id=ANY(%s)", (ids,)
        ).fetchone()["n"]
    assert count == len(SCENARIOS) * args.samples
    print(
        json.dumps(
            {
                "retained_runs": count,
                "retained_events": event_count,
                "scenarios": SCENARIOS,
                "samples_per_scenario": args.samples,
                "run_ids": ids,
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
