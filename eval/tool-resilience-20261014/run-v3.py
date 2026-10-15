"""Repeatable local HTTP -> official MCP -> LangGraph/PostgreSQL fault trials.

Run once with archived baseline sources and once with candidate sources on
PYTHONPATH. All course content is synthetic; no provider or private data needed.
"""
import argparse
import hashlib
import json
import logging
import os
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver

from lecturelens_agent.course_mcp.client import McpEvidenceAuthority
from lecturelens_agent.study.authority import AUTHORITY_PATH, signature
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import MockProvider, ModelResponseError
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyStore

SCENARIOS = ["healthy", "timeout_once", "timeout_persistent", "unavailable_once", "unavailable_persistent",
             "check_unavailable_persistent", "malformed_response", "negative_parameter", "reversed_window",
             "oversized_parameter", "integer_overflow", "unknown_tool", "illegal_call_shape", "protocol_once", "protocol_persistent"]
SECRET = "synthetic-local-fixture-secret-32-bytes"


class FaultProvider(MockProvider):
    def __init__(self, scenario):
        self.scenario, self.decisions = scenario, 0

    def decide(self, messages, timeout):
        self.decisions += 1
        if self.scenario == "protocol_persistent" or self.scenario == "protocol_once" and self.decisions == 1:
            raise ModelResponseError("MODEL_TOOL_CONTRACT")
        if self.decisions == 1:
            if self.scenario == "negative_parameter":
                return {"name": "search_course_evidence", "arguments": {"query": "stop", "start_ms": -1, "end_ms": 2}}
            if self.scenario == "reversed_window":
                return {"name": "search_course_evidence", "arguments": {"query": "stop", "start_ms": 2, "end_ms": 1}}
            if self.scenario == "oversized_parameter":
                return {"name": "search_course_evidence", "arguments": {"query": "x" * 501}}
            if self.scenario == "integer_overflow":
                return {"name": "search_course_evidence", "arguments": {"query": "stop", "start_ms": 0, "end_ms": 2**63}}
            if self.scenario == "unknown_tool":
                return {"name": "publish_untrusted_answer", "arguments": {}}
            if self.scenario == "illegal_call_shape":
                return {"calls": [17]}
        if messages[-1]["role"] == "user" and "NO tools" in messages[-1]["content"]:
            messages = messages[:-1]  # MockProvider consumes JSON context, not the repair prose.
        return super().decide(messages, timeout)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--scenarios", nargs="+", default=SCENARIOS)
    args = parser.parse_args()
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    if "fault_test" not in dsn.rsplit("/", 1)[-1]:
        raise SystemExit("Use a dedicated fault_test PostgreSQL database")
    logging.getLogger("lecturelens_agent.study.runtime").setLevel(logging.ERROR)
    state = {"scenario": "healthy", "seen": [], "faults": 0}

    class Java(BaseHTTPRequestHandler):
        def do_POST(self):
            raw = self.rfile.read(int(self.headers["Content-Length"]))
            request = json.loads(raw)
            ts = self.headers.get("X-LectureLens-Timestamp", "0")
            valid = self.headers.get("X-LectureLens-Signature") == signature(SECRET, ts, raw, AUTHORITY_PATH)
            scenario = state["scenario"]
            fault_action = "CHECK" if scenario == "check_unavailable_persistent" else "SEARCH"
            fault_scenario = scenario.startswith(("timeout", "unavailable")) or scenario in {
                "check_unavailable_persistent", "malformed_response"}
            fault = fault_scenario and request["action"] == fault_action and ("persistent" in scenario or state["faults"] == 0)
            state["seen"].append({"action": request["action"], "fault": bool(fault and scenario != "healthy")})
            if fault:
                state["faults"] += 1
            status = 200 if valid else 403
            result = {k: request[k] for k in ("owner_id", "course_id", "revision")}
            ids = request.get("evidence_ids", ["e1", "e2"])
            result["evidence"] = [] if request["action"] == "CHECK" else [
                {"evidence_id": key, "text": "An algorithm needs a stopping condition.",
                 "start_ms": i * 1000, "end_ms": (i + 1) * 1000, "source_type": "SUBTITLE"}
                for i, key in enumerate(ids)]
            if fault and scenario.startswith("timeout"):
                time.sleep(1.1)  # exceeds the actual MCP client's one-second deadline
            if fault and "unavailable" in scenario:
                status = 503
            if fault and scenario == "malformed_response":
                result["evidence"] = "PRIVATE malformed payload"
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            try:
                self.wfile.write(json.dumps({"data": result}).encode())
            except BrokenPipeError:
                pass

        def log_message(self, *_):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Java)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    store = StudyStore(dsn)
    client_events = []
    client = McpEvidenceAuthority(f"http://127.0.0.1:{server.server_port}", SECRET,
                                 timeout=1, observer=client_events.append)
    runtime = StudyRuntime(store, client, MockProvider())
    runtime.initialize()
    import lecturelens_agent.study.runtime as source
    source_root = Path(source.__file__).parents[1]
    identity = hashlib.sha256()
    for file in sorted(source_root.rglob("*.py")):
        identity.update(str(file.relative_to(source_root)).encode())
        identity.update(file.read_bytes())
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        with args.output.open("w") as out:
            for trial in range(args.samples):
                for scenario in args.scenarios:
                    state.update(scenario=scenario, seen=[], faults=0)
                    client_events.clear()
                    runtime.provider = FaultProvider(scenario)
                    scope = {"owner_id": 42, "course_id": "fault-" + uuid.uuid4().hex, "revision": 1}
                    scope["session_id"] = store.command(StudyCommand(**scope, operation="CREATE_SESSION",
                                                                       request_key="session"), "mock")["session_id"]
                    run_id = store.command(StudyCommand(**scope, operation="START", request_key="run",
                                                        goal="解释停止条件并出两道题"), "mock")["run"]["run_id"]
                    run = next(r for r in store.candidates() if r["run_id"] == run_id)
                    started = time.monotonic()
                    runtime.execute(run)
                    elapsed = (time.monotonic() - started) * 1000
                    result = store.command(StudyCommand(**scope, operation="READ"), "mock")
                    events = store.command(StudyCommand(**scope, operation="EVENTS"), "mock")["events"]
                    artifact = result.get("artifact")
                    record = {"label": args.label, "source_sha256": identity.hexdigest(), "fixture_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(), "trial": trial,
                              "scenario": scenario, "run_id": run_id, "elapsed_ms": round(elapsed, 3),
                              "run": result["run"], "artifact_kind": artifact.get("kind") if artifact else None,
                              "public_events": events, "mcp_events": list(client_events),
                              "http_calls": list(state["seen"]), "injected_faults": state["faults"]}
                    out.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")
                    out.flush()
                    with PostgresSaver.from_conn_string(dsn) as saver:
                        saver.delete_thread(scope["session_id"])
                    with store.connect() as conn:
                        conn.execute("DELETE FROM study_run WHERE run_id=%s", (run_id,))
                        conn.execute("DELETE FROM study_session WHERE session_id=%s", (scope["session_id"],))
                print(f"{args.label}: trial {trial + 1}/{args.samples}", flush=True)
    finally:
        client.close()
        server.shutdown()
        server.server_close()


if __name__ == "__main__":
    main()
