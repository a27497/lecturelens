import pytest
import test_study
import test_study_feedback
from pydantic import ValidationError

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore

setup = test_study.setup
practice = test_study_feedback.practice
feedback = test_study_feedback.feedback


def start_wait(setup):
    store, _, runtime, scope = setup
    response = store.command(
        StudyCommand(
            **scope,
            operation="START",
            request_key="approval",
            goal="Explain stopping conditions",
            approval_required=True,
        ),
        "mock",
    )
    run = next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"])
    runtime.execute(run)
    return run


def decision(setup, value="approve", edit=None, key="decision"):
    store, _, _, scope = setup
    run = test_study.read(setup)["run"]
    return store.command(
        StudyCommand(
            **scope,
            run_id=run["run_id"],
            operation="DECIDE_APPROVAL",
            request_key=key,
            approval_decision=value,
            approval_edit=edit,
        ),
        "mock",
    )


@pytest.mark.parametrize("value", ["approve", "edit", "reject"])
def test_durable_approval_does_not_publish_before_decision(setup, value):
    store, authority, _, scope = setup
    run = start_wait(setup)
    waiting = test_study.read(setup)
    assert waiting["run"]["status"] == "awaiting_approval"
    assert waiting["artifact"] is None
    assert all(
        "answer" not in q and "answer_points" not in q for q in waiting["approval"]["preview"]["questions"]
    )
    assert run["run_id"] not in {r["run_id"] for r in store.candidates()}
    with pytest.raises(StudyError, match="SESSION_BUSY"):
        test_study.start(setup, "other")
    with pytest.raises(StudyError, match="ARTIFACT_NOT_READY"):
        test_study.read(setup, "ANSWERS")
    with store.connect() as conn:
        row = conn.execute(
            "SELECT deadline,approval_seconds FROM study_run WHERE run_id=%s", (run["run_id"],)
        ).fetchone()
        assert row["deadline"] is None and row["approval_seconds"] > 0
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM study_artifact WHERE run_id=%s", (run["run_id"],)
            ).fetchone()["n"]
            == 0
        )
    edited = "Human explanation: an explicit stopping condition is necessary." if value == "edit" else None
    decision(setup, value, edited)
    decision(setup, value, edited)  # Lost HTTP response is safely replayable.
    with pytest.raises(StudyError, match="APPROVAL_DECISION_CONFLICT"):
        decision(setup, value, edited, key="other")
    restarted = StudyRuntime(StudyStore(store.dsn), authority, test_study.MockProvider())
    restarted.execute(next(r for r in store.candidates() if r["run_id"] == run["run_id"]))
    final = test_study.read(setup)
    assert final["run"]["model_calls"] == waiting["run"]["model_calls"] == 4
    assert final["run"]["tool_calls"] == waiting["run"]["tool_calls"] == 3
    if value == "reject":
        assert final["run"]["status"] == "failed" and final["run"]["error_code"] == "APPROVAL_REJECTED"
        assert final["artifact"] is None
    else:
        assert final["run"]["status"] == "succeeded"
        assert final["artifact"]
        if value == "edit":
            assert final["artifact"]["explanation"] == edited and final["artifact"]["human_edited"]
    types = [e["event_type"] for e in test_study.read(setup, "EVENTS")["events"]]
    assert types.count("approval_decided") == 1
    assert types.count("artifact_created") == (0 if value == "reject" else 1)
    assert types.index("approval_waiting") < types.index("approval_decided")


@pytest.mark.parametrize("fence", ["cancel", "revision", "ownership"])
def test_waiting_approval_preserves_fences(setup, fence):
    store, authority, runtime, scope = setup
    run = start_wait(setup)
    if fence == "cancel":
        test_study.read(setup, "CANCEL")
        with pytest.raises(StudyError, match="APPROVAL_NOT_WAITING"):
            decision(setup)
    elif fence == "ownership":
        with pytest.raises(StudyError, match="SESSION_NOT_FOUND_OR_STALE"):
            store.command(
                StudyCommand(
                    **(scope | {"owner_id": 99}),
                    run_id=run["run_id"],
                    operation="DECIDE_APPROVAL",
                    request_key="bad",
                    approval_decision="approve",
                ),
                "mock",
            )
    else:
        decision(setup)
        authority.valid = False
        runtime.execute(run)
        assert test_study.read(setup)["run"]["status"] == "failed"
    assert test_study.read(setup)["artifact"] is None


@pytest.mark.parametrize("value", ["approve", "edit", "reject"])
def test_feedback_publication_gate_and_rejection(feedback, value):
    store, scope, runtime, _, _, _, run, _ = feedback
    with store.connect() as conn:
        conn.execute("UPDATE study_run SET approval_required=true WHERE run_id=%s", (run["run_id"],))
    run = next(r for r in store.candidates() if r["run_id"] == run["run_id"])
    runtime.execute(run)
    command_scope = {
        "owner_id": scope["owner_id"],
        "course_id": scope["course_id"],
        "revision": scope["revision"],
        "session_id": scope["session_id"],
        "run_id": run["run_id"],
    }
    view = store.command(StudyCommand(**command_scope, operation="READ"), "mock")
    assert view["run"]["status"] == "awaiting_approval" and view["feedback"] is None
    store.command(
        StudyCommand(
            **command_scope,
            operation="DECIDE_APPROVAL",
            request_key="decision",
            approval_decision=value,
            approval_edit="Human guidance: check the stopping condition." if value == "edit" else None,
        ),
        "mock",
    )
    runtime.execute(run)
    final = store.command(StudyCommand(**command_scope, operation="READ"), "mock")
    assert final["run"]["status"] == ("failed" if value == "reject" else "succeeded")
    assert (final["feedback"] is None) == (value == "reject")
    if value == "edit":
        assert (
            final["feedback"]["content"]["human_guidance"] == "Human guidance: check the stopping condition."
        )
    with store.connect() as conn:
        assert conn.execute(
            "SELECT count(*) AS n FROM study_feedback WHERE run_id=%s", (run["run_id"],)
        ).fetchone()["n"] == (0 if value == "reject" else 1)


def test_approval_contract_rejects_unscoped_and_invalid_edits():
    base = dict(
        owner_id=1,
        course_id="course",
        revision=1,
        operation="DECIDE_APPROVAL",
        session_id="session",
        run_id="run",
        request_key="key",
        approval_decision="edit",
    )
    for changes in (
        {},
        {"approval_edit": " "},
        {"approval_edit": "x" * 4001},
        {"approval_edit": "valid", "run_id": None},
        {"approval_decision": "approve", "approval_edit": "bad"},
    ):
        with pytest.raises(ValidationError):
            StudyCommand(**(base | changes))


@pytest.mark.parametrize("boundary", ["model_committed", "model_unknown", "tool_reserved"])
def test_replayed_node_charges_budget_once_and_never_repeats_model_request(setup, monkeypatch, boundary):
    from lecturelens_agent.study import call_journal

    store, authority, runtime, _ = setup
    run = test_study.start(setup)
    model_requests = []
    original_decide = runtime.provider.decide

    def count(*args):
        model_requests.append(1)
        return original_decide(*args)

    runtime.provider.decide = count
    if boundary == "tool_reserved":
        original = store.reserve

        def crash(*args, **kwargs):
            original(*args, **kwargs)
            raise test_study.Crash()

        monkeypatch.setattr(store, "reserve", crash)
    else:
        name = "complete" if boundary == "model_committed" else "begin"
        original = getattr(call_journal, name)

        def crash(*args, **kwargs):
            original(*args, **kwargs)
            raise test_study.Crash()

        monkeypatch.setattr(call_journal, name, crash)
    with pytest.raises(test_study.Crash):
        runtime.execute(run)
    monkeypatch.undo()
    runtime.execute(run)
    final = test_study.read(setup)
    if boundary == "model_unknown":
        assert final["run"]["status"] == "failed"
        assert final["run"]["error_code"] == "MODEL_OUTCOME_UNKNOWN"
        assert final["run"]["model_calls"] == 1 and not model_requests
        assert final["artifact"] is None
        assert any(e["event_type"] == "recovery_stopped" for e in test_study.read(setup, "EVENTS")["events"])
    else:
        assert final["run"]["status"] == "succeeded"
        assert final["run"]["model_calls"] == 4 and final["run"]["tool_calls"] == 3
        assert len(model_requests) == 3


@pytest.mark.parametrize("occurrence", [1, 2])
@pytest.mark.parametrize("committed", [False, True])
def test_budget_hint_changes_do_not_create_a_new_logical_model_call(
    setup, monkeypatch, occurrence, committed
):
    from lecturelens_agent.study import call_journal

    _, _, runtime, _ = setup
    run = test_study.start(setup)
    method = "complete" if committed else "begin"
    original = getattr(call_journal, method)
    calls = 0

    def crash(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        if calls == occurrence:
            raise test_study.Crash()
        calls += 1
        return result

    monkeypatch.setattr(call_journal, method, crash)
    with pytest.raises(test_study.Crash):
        runtime.execute(run)
    monkeypatch.undo()
    runtime.execute(run)
    view = test_study.read(setup)
    if committed:
        assert view["run"]["status"] == "succeeded" and view["run"]["model_calls"] == 4
    else:
        assert view["run"]["error_code"] == "MODEL_OUTCOME_UNKNOWN"
        assert view["run"]["model_calls"] == occurrence + 1


def test_replay_key_separates_protocol_repair_and_detects_nonbudget_input_drift(setup):
    from lecturelens_agent.study import call_journal, telemetry

    store, _, _, _ = setup
    run = test_study.start(setup)
    store.claim(run["run_id"], "journal", 90)
    detail = {
        "messages": [{"role": "user", "content": '{"goal":"learn","budget":{"left":5}}'}],
        "schemas": [],
    }
    token = telemetry._span.set({"node": "decide", "turn": 1, "call_id": None, "model_ordinal": 0})
    try:
        key = call_journal.operation_key([], [], "decision")
        prior, meta = call_journal.begin(
            store, run["run_id"], "journal", key, 100, {"purpose": "decision"}, detail
        )
        assert prior is None
        call_journal.complete(store, run["run_id"], "journal", key, meta, {}, response={"ok": True})
        telemetry._span.get()["model_ordinal"] = 0
        other = {
            "messages": [{"role": "user", "content": '{"goal":"learn","budget":{"left":4}}'}],
            "schemas": [],
        }
        assert call_journal.operation_key([], [], "decision") == key
        prior, _ = call_journal.begin(store, run["run_id"], "journal", key, 200, {}, other)
        assert call_journal.replay(prior) == {"ok": True}
        other["messages"][0]["content"] = '{"goal":"different","budget":{"left":4}}'
        prior, _ = call_journal.begin(store, run["run_id"], "journal", key, 200, {}, other)
        with pytest.raises(StudyError, match="MODEL_INPUT_CHANGED"):
            call_journal.replay(prior)
        telemetry._span.get().update(model_ordinal=0, protocol_retries=1)
        assert call_journal.operation_key([], [], "decision") != key
        assert store.guard(run["run_id"], "journal")["model_calls"] == 1
    finally:
        telemetry._span.reset(token)


@pytest.mark.parametrize("complete", [False, True])
def test_pre_journal_trace_observation_can_resume_without_recharging(setup, complete):
    from lecturelens_agent.study import call_journal

    store, _, _, _ = setup
    run = test_study.start(setup)
    store.claim(run["run_id"], "legacy", 90)
    store.reserve(run["run_id"], "legacy", "model", 123)
    detail = {
        "messages": [{"role": "user", "content": '{"goal":"legacy","budget":{"left":5}}'}],
        "schemas": [],
    }
    store.event(
        run["run_id"], "legacy", "model_started", {"attempt": 1, "purpose": "decision", "_trace": detail}
    )
    if complete:
        store.event(
            run["run_id"],
            "legacy",
            "model_finished",
            {"attempt": 1, "purpose": "decision", "_trace": {"response": {"ok": True}}},
        )
    other = {
        "messages": [{"role": "user", "content": '{"goal":"legacy","budget":{"left":4}}'}],
        "schemas": [],
    }
    prior, _ = call_journal.begin(
        store, run["run_id"], "legacy", "stable-slot", 456, {"purpose": "decision"}, other
    )
    if complete:
        assert call_journal.replay(prior) == {"ok": True}
    else:
        with pytest.raises(StudyError, match="MODEL_OUTCOME_UNKNOWN"):
            call_journal.replay(prior)
    row = store.guard(run["run_id"], "legacy")
    assert row["model_calls"] == 1 and row["reserved_tokens"] == 123


def test_legacy_tool_started_is_not_charged_twice(setup):
    store, _, _, _ = setup
    run = test_study.start(setup)
    store.claim(run["run_id"], "legacy", 90)
    store.reserve(run["run_id"], "legacy", "tool")
    store.event(run["run_id"], "legacy", "tool_started", {"call_id": "0:0", "tool": "search_course_evidence"})
    store.reserve(run["run_id"], "legacy", "tool", key="0:0")
    store.reserve(run["run_id"], "legacy", "tool", key="0:0")
    assert store.guard(run["run_id"], "legacy")["tool_calls"] == 1


@pytest.mark.parametrize("committed", [False, True])
def test_feedback_budget_dependent_offering_is_frozen_on_recovery(feedback, monkeypatch, committed):
    from lecturelens_agent.study import call_journal

    _, _, runtime, _, _, _, run, _ = feedback
    original_feedback = runtime.provider.feedback

    def with_window(messages, schemas, timeout, *, review=False):
        import json

        body = json.loads(messages[-1]["content"])
        if not review and len(body["observations"]) == 1:
            return {
                "calls": [
                    {
                        "name": "read_feedback_window",
                        "arguments": {"evidence_id": body["evidence"][0]["evidence_id"]},
                    }
                ]
            }
        return original_feedback(messages, schemas, timeout, review=review)

    runtime.provider.feedback = with_window
    method = "complete" if committed else "begin"
    original = getattr(call_journal, method)
    calls = 0

    def crash(*args, **kwargs):
        nonlocal calls
        result = original(*args, **kwargs)
        if calls == 3:
            raise test_study.Crash()
        calls += 1
        return result

    monkeypatch.setattr(call_journal, method, crash)
    with pytest.raises(test_study.Crash):
        runtime.execute(run)
    monkeypatch.undo()
    runtime.execute(run)
    result = test_study_feedback.view(feedback)
    if committed:
        assert result["run"]["status"] == "succeeded" and result["run"]["model_calls"] == 5
    else:
        assert result["run"]["error_code"] == "MODEL_OUTCOME_UNKNOWN" and result["run"]["model_calls"] == 4
