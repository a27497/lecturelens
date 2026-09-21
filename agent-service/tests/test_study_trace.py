import json

import pytest
import test_study
from langgraph.checkpoint.postgres import PostgresSaver

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.replay import start_replay
from lecturelens_agent.study.store import StudyError
from lecturelens_agent.study.trace import RunTrace, classify, compare, metrics

setup = test_study.setup


class Gateway:
    """Exercise the same command/scope contract; real Java replay is a separate trial."""

    def __init__(self, setup):
        self.store, self.authority, _, scope = setup
        self.scope = {k: scope[k] for k in ("owner_id", "course_id", "revision")}
        self.calls = []

    def command(self, course_id, command):
        self.calls.append(command)
        self.authority.read(self.scope)
        assert course_id == self.scope["course_id"]
        return self.scope | self.store.command(StudyCommand(**self.scope, **command), "mock")


@pytest.fixture
def trace(setup):
    store, _, _, scope = setup
    yield RunTrace(store, Gateway(setup))
    with store.connect() as conn:
        sessions = conn.execute(
            "SELECT session_id FROM study_session WHERE course_id=%s AND session_id<>%s",
            (scope["course_id"], scope["session_id"]),
        ).fetchall()
        for row in sessions:
            with PostgresSaver.from_conn_string(store.dsn) as saver:
                saver.delete_thread(row["session_id"])
            conn.execute("DELETE FROM study_run WHERE session_id=%s", (row["session_id"],))
            conn.execute("DELETE FROM study_session WHERE session_id=%s", (row["session_id"],))


def test_trace_has_context_decisions_tools_checkpoints_and_real_usage_fields(setup, trace):
    store, _, runtime, _ = setup
    original = runtime.provider.decide

    def decide(*args):
        return {**original(*args), "usage": {"prompt_tokens": 17, "completion_tokens": 9}}

    runtime.provider.decide = decide
    run = test_study.start(setup)
    runtime.execute(run)
    result = trace.read(run["run_id"])
    assert result["question"] == run["goal"] and result["final_answer"]["questions"]
    assert result["tools"][0]["arguments"] and result["checkpoints"]
    starts = [e["payload"] for e in result["events"] if e["event_type"] == "model_started"]
    assert all(e["_trace"]["messages"] and e["_trace"]["schemas"] for e in starts)
    ids = {c["checkpoint_id"] for c in result["checkpoints"]}
    assert all(e["_trace"]["checkpoint_id"] in ids for e in starts)
    assert result["metrics"]["input_tokens"]["known_total"] >= 17
    assert result["metrics"]["tool_node_latency_inclusive_ms"]
    assert result["metrics"]["retrieval_calls"] == 1
    assert "worker_token" not in result["run"] and "model_config" not in result["run"]
    public = test_study.read(setup, "EVENTS")["events"]
    assert "_trace" not in json.dumps(public) and "An algorithm" not in json.dumps(public)
    assert not any(e["event_type"].startswith(("node_", "evidence_")) for e in public)
    # Cursors stay original durable sequence IDs, including private-event gaps.
    tail = store.command(StudyCommand(**setup[3], operation="EVENTS", after=public[2]["sequence"]), "mock")
    assert tail["events"] == public[3:]


def test_trace_never_includes_another_run_in_same_session(setup, trace):
    _, _, runtime, _ = setup
    first = test_study.start(setup)
    runtime.execute(first)
    second = test_study.start(setup, "second")
    runtime.execute(second)
    result = trace.read(first["run_id"])
    assert second["run_id"] not in json.dumps(result, default=str)


def test_replay_uses_normal_start_and_preserves_source_and_idempotency(setup, trace):
    store, _, runtime, _ = setup
    original = runtime.provider.decide
    runtime.provider.decide = lambda *_: {
        "name": "report_insufficient_evidence",
        "arguments": {"reason": "unsupported"},
    }
    source = test_study.start(setup)
    runtime.execute(source)
    before = trace.read(source["run_id"])
    runtime.provider.decide = original
    replay = start_replay(trace, source["run_id"], "repeat-safe")
    assert replay["run"]["session_id"] != source["session_id"]
    assert replay["run"]["model_calls"] == replay["run"]["tool_calls"] == 0
    assert start_replay(trace, source["run_id"], "repeat-safe")["run"]["run_id"] == replay["run"]["run_id"]
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == replay["run"]["run_id"]))
    after = trace.read(replay["run"]["run_id"])
    comparison = compare(before, after)
    assert comparison["before_status"] == "failed" and comparison["after_status"] == "succeeded"
    assert comparison["quality_pass"] is None
    assert trace.read(source["run_id"])["checkpoints"] == before["checkpoints"]
    assert sum(e["event_type"] == "replay_linked" for e in after["events"]) == 1


@pytest.mark.parametrize("change", ["owner", "revision", "deleted"])
def test_trace_and_replay_require_current_authority(setup, trace, change):
    _, authority, runtime, _ = setup
    source = test_study.start(setup)
    runtime.execute(source)
    if change == "deleted":
        authority.valid = False
    else:
        trace.gateway.scope["owner_id" if change == "owner" else "revision"] += 1
    with pytest.raises(StudyError):
        trace.read(source["run_id"])
    with pytest.raises(StudyError):
        start_replay(trace, source["run_id"], "denied")
    assert not any(c["operation"] == "START" for c in trace.gateway.calls)


def test_authority_change_during_projection_does_not_release_data(setup, trace):
    _, authority, runtime, _ = setup
    source = test_study.start(setup)
    runtime.execute(source)
    original = trace.authorize
    count = 0

    def authorize(row):
        nonlocal count
        count += 1
        if count == 2:
            authority.valid = False
        return original(row)

    trace.authorize = authorize
    with pytest.raises(StudyError):
        trace.read(source["run_id"])


def test_replay_rejects_active_run(setup, trace):
    run = test_study.start(setup)
    with pytest.raises(StudyError, match="TERMINAL_PRACTICE"):
        start_replay(trace, run["run_id"], "active")


def test_missing_measurements_are_not_reported_as_zero():
    result = metrics({"model_calls": 1, "tool_calls": 1, "reserved_tokens": 100}, [])
    assert result["input_tokens"] == {"total": None, "known_total": 0, "missing_calls": 1}
    assert result["tool_node_latency_inclusive_ms"] is None
    assert result["retrieval_calls"] is None


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("MODEL_TOOL_CONTRACT", "tool selection"),
        ("INDEX_SEARCH_FAILED", "retrieval"),
        ("CITATION_MISMATCH", "context"),
        ("QUALITY_REPAIR_EXHAUSTED", "generation"),
        ("COURSE_UNAVAILABLE_OR_CHANGED", "permission-state"),
        ("MODEL_TIMEOUT", "infra"),
    ],
)
def test_taxonomy(code, expected):
    assert classify(code) == expected
