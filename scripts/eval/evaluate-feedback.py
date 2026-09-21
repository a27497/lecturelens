#!/usr/bin/env python3
"""Bounded real-model feedback replay, with immutable inputs and an aggregate call ledger.

Seeds already-reviewed practice artifacts and synthetic learner answers; only feedback decisions
are autonomous. Fixed recorded Evidence is not a fresh Java ingestion/authority acceptance test.
"""

import argparse
import fcntl
import hashlib
import json
import os
import time
import uuid
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.conninfo import conninfo_to_dict

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.models import ModelCommand, ModelRegistry, RegistryProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore

ROOT = Path(__file__).resolve().parents[2]


def digest_source():
    digest = hashlib.sha256()
    root = ROOT / "agent-service/src"
    for path in sorted((root / "lecturelens_agent").rglob("*.py")):
        digest.update(str(path.relative_to(root)).encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def reserve_call(ledger, case_id, review, limit=84):
    with ledger.open("a+") as out:
        fcntl.flock(out, fcntl.LOCK_EX)
        out.seek(0)
        count = sum(1 for line in out if line.strip())
        if limit is not None and count >= limit:
            raise StudyError("MODEL_EVALUATION_CALL_LIMIT")
        out.write(
            json.dumps(
                {
                    "ordinal": count + 1,
                    "case_id": case_id,
                    "purpose": "review" if review else "decision",
                    "at": time.time(),
                }
            )
            + "\n"
        )
        out.flush()
        os.fsync(out.fileno())


class FixedEvidence:
    def __init__(self, scope, evidence):
        self.scope, self.evidence = scope, evidence

    def read(self, scope, action="CHECK", **args):
        if any(scope.get(key) != value for key, value in self.scope.items()):
            raise StudyError("EVIDENCE_SCOPE_MISMATCH")
        if action == "CHECK":
            selected = []
        elif action == "READ":
            wanted = set(args["evidence_ids"])
            selected = [item for item in self.evidence if item["evidence_id"] in wanted]
            if len(selected) != len(wanted):
                raise StudyError("FEEDBACK_CITATION_MISMATCH")
        elif action == "WINDOW":
            anchor = next((e for e in self.evidence if e["evidence_id"] == args["evidence_id"]), None)
            if anchor is None:
                raise StudyError("FEEDBACK_CITATION_MISMATCH")
            ordered = sorted(
                [e for e in self.evidence if e["source_type"] == anchor["source_type"]],
                key=lambda e: (e["start_ms"], e["end_ms"]),
            )
            position = next(
                (i for i, item in enumerate(ordered) if item["evidence_id"] == args["evidence_id"]), None
            )
            if position is None:
                raise StudyError("FEEDBACK_CITATION_MISMATCH")
            selected = ordered[max(0, position - 1) : position + 2]
        else:
            raise StudyError("UNEXPECTED_EVALUATION_TOOL")
        return self.scope | {"evidence": selected}


class CountedProvider(RegistryProvider):
    def __init__(self, registry, ledger, case_id, call_limit=84):
        super().__init__(registry)
        self.ledger, self.case_id = ledger, case_id
        self.call_limit = call_limit
        self.responses = []

    def for_run(self, run):
        delegate = super().for_run(run)
        request = delegate.feedback

        def feedback(messages, schemas, timeout, *, review=False):
            reserve_call(self.ledger, self.case_id, review, self.call_limit)
            client = delegate.clients["review" if review else "decision"]

            def observe(raw):
                body = raw.decode("utf-8", errors="replace")
                if client.key:
                    body = body.replace(client.key, "[REDACTED]").replace(
                        json.dumps(client.key)[1:-1], "[REDACTED]"
                    )
                self.responses.append({"purpose": "review" if review else "decision", "body": body})

            client.response_observer = observe
            return request(messages, schemas, timeout, review=review)

        delegate.feedback = feedback
        return delegate


def validate_cases(data):
    cases = data["cases"]
    phase = data["phase"]
    limit = 6 if phase == "development" else 8 if phase in {"holdout", "regression"} else 0
    if not 1 <= len(cases) <= limit or len({c["id"] for c in cases}) != len(cases):
        raise ValueError("Invalid bounded evaluation cases")
    for case in cases:
        if not case["learner_answer"].strip() or len(case["learner_answer"]) > 4000:
            raise ValueError("Use a nonempty synthetic learner answer")
        ids = {item["evidence_id"] for item in case["evidence"]}
        if not set(case["question"]["evidence_ids"]) <= ids or len(case["question"]["evidence_ids"]) > 8:
            raise ValueError("Question sources absent from frozen evidence")
    return cases


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-config", type=Path, required=True)
    parser.add_argument("--owner-id", type=int, required=True)
    parser.add_argument("--cases", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--ledger", type=Path, required=True)
    parser.add_argument("--frozen-sha", required=True)
    parser.add_argument(
        "--call-limit",
        type=int,
        default=84,
        help="Aggregate ledger cap; 0 only with explicit unlimited authorization",
    )
    args = parser.parse_args()
    if args.call_limit < 0:
        parser.error("call-limit must be nonnegative")
    call_limit = args.call_limit or None
    os.umask(0o077)
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    if conninfo_to_dict(dsn).get("dbname") not in {"lecturelens_agent_test", "lecturelens_agent_pilot_test"}:
        raise ValueError("Use an isolated test database")
    source_sha = digest_source()
    if source_sha != args.frozen_sha:
        raise ValueError("Source changed since freezing")
    data = json.loads(args.cases.read_text())
    cases = validate_cases(data)
    prior_calls = len(args.ledger.read_text().splitlines()) if args.ledger.exists() else 0
    # Four calls cover read, independent course basis, draft and review. Repairs count against
    # the persistent aggregate cap; exhaustion remains a recorded failed trial.
    if call_limit is not None and prior_calls + 4 * len(cases) > call_limit:
        raise ValueError("Insufficient remaining call authorization for this queue")
    args.output.mkdir(parents=True, exist_ok=False)
    deployment = json.loads(args.runtime_config.read_text())
    if conninfo_to_dict(deployment["AGENT_DATABASE_URL"]) == conninfo_to_dict(dsn):
        raise ValueError("Source configuration and evaluation databases must differ")
    for key in ("AGENT_MODEL_ENCRYPTION_KEY", "AGENT_MODEL_ALLOWED_ORIGINS"):
        if deployment.get(key):
            os.environ[key] = deployment[key]
    live = ModelRegistry(deployment["AGENT_DATABASE_URL"], deployment["AGENT_SERVICE_SECRET"])
    original = live.freeze(args.owner_id)
    if original["review"]["model"] != "qwen3-max":
        raise ValueError("Authorized review model changed")
    frozen = {role: dict(original["review"]) for role in ("decision", "review")}
    os.environ.pop("AGENT_MODEL_ENCRYPTION_KEY", None)
    os.environ["STUDY_FEEDBACK_ENABLED"] = "true"
    registry = ModelRegistry(dsn, uuid.uuid4().hex + uuid.uuid4().hex)
    registry.initialize()
    owner = uuid.uuid4().int % 1_000_000_000 + 2_000_000_000
    identity = {
        "source_sha256": source_sha,
        "dataset_sha256": hashlib.sha256(args.cases.read_bytes()).hexdigest(),
        "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "models": {
            role: {key: cfg[key] for key in ("model", "version", "base_url")} for role, cfg in frozen.items()
        },
        "model_identity_limit": "Remote aliases, not verifiable weights or hardware",
        "phase": data["phase"],
        "cases": len(cases),
        "call_cap_all_queues": call_limit,
        "budgets": {
            "model_calls_per_run": 6,
            "tools_per_run": 8,
            "reserved_tokens_per_run": 64000,
            "deadline_seconds": 90,
        },
        "scope": "Known-course recorded evidence; seeded reviewed practice and synthetic learner answers; autonomous feedback only",
    }
    (args.output / "identity.json").write_text(json.dumps(identity, indent=2) + "\n")
    (args.output / "cases.json").write_bytes(args.cases.read_bytes())
    bindings = {}
    try:
        for role, cfg in frozen.items():
            saved = registry.command(
                ModelCommand(
                    owner_id=owner,
                    operation="SAVE",
                    connection={
                        "name": "Feedback evaluation " + role,
                        "base_url": cfg["base_url"],
                        "api_key": live.unseal(cfg["credential"]),
                        "model_ids": [cfg["model"]],
                    },
                )
            )
            bindings[role] = {"connection_id": saved["connection_id"], "model": cfg["model"]}
        registry.command(ModelCommand(owner_id=owner, operation="ROUTE", bindings=bindings))
        store = StudyStore(dsn, model_resolver=registry.freeze)
        with (args.output / "trials.jsonl").open("x") as out:
            for case in cases:
                if digest_source() != source_sha:
                    raise ValueError("Candidate changed mid-queue")
                scope = {"owner_id": owner, "course_id": "feedback-eval-" + uuid.uuid4().hex, "revision": 1}
                runtime = StudyRuntime(
                    store,
                    FixedEvidence(scope, case["evidence"]),
                    CountedProvider(registry, args.ledger, case["id"], call_limit),
                )
                runtime.initialize()
                session = store.command(
                    StudyCommand(**scope, operation="CREATE_SESSION", request_key="session"), "real"
                )["session_id"]
                command_scope = scope | {"session_id": session}
                parent = store.command(
                    StudyCommand(
                        **command_scope,
                        operation="START",
                        request_key="seed-practice",
                        goal="Frozen reviewed practice for feedback evaluation",
                    ),
                    "real",
                )["run"]["run_id"]
                token = uuid.uuid4().hex
                store.claim(parent, token, 90)
                artifact = {
                    "kind": "practice",
                    "title": "Frozen feedback evaluation practice",
                    "explanation": "Previously reviewed course-grounded exercise.",
                    "revision": 1,
                    "mode": "real",
                    "questions": [case["question"]],
                    "evidence_ids": case["question"]["evidence_ids"],
                    "citations": case["evidence"],
                }
                store.save_tool(parent, token, "seed", "evaluation_seed", {}, {}, artifact=artifact)
                store.finish(parent, token, "succeeded")
                public = store.command(StudyCommand(**command_scope, operation="READ", run_id=parent), "real")
                command_scope |= {
                    "run_id": parent,
                    "artifact_id": public["artifact"]["artifact_id"],
                    "question_index": 0,
                }
                attempt = store.command(
                    StudyCommand(
                        **command_scope,
                        operation="SAVE_ATTEMPT",
                        request_key="synthetic-answer",
                        expected_version=0,
                        answer_text=case["learner_answer"],
                    ),
                    "real",
                )["attempt"]
                response = store.command(
                    StudyCommand(
                        **command_scope,
                        operation="START_FEEDBACK",
                        request_key=case["id"],
                        attempt_id=attempt["attempt_id"],
                    ),
                    "real",
                )
                feedback_id = response["run"]["run_id"]
                run = next(row for row in store.candidates() if row["run_id"] == feedback_id)
                runtime.execute(run)
                read_scope = command_scope | {"run_id": feedback_id}
                response = store.command(StudyCommand(**read_scope, operation="READ"), "real")
                events = store.command(StudyCommand(**read_scope, operation="EVENTS"), "real")["events"]
                with store.connect() as conn:
                    tools = conn.execute(
                        "SELECT call_id,tool_name,arguments,result FROM study_tool_result WHERE run_id=%s ORDER BY call_id",
                        (feedback_id,),
                    ).fetchall()
                with PostgresSaver.from_conn_string(dsn) as saver:
                    checkpoint = saver.get({"configurable": {"thread_id": session}})
                elapsed = (response["run"]["finished_at"] - response["run"]["created_at"]).total_seconds()
                record = {
                    "case_id": case["id"],
                    "identity": identity,
                    "run": response["run"],
                    "feedback": response["feedback"],
                    "events": events,
                    "tools": tools,
                    "provider_responses": runtime.provider.responses,
                    "pending": (checkpoint or {}).get("channel_values", {}).get("pending"),
                    "elapsed_seconds": elapsed,
                }
                out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                out.flush()
                os.fsync(out.fileno())
                # Cleanup only this session, after the entire private audit record is durable.
                with PostgresSaver.from_conn_string(dsn) as saver:
                    saver.delete_thread(session)
                with store.connect() as conn:
                    conn.execute("DELETE FROM study_run WHERE session_id=%s", (session,))
                    conn.execute("DELETE FROM study_session WHERE session_id=%s", (session,))
                print(
                    json.dumps(
                        {
                            "case": case["id"],
                            "status": response["run"]["status"],
                            "error": response["run"]["error_code"],
                            "seconds": round(elapsed, 2),
                        }
                    ),
                    flush=True,
                )
        if live.freeze(args.owner_id) != original:
            raise ValueError("Live source configuration changed during evaluation")
    finally:
        with registry.store.connect() as conn:
            conn.execute("DELETE FROM agent_model_routing WHERE owner_id=%s", (owner,))
            conn.execute("DELETE FROM agent_model_connection WHERE owner_id=%s", (owner,))


if __name__ == "__main__":
    main()
