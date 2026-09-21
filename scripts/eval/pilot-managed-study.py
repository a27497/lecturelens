#!/usr/bin/env python3
"""Small real-provider development pilot using frozen personal routing in an isolated DB.

Reads the explicitly selected user's live configuration, never changes it. Only public
fixed Evidence leaves this machine. Raw artifacts are private, trials are never overwritten.
"""

import argparse
import importlib.util
import json
import os
import uuid
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver
from psycopg.conninfo import conninfo_to_dict

import lecturelens_agent
from lecturelens_agent.study.context import aliases_in
from lecturelens_agent.study.contracts import TOOLS, StudyCommand
from lecturelens_agent.study.models import ModelCommand, ModelRegistry, RegistryProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyStore

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location(
    "fixed_replay", Path(__file__).with_name("replay-study-quality.py")
)
replay = importlib.util.module_from_spec(spec)
spec.loader.exec_module(replay)


def pilot_cases(path, seeded=False):
    data = json.loads(path.read_text())
    cases = data["cases"]
    if not 1 <= len(cases) <= 6 or len({case["id"] for case in cases}) != len(cases):
        raise ValueError("Use one to six uniquely identified cases")
    if any(case.get("split") != "development" for case in cases):
        raise ValueError("Only development cases are allowed")
    if seeded:
        if len(cases) > 2:
            raise ValueError("Use at most two seeded repair cases")
        for case in cases:
            candidate = dict(case["candidate"])
            if candidate.pop("kind") != "practice":
                raise ValueError("Seed a practice candidate only")
            TOOLS["create_practice_set"][0].model_validate(candidate)
    return cases


class SeededRegistryProvider(RegistryProvider):
    """Development-only: deterministic search/draft, real review and subsequent decisions."""

    def __init__(self, registry, candidate, evidence):
        super().__init__(registry)
        self.candidate, self.evidence = candidate, evidence
        self.calls = []

    def for_run(self, run):
        return SeededRunProvider(super().for_run(run), self.candidate, self.evidence, self.calls)


class SeededRunProvider:
    mode = "real"

    def __init__(self, delegate, candidate, evidence, calls):
        self.delegate, self.candidate, self.evidence, self.calls = delegate, candidate, evidence, calls

    def identity(self, purpose):
        return self.delegate.identity(purpose)

    def decide(self, messages, timeout):
        context = json.loads(messages[-1]["content"])
        history = context.get("history", [])
        if not history:
            response = {"name": "search_course_evidence", "arguments": {"query": context["goal"][:500]}}
        elif len(history) == 1 and history[0]["tool"] == "search_course_evidence":
            visible = {
                (item["start_ms"], item["end_ms"]): item["evidence_id"] for item in context["evidence"]
            }
            mapping = {
                item["evidence_id"]: visible[(item["start_ms"], item["end_ms"])]
                for item in self.evidence
                if (item["start_ms"], item["end_ms"]) in visible
            }
            refs = set(self.candidate["evidence_ids"])
            for question in self.candidate["questions"]:
                refs.update(question["evidence_ids"])
            if not refs <= mapping.keys():
                raise ValueError("Seed references evidence absent from the actual tool observation")
            arguments = aliases_in(self.candidate, mapping)
            arguments.pop("kind")
            response = {"name": "create_practice_set", "arguments": arguments}
        else:
            return self._real_call("decision", messages, timeout)
        self.calls.append({"purpose": "decision", "seeded": True, "response": response})
        return response

    def review(self, messages, timeout):
        return self._real_call("review", messages, timeout)

    def _real_call(self, purpose, messages, timeout):
        client = getattr(self.delegate, "clients", {}).get(purpose)
        request = client._request if client is not None else None
        observer = getattr(client, "response_observer", None)

        def redacted(value):
            if isinstance(value, str):
                if client is not None and client.key:
                    return value.replace(client.key, "[REDACTED]").replace(
                        json.dumps(client.key)[1:-1], "[REDACTED]"
                    )
                return value
            if isinstance(value, dict):
                return {redacted(key): redacted(item) for key, item in value.items()}
            if isinstance(value, list):
                return [redacted(item) for item in value]
            return value

        record = {
            "purpose": purpose,
            "seeded": False,
            "messages": redacted(messages),
            "wire_responses": [],
            "raw_responses": [],
        }

        def recorded_request(*args, **kwargs):
            response = request(*args, **kwargs)
            # Preserve parsed tool arguments before semantic/schema validation can reject them.
            record["wire_responses"].append(redacted(response))
            return response

        self.calls.append(record)
        if client is not None:
            client._request = recorded_request
            client.response_observer = lambda raw: record["raw_responses"].append(
                redacted(raw.decode("utf-8", errors="replace"))
            )
        try:
            method = self.delegate.decide if purpose == "decision" else self.delegate.review
            response = method(messages, timeout)
        except Exception as error:  # noqa: BLE001 -- retain usage, never credentials or exception text
            record.update(
                status="failed",
                error_code=getattr(error, "code", "PILOT_CALL_FAILED"),
                usage=getattr(error, "usage", {}),
                diagnostics=redacted(getattr(error, "diagnostics", {})),
            )
            raise
        finally:
            if client is not None:
                client._request = request
                client.response_observer = observer
        record.update(status="ok", response=redacted(response), usage=response.get("usage", {}))
        return response


class RecordedRunProvider(SeededRunProvider):
    """Ordinary development runs: record every real decision; never inject a tool call."""

    def decide(self, messages, timeout):
        return self._real_call("decision", messages, timeout)


class RecordingRegistryProvider(RegistryProvider):
    def __init__(self, registry):
        super().__init__(registry)
        self.calls = []

    def for_run(self, run):
        return RecordedRunProvider(super().for_run(run), None, [], self.calls)


def write_private(path, value):
    with path.open("x") as out:
        json.dump(value, out, ensure_ascii=False, indent=2, default=str)
        out.write("\n")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--runtime-config", required=True, type=Path)
    parser.add_argument("--owner-id", required=True, type=int)
    parser.add_argument("--cases", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument(
        "--seeded-candidates",
        action="store_true",
        help="Development-only seeded drafts; does not evaluate autonomous generation",
    )
    parser.add_argument(
        "--decision-model",
        choices=["qwen3-max"],
        help="Explicit isolated experiment using the existing review connection for generation; never changes live routing",
    )
    args = parser.parse_args()
    os.umask(0o077)
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    if conninfo_to_dict(dsn).get("dbname") not in {"lecturelens_agent_test", "lecturelens_agent_pilot_test"}:
        raise ValueError("Use the separate test database")
    cases = pilot_cases(args.cases, args.seeded_candidates)
    args.output.mkdir(parents=True, exist_ok=True)
    package = Path(lecturelens_agent.__file__).resolve().parent
    if not package.is_relative_to(args.output.resolve() / "src"):
        raise ValueError("Run with PYTHONPATH pointing to output/src frozen source")
    source = json.loads((ROOT / "eval/study-v2/sources.json").read_text())
    evidence = replay.captions(source, ROOT / ".data/study-v2/lecture4.vtt")
    # Only the named owner is read. Credentials stay in memory or encrypted database columns.
    deployment = json.loads(args.runtime_config.read_text())
    os.environ.update(deployment)
    live = ModelRegistry(deployment["AGENT_DATABASE_URL"], deployment["AGENT_SERVICE_SECRET"])
    frozen = live.freeze(args.owner_id)
    if {role: cfg["model"] for role, cfg in frozen.items()} != {
        "decision": "qwen-plus",
        "review": "qwen3-max",
    }:
        raise ValueError("Selected model configuration changed; re-scope the pilot first")
    source_models = {role: cfg["model"] for role, cfg in frozen.items()}
    if args.decision_model is not None:
        frozen["decision"] = dict(frozen["review"])

    # Private test registry uses a fresh encryption key, unrelated to the live key.
    os.environ.pop("AGENT_MODEL_ENCRYPTION_KEY", None)
    registry = ModelRegistry(dsn, uuid.uuid4().hex + uuid.uuid4().hex)
    registry.initialize()
    owner = uuid.uuid4().int % 1_000_000_000 + 2_000_000_000
    bindings = {}
    identity = {
        "protocol": "seeded-draft-real-repair-development"
        if args.seeded_candidates
        else "managed-real-provider-development-fixed-evidence",
        "seeded_decisions_per_run": 2 if args.seeded_candidates else 0,
        "autonomous_generation_assessed": not args.seeded_candidates,
        "runtime_sha256": replay.digest(
            b"".join(
                str(p.relative_to(package)).encode() + p.read_bytes() for p in sorted(package.rglob("*.py"))
            )
        ),
        "runner_sha256": replay.digest(Path(__file__).read_bytes()),
        "dataset_sha256": replay.digest(args.cases.read_bytes()),
        "source_sha256": source["subtitle_sha256"],
        "evidence_sha256": replay.digest(json.dumps(evidence, sort_keys=True).encode()),
        "models": {
            role: {key: cfg[key] for key in ["model", "version", "base_url"]} for role, cfg in frozen.items()
        },
        "source_models": source_models,
        "isolated_decision_override": args.decision_model,
        "version_note": "Model versions identify source connections; isolated test connections start at version 1.",
        "deadline_seconds": 90,
        "max_model_calls_per_run": 6,
        "max_tool_calls_per_run": 8,
        "reserved_token_budget_per_run": 64000,
        "decision_output_limit": 900,
        "review_output_limit": 300,
        "practice_contract": TOOLS["create_practice_set"][0].__name__,
        "practice_contracts": {
            name: TOOLS[name][0].__name__
            for name in ("create_practice_set", "create_python_practice", "create_interval_practice", "create_sequence_practice")
            if name in TOOLS
        },
        "max_candidates_per_run": 2,
        "max_tool_format_repairs_per_run": 1,
        "temperature": 0.2,
        "bailian_enable_thinking": False,
        "tool_choice": "named for single tool; auto for multiple",
        "model_identity_limit": "Provider aliases may change; remote weights/hardware are not verifiable.",
        "full_l2_gate_assessed": False,
    }
    # Exclusively created before any model call; refuses retries over existing evidence.
    write_private(args.output / "identity.json", identity)
    write_private(args.output / "cases.json", json.loads(args.cases.read_text()))
    write_private(args.output / "evidence.json", evidence)
    try:
        for role, cfg in frozen.items():
            saved = registry.command(
                ModelCommand(
                    owner_id=owner,
                    operation="SAVE",
                    connection={
                        "name": "Pilot " + role,
                        "base_url": cfg["base_url"],
                        "api_key": live.unseal(cfg["credential"]),
                        "model_ids": [cfg["model"]],
                    },
                )
            )
            bindings[role] = {"connection_id": saved["connection_id"], "model": cfg["model"]}
        registry.command(ModelCommand(owner_id=owner, operation="ROUTE", bindings=bindings))
        store = StudyStore(dsn, model_resolver=registry.freeze)
        with (args.output / "results.jsonl").open("x") as output:
            for case in cases:
                scope = {"owner_id": owner, "course_id": "pilot-" + uuid.uuid4().hex, "revision": 1}
                provider = (
                    SeededRegistryProvider(registry, case["candidate"], evidence)
                    if args.seeded_candidates
                    else RecordingRegistryProvider(registry)
                )
                runtime = StudyRuntime(store, replay.FixedEvidence(scope, evidence), provider, seconds=90)
                runtime.initialize()
                session = store.command(
                    StudyCommand(**scope, operation="CREATE_SESSION", request_key="session"), "real"
                )["session_id"]
                scope["session_id"] = session
                run_id = store.command(
                    StudyCommand(**scope, operation="START", request_key=case["id"], goal=case["goal"]),
                    "real",
                )["run"]["run_id"]
                with store.connect() as conn:
                    run = conn.execute(
                        "SELECT r.*,s.owner_id,s.course_id,s.revision FROM study_run r JOIN study_session s USING(session_id) WHERE run_id=%s",
                        (run_id,),
                    ).fetchone()
                runtime.execute(run)
                response = store.command(StudyCommand(**scope, operation="READ"), "real")
                events = store.command(StudyCommand(**scope, operation="EVENTS"), "real")["events"]
                with store.connect() as conn:
                    artifact = conn.execute(
                        "SELECT content FROM study_artifact WHERE run_id=%s", (run_id,)
                    ).fetchone()
                    tools = conn.execute(
                        "SELECT * FROM study_tool_result WHERE run_id=%s ORDER BY call_id", (run_id,)
                    ).fetchall()
                with PostgresSaver.from_conn_string(dsn) as saver:
                    checkpoint = saver.get({"configurable": {"thread_id": session}})
                pending = (checkpoint or {}).get("channel_values", {}).get("pending")
                row = {
                    "identity": identity,
                    "case_id": case["id"],
                    "run": response["run"],
                    "artifact": artifact["content"] if artifact else None,
                    "evidence": evidence,
                    "events": events,
                    "tools": tools,
                    "provider_calls": provider.calls,
                    "pending_candidate": {key: pending[key] for key in ["name", "arguments"]}
                    if pending
                    and pending.get("name")
                    in {
                        "create_practice_set",
                        "create_python_practice",
                        "create_interval_practice",
                        "create_sequence_practice",
                        "report_insufficient_evidence",
                    }
                    else None,
                }
                row["elapsed_seconds"] = (
                    response["run"]["finished_at"] - response["run"]["created_at"]
                ).total_seconds()
                output.write(json.dumps(row, ensure_ascii=False, default=str) + "\n")
                output.flush()
                os.fsync(output.fileno())
                # Only clean this pilot's rows after its raw record is durable.
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
                            "seconds": round(row["elapsed_seconds"], 2),
                        },
                        ensure_ascii=False,
                    ),
                    flush=True,
                )
    finally:
        with registry.store.connect() as conn:
            conn.execute("DELETE FROM agent_model_routing WHERE owner_id=%s", (owner,))
            conn.execute("DELETE FROM agent_model_connection WHERE owner_id=%s", (owner,))


if __name__ == "__main__":
    main()
