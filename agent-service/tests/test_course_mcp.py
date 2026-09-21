import hmac
import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest
import test_study
import test_study_attempts
import test_study_feedback
from mcp import StdioServerParameters

from lecturelens_agent.course_mcp.client import McpEvidenceAuthority
from lecturelens_agent.study.authority import AUTHORITY_PATH, EvidenceAuthority, course_authority, signature
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError
from lecturelens_agent.study.telemetry import TracedAuthority
from lecturelens_agent.study.trace import classify

setup = test_study.setup
practice = test_study_attempts.practice
feedback = test_study_feedback.feedback
SECRET = "test-course-mcp-java-secret-32-bytes"


@pytest.fixture
def java_fixture(setup):
    """HTTP boundary fixture; real Java acceptance is separately retained in eval/."""
    _, authority, _, scope = setup
    state = {
        "owner_id": scope["owner_id"],
        "course_id": scope["course_id"],
        "revision": scope["revision"],
        "deleted": False,
        "seen": [],
        "delay": 0,
        "entered": threading.Event(),
        "after_read": None,
    }

    class Java(BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers["Content-Length"]))
            request = json.loads(body)
            state["seen"].append(request)
            timestamp = self.headers.get("X-LectureLens-Timestamp", "0")
            signed = self.headers.get("X-LectureLens-Signature", "")
            valid = abs(time.time() - int(timestamp)) <= 60 and hmac.compare_digest(
                signed, signature(SECRET, timestamp, body, AUTHORITY_PATH)
            )
            if not valid:
                status, result = 401, {}
            elif state["deleted"] or any(
                request[k] != state[k] for k in ("owner_id", "course_id", "revision")
            ):
                status, result = 409, {}
            else:
                try:
                    state["entered"].set()
                    if request["action"] == "SEARCH":
                        state["search_entered"].set()
                        time.sleep(state["delay"])
                    result = authority.read(
                        request,
                        request["action"],
                        **{
                            k: v
                            for k, v in request.items()
                            if k not in {"owner_id", "course_id", "revision", "action"}
                        },
                    )
                    if state["after_read"]:
                        state["after_read"](request)
                    status = 409 if state["deleted"] or state["revision"] != request["revision"] else 200
                except StudyError:
                    status, result = 409, {}
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
    state["search_entered"] = threading.Event()
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{server.server_port}", state
    server.shutdown()
    server.server_close()


@pytest.fixture
def mcp_setup(setup, java_fixture):
    url, _ = java_fixture
    client = McpEvidenceAuthority(url, SECRET)
    setup[2].authority = TracedAuthority(client)
    yield setup
    client.close()


def test_actual_stdio_discovery_and_internal_contract_parity(setup, java_fixture):
    url, state = java_fixture
    events = []
    mcp, internal = McpEvidenceAuthority(url, SECRET, observer=events.append), EvidenceAuthority(url, SECRET)
    try:
        for action, args in [
            ("CHECK", {}),
            ("SEARCH", {"query": "stopping condition"}),
            ("SEARCH", {"query": "stop", "start_ms": 0, "end_ms": 2000}),
            ("READ", {"evidence_ids": ["e1", "e2"]}),
            ("READ", {"evidence_ids": []}),
            ("WINDOW", {"evidence_id": "e1"}),
        ]:
            assert mcp.read(setup[3], action, **args) == internal.read(setup[3], action, **args)
            assert state["seen"][-1] == state["seen"][-2]
        assert sum(e["event"] == "initialize" for e in events) == 1
        assert set(events[0]["tools"]) == {
            "get_course_revision",
            "search_course_evidence",
            "get_course_evidence",
            "get_evidence_context",
        }
        assert mcp.parameters.env == {"AGENT_JAVA_BASE_URL": url}
    finally:
        mcp.close()


@pytest.mark.parametrize("change", ["owner_id", "revision", "deleted", "signature"])
def test_java_rejects_authority_violation_with_same_error_as_internal(setup, java_fixture, change):
    url, state = java_fixture
    scope = dict(setup[3])
    if change in {"owner_id", "revision"}:
        scope[change] += 1
    if change == "deleted":
        state["deleted"] = True
    secret = "wrong" if change == "signature" else SECRET
    mcp = McpEvidenceAuthority(url, secret)
    try:
        for client in [mcp, EvidenceAuthority(url, secret)]:
            with pytest.raises(StudyError) as error:
                client.read(scope)
            assert error.value.code == "COURSE_UNAVAILABLE_OR_CHANGED" and error.value.status == 409
        assert len(state["seen"]) == 2  # neither MCP nor the client substitutes an authorization verdict
    finally:
        mcp.close()


def test_revision_change_during_java_read_is_rejected(mcp_setup, java_fixture):
    _, state = java_fixture
    state["after_read"] = lambda request: state.update(revision=state["revision"] + 1)
    with pytest.raises(StudyError, match="COURSE_UNAVAILABLE_OR_CHANGED"):
        mcp_setup[2].authority.read(mcp_setup[3], "SEARCH", query="stop")


def test_runtime_through_mcp_retains_public_privacy_and_tool_counts(mcp_setup):
    test_study.test_explain_practice_persists_events_citations_and_hides_answers(mcp_setup)
    with mcp_setup[0].connect() as conn:
        rows = conn.execute(
            "SELECT payload FROM study_event WHERE run_id=%s AND event_type='evidence_finished'",
            (test_study.read(mcp_setup)["run"]["run_id"],),
        ).fetchall()
    assert rows and all(row["payload"]["transport"] == "mcp-stdio" for row in rows)


def test_cancel_and_late_result_isolation_over_mcp(mcp_setup):
    test_study.test_cancel_during_model_io_fences_late_result(mcp_setup)


def test_delete_cascades_checkpoints_events_and_artifacts_over_mcp(mcp_setup):
    test_study.test_delete_sync_purges_artifacts_and_framework_checkpoints(mcp_setup)


def test_feedback_uses_the_same_mcp_adapter(mcp_setup, feedback):
    test_study_feedback.test_feedback_is_separate_from_answer_and_is_recovered_with_parent_practice(feedback)


@pytest.mark.parametrize("stop", ["cancel", "deadline", "revision", "deletion"])
def test_late_mcp_search_never_publishes_after_a_fence(mcp_setup, java_fixture, stop):
    store, _, runtime, scope = mcp_setup
    _, state = java_fixture
    state["delay"] = 0.8
    run = test_study.start(mcp_setup)
    worker = threading.Thread(target=runtime.execute, args=(run,))
    worker.start()
    try:
        assert state["search_entered"].wait(5)
        # A separate authority CHECK (e.g. gateway CANCEL) must not queue behind SEARCH.
        before = time.monotonic()
        runtime.authority.read(scope)
        assert time.monotonic() - before < 0.6
        if stop == "cancel":
            store.command(StudyCommand(**scope, operation="CANCEL", run_id=run["run_id"]), "mock")
        elif stop == "deadline":
            with store.connect() as conn:
                conn.execute(
                    "UPDATE study_run SET deadline=now()-interval '1 second' WHERE run_id=%s",
                    (run["run_id"],),
                )
        elif stop == "revision":
            state["revision"] += 1
        else:
            state["deleted"] = True
    finally:
        worker.join(5)
    assert not worker.is_alive()
    result = test_study.read(mcp_setup)
    assert result["run"]["status"] == {"cancel": "cancelled", "deadline": "budget_exceeded"}.get(
        stop, "failed"
    )
    assert result["artifact"] is None
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM study_tool_result WHERE run_id=%s", (run["run_id"],)
            ).fetchone()["n"]
            == 0
        )


def test_recovery_with_a_new_mcp_session_does_not_repeat_committed_tool(mcp_setup, java_fixture):
    store, _, runtime, _ = mcp_setup
    run = test_study.start(mcp_setup)
    original = store.save_tool

    def crash(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[3] == "create_practice_set":
            raise test_study.Crash()
        return result

    store.save_tool = crash
    with pytest.raises(test_study.Crash):
        runtime.execute(run)
    store.save_tool = original
    runtime.authority.close()
    fresh = McpEvidenceAuthority(java_fixture[0], SECRET)
    try:
        StudyRuntime(store, fresh, MockProvider()).execute(run)
        result = test_study.read(mcp_setup)
        assert result["run"]["status"] == "succeeded"
        assert result["run"]["model_calls"] == 4 and result["run"]["tool_calls"] == 3
    finally:
        fresh.close()


@pytest.mark.parametrize(
    ("mode", "expected"),
    [
        ("malformed", "MCP_MALFORMED_RESPONSE"),
        ("mismatched_text", "MCP_MALFORMED_RESPONSE"),
        ("scope", "EVIDENCE_SCOPE_MISMATCH"),
        ("timeout", "MCP_TIMEOUT"),
        ("crash", "MCP_SERVER_UNAVAILABLE"),
        ("catalog", "MCP_CONTRACT_MISMATCH"),
        ("error", "MCP_TOOL_FAILED"),
        ("search_malformed", "MCP_MALFORMED_RESPONSE"),
        ("search_timeout", "MCP_TIMEOUT"),
        ("search_crash", "MCP_SERVER_UNAVAILABLE"),
    ],
)
def test_broken_mcp_enters_existing_terminal_failure_without_fallback(setup, mode, expected):
    parameters = StdioServerParameters(
        command=sys.executable, args=[str(Path(__file__).parent / "fixtures/course_mcp_fault.py"), mode]
    )
    client = McpEvidenceAuthority("http://127.0.0.1:1", SECRET, parameters=parameters, timeout=2)
    store, direct, runtime, _ = setup
    runtime.authority = TracedAuthority(client)
    try:
        runtime.execute(test_study.start(setup))
        result = test_study.read(setup)
        assert result["run"]["status"] == "failed" and result["run"]["error_code"] == expected
        assert classify(expected) == (
            "permission-state" if expected == "EVIDENCE_SCOPE_MISMATCH" else "infra"
        )
        assert result["run"]["model_calls"] == result["run"]["tool_calls"] == int(mode.startswith("search_"))
        assert direct.reads == [] and result["artifact"] is None
    finally:
        client.close()


def test_transport_selection_is_explicit_and_invalid_values_fail(monkeypatch):
    monkeypatch.delenv("AGENT_COURSE_TOOL_TRANSPORT", raising=False)
    assert isinstance(course_authority("http://127.0.0.1:1", SECRET), EvidenceAuthority)
    monkeypatch.setenv("AGENT_COURSE_TOOL_TRANSPORT", "mcp")
    client = course_authority("http://127.0.0.1:1", SECRET)
    assert isinstance(client, McpEvidenceAuthority)
    client.close()
    monkeypatch.setenv("AGENT_COURSE_TOOL_TRANSPORT", "fallback")
    with pytest.raises(RuntimeError):
        course_authority("http://127.0.0.1:1", SECRET)
