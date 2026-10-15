"""Fault semantics with real persistent budgets, journal and checkpoints."""

import json
import threading

import pytest
import test_study
from pydantic import ValidationError

from lecturelens_agent.course_mcp.contracts import SearchRequest
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.store import StudyError

setup = test_study.setup


def public(setup):
    return test_study.read(setup, "EVENTS")["events"]


@pytest.mark.parametrize("action", ["SEARCH", "READ", "WINDOW", "CHECK"])
@pytest.mark.parametrize("failures", [1, 2, 3])
def test_bounded_read_retry_is_charged_and_public(setup, action, failures):
    store, authority, runtime, _ = setup
    original = authority.read
    attempts = []

    def broken(scope, selected="CHECK", **args):
        if selected == action:
            attempts.append(selected)
            if len(attempts) <= failures:
                raise StudyError("MCP_AUTHORITY_UNAVAILABLE", 503)
        return original(scope, selected, **args)

    authority.read = broken
    run = test_study.start(setup)
    runtime.execute(run)
    result = test_study.read(setup)
    retries = [e for e in public(setup) if e["event_type"] == "tool_retry_started"]
    assert len(retries) == min(failures, 2)
    assert all(e["payload"]["failure_category"] == "tool_dependency_unavailable" for e in retries)
    if failures < 3:
        assert result["run"]["status"] == "succeeded"
        assert result["run"]["tool_calls"] == 3 + failures
    else:
        assert result["run"]["status"] == "failed"
        assert result["artifact"] is None and len(attempts) == 3
        assert any(e["event_type"] == "dependency_stopped" for e in public(setup))


@pytest.mark.parametrize(
    "code,category",
    [
        ("MCP_MALFORMED_RESPONSE", "malformed_response"),
        ("MCP_MALFORMED_AUTHORITY_RESPONSE", "malformed_response"),
        ("EVIDENCE_SCOPE_MISMATCH", "permission_state"),
        ("COURSE_UNAVAILABLE_OR_CHANGED", "permission_state"),
    ],
)
def test_fail_closed_errors_are_not_retried(setup, code, category):
    _, authority, runtime, _ = setup
    original = authority.read
    attempts = []

    def broken(scope, action="CHECK", **args):
        if action == "SEARCH":
            attempts.append(action)
            raise StudyError(code)
        return original(scope, action, **args)

    authority.read = broken
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "failed" and result["artifact"] is None
    assert len(attempts) == 1
    stopped = next(e for e in public(setup) if e["event_type"] == "dependency_stopped")
    assert stopped["payload"]["failure_category"] == category


@pytest.mark.parametrize(
    "call,category",
    [
        ({"name": "publish_answer", "arguments": {}}, "model_tool_selection"),
        ({"name": "search_course_evidence", "arguments": {"query": "x" * 501}}, "invalid_parameters"),
        (
            {"name": "search_course_evidence", "arguments": {"query": "x", "start_ms": -1, "end_ms": 2}},
            "invalid_parameters",
        ),
        ({"name": "search_course_evidence", "arguments": "{}"}, "invalid_parameters"),
        ({"calls": [17]}, "model_protocol"),
        ({"calls": [{"name": ["search_course_evidence"], "arguments": {}}]}, "model_tool_selection"),
    ],
)
def test_illegal_model_call_is_rejected_before_execution(setup, call, category):
    _, authority, runtime, _ = setup
    runtime.provider.decide = lambda *_: call
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "failed" and result["artifact"] is None
    assert result["run"]["tool_calls"] == 0
    assert all(action == "CHECK" for action in authority.reads)
    rejected = next(e for e in public(setup) if e["event_type"] == "tool_rejected")
    assert rejected["payload"]["failure_category"] == category
    assert "arguments" not in json.dumps(public(setup))


@pytest.mark.parametrize("fence", ["cancel", "deadline", "revision", "shutdown", "budget"])
def test_failure_cannot_bypass_fences_to_retry(setup, fence):
    store, authority, runtime, scope = setup
    run = test_study.start(setup)
    original = authority.read
    attempts = []

    def broken(scope_arg, action="CHECK", **args):
        if action == "SEARCH":
            attempts.append(action)
            if fence == "cancel":
                store.command(StudyCommand(**scope, operation="CANCEL", run_id=run["run_id"]), "mock")
            elif fence == "deadline":
                with store.connect() as conn:
                    conn.execute(
                        "UPDATE study_run SET deadline=now()-interval '1 second' WHERE run_id=%s",
                        (run["run_id"],),
                    )
            elif fence == "budget":
                with store.connect() as conn:
                    conn.execute("UPDATE study_run SET tool_calls=8 WHERE run_id=%s", (run["run_id"],))
            elif fence == "revision":
                authority.valid = False
                raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED")
            else:
                runtime.stop.set()
            raise StudyError("MCP_AUTHORITY_UNAVAILABLE", 503)
        return original(scope_arg, action, **args)

    authority.read = broken
    runtime.execute(run)
    result = test_study.read(setup)
    assert len(attempts) == 1 and result["artifact"] is None
    assert (
        result["run"]["status"]
        == {
            "cancel": "cancelled",
            "deadline": "budget_exceeded",
            "budget": "budget_exceeded",
            "revision": "failed",
            "shutdown": "running",
        }[fence]
    )


def test_checkpoint_restart_preserves_attempt_cap_and_error(setup):
    store, authority, runtime, _ = setup
    original = authority.read
    attempts = []

    def crash(scope, action="CHECK", **args):
        if action == "SEARCH":
            attempts.append(action)
            if len(attempts) == 2:
                raise test_study.Crash()
            raise StudyError("MCP_TIMEOUT", 503)
        return original(scope, action, **args)

    authority.read = crash
    run = test_study.start(setup)
    with pytest.raises(test_study.Crash):
        runtime.execute(run)
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == "failed"
    assert result["run"]["error_code"] == "MCP_TIMEOUT" and len(attempts) == 3
    assert result["run"]["tool_calls"] == 3  # one logical reservation + two persisted physical retries
    assert [e["payload"]["attempt"] for e in public(setup) if e["event_type"] == "tool_retry_started"] == [
        2,
        3,
    ]


def test_cancel_during_backoff_stops_before_next_external_call(setup):
    store, authority, runtime, scope = setup
    original = authority.read
    ready = threading.Event()
    release = threading.Event()
    original_event = store.event
    calls = []

    def event(*args):
        result = original_event(*args)
        if args[2] == "tool_retry_backoff":
            ready.set()
            assert release.wait(5)
        return result

    def broken(scope, action="CHECK", **args):
        if action == "SEARCH":
            calls.append(action)
            raise StudyError("MCP_TIMEOUT", 503)
        return original(scope, action, **args)

    store.event, authority.read = event, broken
    run = test_study.start(setup)
    worker = threading.Thread(target=runtime.execute, args=(run,))
    worker.start()
    try:
        assert ready.wait(5)
        store.command(StudyCommand(**scope, operation="CANCEL", run_id=run["run_id"]), "mock")
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and len(calls) == 1
    assert test_study.read(setup)["run"]["status"] == "cancelled"


def test_transport_validates_window_before_connect():
    from lecturelens_agent.course_mcp.client import McpEvidenceAuthority

    client = McpEvidenceAuthority("http://127.0.0.1:1", "synthetic-secret")
    client._connection = lambda: pytest.fail("invalid arguments opened a transport")
    with pytest.raises(StudyError, match="MCP_INVALID_REQUEST"):
        client.read(
            {"owner_id": 1, "course_id": "c", "revision": 0}, "SEARCH", query="x", start_ms=3, end_ms=1
        )
    client.close()


@pytest.mark.parametrize(
    "args", [{"query": " "}, {"query": "x", "start_ms": 1}, {"query": "x", "end_ms": -1}]
)
def test_mcp_request_rejects_bad_windows(args):
    with pytest.raises(ValidationError):
        SearchRequest.model_validate(
            {
                "owner_id": 1,
                "course_id": "c",
                "revision": 0,
                "authorization": {"timestamp": "0", "signature": "0" * 64},
                **args,
            }
        )


def test_artifact_write_failure_is_never_automatically_retried(setup):
    store, _, runtime, _ = setup
    original = store.save_tool
    writes = []

    def fail_write(*args, **kwargs):
        if args[3] == "create_practice_set":
            writes.append(args[3])
            raise StudyError("MCP_AUTHORITY_UNAVAILABLE", 503)
        return original(*args, **kwargs)

    store.save_tool = fail_write
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert len(writes) == 1 and result["run"]["status"] == "failed"
    assert result["artifact"] is None
    assert not any(e["event_type"] == "tool_retry_started" for e in public(setup))


@pytest.mark.parametrize("payload", [None, {"evidence": "PRIVATE bad data"}, []])
def test_malformed_internal_response_is_public_and_never_published(setup, payload):
    _, authority, runtime, _ = setup
    original = authority.read

    def malformed(scope, action="CHECK", **args):
        return payload if action == "SEARCH" else original(scope, action, **args)

    authority.read = malformed
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["error_code"] == "MCP_MALFORMED_RESPONSE" and result["artifact"] is None
    assert not any(e["event_type"] == "tool_retry_started" for e in public(setup))
    assert any(e["payload"].get("failure_category") == "malformed_response" for e in public(setup))
    assert "PRIVATE" not in json.dumps(public(setup))


def test_integer_outside_java_long_is_rejected_before_goal_normalization(setup):
    _, authority, runtime, _ = setup
    runtime.provider.decide = lambda *_: {
        "name": "search_course_evidence",
        "arguments": {
            "query": "stop",
            "start_ms": 0,
            "end_ms": 2**63,
        },
    }
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["error_code"] == "INVALID_TOOL_ARGUMENTS"
    assert result["run"]["tool_calls"] == 0 and all(a == "CHECK" for a in authority.reads)
    assert (
        next(e for e in public(setup) if e["event_type"] == "tool_rejected")["payload"]["failure_category"]
        == "invalid_parameters"
    )


@pytest.mark.parametrize(
    "change", [{"owner_id": 2**63}, {"revision": 2**63}, {"start_ms": 0, "end_ms": 2**63}]
)
def test_mcp_request_rejects_integer_overflow(change):
    with pytest.raises(ValidationError):
        SearchRequest.model_validate(
            {
                "owner_id": 1,
                "course_id": "c",
                "revision": 0,
                "query": "x",
                "authorization": {"timestamp": "0", "signature": "0" * 64},
                **change,
            }
        )
