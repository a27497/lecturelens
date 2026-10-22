"""Scope mechanics only: deterministic providers, real PostgreSQL, no quality claim."""

import copy
import json

import pytest
import test_study
from pydantic import ValidationError
from test_study import setup  # noqa: F401

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.learning_scope import (
    LearningScope,
    check_scope_response,
    inject_scope,
    validate_scope_call,
)
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore


def selection(ids=("e1",), policy="strict"):
    return dict(version=1, kind="segments", policy=policy, revision=1, evidence_ids=list(ids))


class ScopedAuthority(test_study.Authority):
    def __init__(self):
        super().__init__()
        self.selections = []
        self.empty = False

    def read(self, scope, action="CHECK", **arguments):
        validate_scope_call(scope, action, arguments)
        self.selections.append((copy.deepcopy(scope.get("learning_scope")), action, copy.deepcopy(arguments)))
        result = super().read(scope, action, **arguments)
        frozen = scope.get("learning_scope")
        if frozen:
            result["learning_scope"] = copy.deepcopy(frozen)
            if frozen["policy"] == "strict" or (action == "SEARCH" and not arguments.get("expand_to_course")):
                result["evidence"] = [
                    e for e in result["evidence"] if e["evidence_id"] in frozen["evidence_ids"]
                ]
        if self.empty:
            result["evidence"] = []
        return result


@pytest.fixture
def scoped(request):
    store, _, runtime, identity = request.getfixturevalue("setup")
    authority = ScopedAuthority()
    runtime.authority.authority = authority
    return store, authority, runtime, identity


def start(scoped, scope=None, key="scope-run", approval=False):
    store, _, _, identity = scoped
    response = store.command(
        StudyCommand(
            **identity,
            operation="START",
            goal="Explain this selection",
            request_key=key,
            learning_scope=selection() if scope is None else scope,
            approval_required=approval,
        ),
        "mock",
    )
    return next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"])


@pytest.mark.parametrize(
    "change",
    [
        {"evidence_ids": []},
        {"evidence_ids": ["e1", "e1"]},
        {"revision": -1},
        {"revision": True},
        {"policy": "silently-expand"},
        {"kind": "course"},
        {"version": 2},
        {"version": True},
    ],
)
def test_contract_rejects_invalid_selection(change):
    with pytest.raises(ValidationError):
        LearningScope.model_validate(selection() | change)


def test_scope_is_start_only_and_revision_bound():
    for operation, revision in [("READ", 1), ("START", 2)]:
        with pytest.raises(ValidationError):
            StudyCommand(
                owner_id=42, course_id="c", revision=revision, operation=operation, learning_scope=selection()
            )


def test_frozen_scope_survives_execution_and_hides_new_runs_from_legacy_workers(scoped):
    store, authority, runtime, identity = scoped
    run = start(scoped)
    with store.connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM study_run WHERE run_id=%s AND status IN ('queued','running')", (run["run_id"],)
        ).fetchone()
    runtime.execute(run)
    result = store.command(StudyCommand(**identity, operation="READ"), "mock")
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["learning_scope"] == selection()
    assert {c["evidence_id"] for c in result["artifact"]["citations"]} == {"e1"}
    assert all(scope == selection() for scope, _, _ in authority.selections)
    assert all(
        e == "e1"
        for _, action, args in authority.selections
        if action == "READ"
        for e in args["evidence_ids"]
    )
    same = store.command(
        StudyCommand(
            **identity,
            operation="START",
            goal="Explain this selection",
            request_key="scope-run",
            learning_scope=selection(),
        ),
        "mock",
    )
    assert same["run"]["run_id"] == run["run_id"]
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        store.command(
            StudyCommand(
                **identity,
                operation="START",
                goal="Explain this selection",
                request_key="scope-run",
                learning_scope=selection(policy="course"),
            ),
            "mock",
        )


def test_scope_busy_fence_and_cancel_leave_no_artifact(scoped):
    store, _, runtime, identity = scoped
    run = start(scoped)
    with pytest.raises(StudyError, match="SESSION_BUSY"):
        test_study.start(scoped, "legacy-run")
    store.command(StudyCommand(**identity, operation="CANCEL", run_id=run["run_id"]), "mock")
    runtime.execute(run)
    result = store.command(StudyCommand(**identity, operation="READ"), "mock")
    assert result["run"]["status"] == "cancelled" and result["artifact"] is None
    assert result["run"]["learning_scope"] == selection()


def test_scope_approval_checkpoint_recovery_preserves_scope_and_budget(scoped):
    store, authority, runtime, identity = scoped
    run = start(scoped, approval=True)
    runtime.execute(run)
    waiting = store.command(StudyCommand(**identity, operation="READ"), "mock")
    assert waiting["run"]["status"] == "awaiting_approval"
    with store.connect() as conn:
        raw = conn.execute("SELECT status FROM study_run WHERE run_id=%s", (run["run_id"],)).fetchone()[
            "status"
        ]
        assert raw == "awaiting_approval_scoped_v1"
    store.command(
        StudyCommand(
            **identity,
            operation="DECIDE_APPROVAL",
            run_id=run["run_id"],
            request_key="approve",
            approval_decision="approve",
        ),
        "mock",
    )
    restarted = StudyRuntime(StudyStore(store.dsn), authority, MockProvider())
    restarted.execute(next(r for r in store.candidates() if r["run_id"] == run["run_id"]))
    final = store.command(StudyCommand(**identity, operation="READ"), "mock")
    assert final["run"]["status"] == "succeeded"
    assert final["run"]["learning_scope"] == selection()
    assert final["run"]["model_calls"] == waiting["run"]["model_calls"]


def test_empty_strict_scope_can_only_publish_insufficiency(scoped):
    store, authority, runtime, identity = scoped
    authority.empty = True

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        return (
            {
                "name": "report_insufficient_evidence",
                "arguments": {"reason": "No support in the selected passages."},
            }
            if body["history"]
            else {"name": "search_course_evidence", "arguments": {"query": "unsupported topic"}}
        )

    runtime.provider.decide = decide
    runtime.execute(start(scoped))
    result = store.command(StudyCommand(**identity, operation="READ"), "mock")
    assert result["artifact"]["kind"] == "insufficient_evidence"
    assert result["artifact"]["citations"] == [] and result["artifact"]["questions"] == []
    assert not any(args.get("expand_to_course") for _, _, args in authority.selections)


def test_recent_context_does_not_leak_a_previous_scope(scoped):
    store, _, runtime, identity = scoped
    first = start(scoped)
    runtime.execute(first)
    second = start(scoped, selection(["e2"]), key="next")
    assert store.recent_context(identity["session_id"], second["run_id"]) == []


def test_scope_echo_and_tool_boundaries_fail_closed():
    scope = dict(owner_id=42, course_id="c", revision=1, learning_scope=selection())
    payload = inject_scope(scope, {})
    for result in [{}, {"learning_scope": selection(), "evidence": [{"evidence_id": "e2"}]}]:
        with pytest.raises(StudyError, match="EVIDENCE_SCOPE_MISMATCH"):
            check_scope_response(payload, result)
    for action, args in [
        ("READ", {"evidence_ids": ["e2"]}),
        ("WINDOW", {"evidence_id": "e2"}),
        ("SEARCH", {"expand_to_course": True}),
    ]:
        with pytest.raises(StudyError, match="EVIDENCE_SCOPE_MISMATCH"):
            validate_scope_call(scope, action, args)
    validate_scope_call(
        scope | {"learning_scope": selection(policy="course")}, "SEARCH", {"expand_to_course": True}
    )


def test_feedback_inherits_scope_even_for_an_older_writer(scoped, monkeypatch):
    monkeypatch.setenv("STUDY_FEEDBACK_ENABLED", "true")
    store, authority, runtime, identity = scoped
    run = start(scoped)
    runtime.execute(run)
    view = store.command(StudyCommand(**identity, operation="READ"), "mock")
    artifact_id = view["artifact"]["artifact_id"]
    attempt = store.command(
        StudyCommand(
            **identity,
            operation="SAVE_ATTEMPT",
            run_id=run["run_id"],
            artifact_id=artifact_id,
            question_index=0,
            request_key="answer",
            expected_version=0,
            answer_text="My saved answer",
        ),
        "mock",
    )["attempt"]
    feedback = store.command(
        StudyCommand(
            **identity,
            operation="START_FEEDBACK",
            run_id=run["run_id"],
            artifact_id=artifact_id,
            question_index=0,
            attempt_id=attempt["attempt_id"],
            request_key="feedback",
        ),
        "mock",
    )
    assert feedback["run"]["learning_scope"] == selection()
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == feedback["run"]["run_id"]))
    with store.connect() as conn:
        # Same insert an old binary would issue: no learning_scope, default legacy queue state.
        row = conn.execute(
            "INSERT INTO study_run(run_id,session_id,request_key,goal,model_mode,task_kind,source_attempt_id) "
            "VALUES (%s,%s,'old-feedback','Feedback','mock','feedback',%s) RETURNING *",
            (run["run_id"] + "-old", identity["session_id"], attempt["attempt_id"]),
        ).fetchone()
        assert row["learning_scope"] == selection() and row["status"] == "queued_scoped_v1"
    with pytest.raises(Exception, match="Learning scope is immutable"), store.connect() as conn:
        conn.execute("UPDATE study_run SET learning_scope=NULL WHERE run_id=%s", (run["run_id"],))


def test_crashed_running_scope_remains_invisible_to_old_worker(scoped):
    store, _, runtime, identity = scoped
    run = start(scoped)
    store.claim(run["run_id"], "crashed-worker", 90)
    with store.connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM study_run WHERE run_id=%s AND status IN ('queued','running')", (run["run_id"],)
        ).fetchone()
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == run["run_id"]))
    view = store.command(StudyCommand(**identity, operation="READ"), "mock")
    assert view["run"]["status"] == "succeeded" and view["run"]["learning_scope"] == selection()
