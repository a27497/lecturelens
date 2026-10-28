"""Real PostgreSQL checks for private keys, immutable deterministic judgments and legacy answers."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import test_study

from lecturelens_agent.study.choice_graph import MockChoiceProvider
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.store import StudyError, StudyStore

setup = test_study.setup


@pytest.fixture
def choice(setup):
    store, authority, runtime, scope = setup
    response = store.command(
        StudyCommand(
            **scope,
            operation="START",
            request_key="choice-start",
            goal="Identify the course stopping condition.",
            practice_format="choice",
        ),
        "mock",
    )
    queued = next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"])
    assert queued["status"] == "queued_choice_v1"
    runtime.execute(queued)
    view = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert view["run"]["status"] == "succeeded", view
    with store.connect() as conn:
        private = conn.execute(
            "SELECT content FROM study_artifact WHERE artifact_id=%s", (view["artifact"]["artifact_id"],)
        ).fetchone()["content"]
    return (
        store,
        authority,
        runtime,
        scope | {"run_id": view["run"]["run_id"], "artifact_id": view["artifact"]["artifact_id"]},
        private,
    )


def read(choice, **changes):
    store, _, _, scope, _ = choice
    return store.command(StudyCommand(**(scope | {"operation": "READ"} | changes)), "mock")


def save(choice, option, version=0, key="choice-answer", question_index=0, **changes):
    store, _, _, scope, _ = choice
    return store.command(
        StudyCommand(
            **(
                scope
                | {
                    "operation": "SAVE_ATTEMPT",
                    "question_index": question_index,
                    "selected_option_id": option,
                    "expected_version": version,
                    "request_key": key,
                }
                | changes
            )
        ),
        "mock",
    )["attempt"]


def test_all_browser_projections_keep_private_key_hidden_until_a_nonempty_submission(choice):
    view = read(choice)
    q = view["artifact"]["questions"][0]
    assert q["kind"] == "choice" and len(q["options"]) == 3
    assert "correct_option_id" not in json.dumps(view, default=str)
    for op in ("ANSWERS", "EVENTS", "RUNS", "ATTEMPT_HISTORY"):
        response = read(choice, operation=op, question_index=0)
        assert "correct_option_id" not in json.dumps(response, default=str), (op, response)
    assert view["attempts"] == [] and all(row["attempt"] is None for row in view["practice_results"])
    store, _, _, scope, _ = choice
    for fields in ({}, {"selected_option_id": ""}, {"selected_option_id": "Z"}, {"answer_text": "A"}):
        with pytest.raises((StudyError, ValueError)):
            store.command(
                StudyCommand(
                    **scope,
                    operation="SAVE_ATTEMPT",
                    question_index=0,
                    request_key="blank",
                    expected_version=0,
                    **fields,
                ),
                "mock",
            )
    assert read(choice)["attempts"] == []


def test_each_selected_option_matches_private_key_and_cannot_be_model_graded(choice):
    _, _, runtime, _, private = choice
    private_question = private["questions"][0]
    initial = read(choice)["run"]
    # Any grader/model request after publication would fail this check.
    runtime.provider.decide = lambda *_: pytest.fail("Submission must not call a model")
    for version, option in enumerate(private_question["options"]):
        saved = save(choice, option["id"], version=version, key=f"answer-{version}")
        result = saved["choice_result"]
        assert result["is_correct"] is (option["id"] == private_question["correct_option_id"])
        assert result["correct_option_id"] == private_question["correct_option_id"]
        assert saved["selected_option_id"] == option["id"]
        assert saved["answer_text"] == option["text"]
        assert [c["evidence_id"] for c in result["citations"]] == private_question["evidence_ids"]
        assert read(choice)["practice_results"][0]["attempt"] == saved
    after = read(choice)["run"]
    assert (after["model_calls"], after["tool_calls"]) == (initial["model_calls"], initial["tool_calls"])


def test_judgments_survive_restart_and_history_never_changes_prior_versions(choice):
    store, _, _, scope, private = choice
    q = private["questions"][0]
    wrong = next(o["id"] for o in q["options"] if o["id"] != q["correct_option_id"])
    first = save(choice, wrong)
    second = save(choice, q["correct_option_id"], 1, "correction")
    assert not first["choice_result"]["is_correct"] and second["choice_result"]["is_correct"]
    restarted = StudyStore(store.dsn)
    restarted.initialize()
    assert restarted.command(StudyCommand(**scope, operation="READ"), "mock")["attempts"] == [second]
    history = read(choice, operation="ATTEMPT_HISTORY", question_index=0)["attempts"]
    assert history == [second, first]
    assert save(choice, wrong) == first  # Replayed request after a later version.
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        save(choice, q["correct_option_id"])


def test_concurrent_choices_only_commit_one_answer_and_its_matching_judgment(choice):
    q = choice[-1]["questions"][0]

    def submit(option):
        try:
            return save(choice, option["id"], key="parallel-" + option["id"])
        except StudyError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = list(pool.map(submit, q["options"][:2]))
    saved = [o for o in outcomes if isinstance(o, dict)]
    assert len(saved) == 1 and "ATTEMPT_VERSION_CONFLICT" in outcomes
    assert saved[0]["choice_result"]["is_correct"] is (
        saved[0]["selected_option_id"] == q["correct_option_id"]
    )
    assert read(choice)["attempts"] == saved


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_id": 999},
        {"course_id": "other"},
        {"revision": 99},
        {"session_id": "other"},
        {"run_id": "other"},
        {"artifact_id": "other"},
    ],
)
def test_choice_save_history_and_read_preserve_owner_revision_and_parent_fences(choice, changes):
    with pytest.raises(StudyError):
        save(choice, "A", **changes)
    with pytest.raises(StudyError):
        read(choice, operation="ATTEMPT_HISTORY", question_index=0, **changes)
    assert read(choice)["attempts"] == []


def test_open_question_keeps_text_only_and_feedback_default_off(choice, monkeypatch):
    store, _, _, scope, private = choice
    monkeypatch.delenv("STUDY_FEEDBACK_ENABLED", raising=False)
    with pytest.raises(StudyError, match="OPEN_ANSWER_REQUIRES_TEXT"):
        save(choice, "A", question_index=1)
    opened = store.command(
        StudyCommand(
            **scope,
            operation="SAVE_ATTEMPT",
            question_index=1,
            answer_text="A stopping condition makes execution finite.",
            expected_version=0,
            request_key="open-answer",
        ),
        "mock",
    )["attempt"]
    assert "choice_result" not in opened and "selected_option_id" not in opened
    assert "correct_option_id" not in json.dumps(read(choice), default=str)
    answers = read(choice, operation="ANSWERS")["questions"]
    assert answers[1]["answer"] == private["questions"][1]["answer"]
    assert "correct_option_id" not in answers[0] and "answer" not in answers[0]
    assert read(choice)["feedback_enabled"] is False
    with pytest.raises(StudyError, match="FEEDBACK_DISABLED"):
        store.command(
            StudyCommand(
                **scope,
                operation="START_FEEDBACK",
                question_index=1,
                attempt_id=opened["attempt_id"],
                request_key="feedback",
            ),
            "mock",
        )


def test_choice_cannot_request_model_feedback_even_if_feedback_enabled(choice, monkeypatch):
    store, _, _, scope, private = choice
    monkeypatch.setenv("STUDY_FEEDBACK_ENABLED", "true")
    saved = save(choice, private["questions"][0]["correct_option_id"])
    with pytest.raises(StudyError, match="CHOICE_USES_PROGRAM_JUDGMENT"):
        store.command(
            StudyCommand(
                **scope,
                operation="START_FEEDBACK",
                question_index=0,
                attempt_id=saved["attempt_id"],
                request_key="feedback",
            ),
            "mock",
        )


def test_deleting_parent_cascades_immutable_choice_judgments(choice):
    store, _, _, scope, private = choice
    saved = save(choice, private["questions"][0]["correct_option_id"])
    with store.connect() as conn:
        conn.execute("DELETE FROM study_run WHERE run_id=%s", (scope["run_id"],))
        assert (
            conn.execute("SELECT 1 FROM study_attempt WHERE attempt_id=%s", (saved["attempt_id"],)).fetchone()
            is None
        )


def test_choice_start_replay_binds_format_and_never_runs_real_provider(setup):
    store, _, _, scope = setup
    cmd = StudyCommand(
        **scope,
        operation="START",
        goal="Compare with this course.",
        request_key="format",
        practice_format="choice",
    )
    for mode, approval in (("real", False), ("mock", True)):
        with pytest.raises(StudyError, match="CHOICE_MOCK_ONLY"):
            store.command(cmd.model_copy(update={"approval_required": approval}), mode)
    first = store.command(cmd, "mock")
    assert store.command(cmd, "mock")["run"]["run_id"] == first["run"]["run_id"]
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        store.command(cmd.model_copy(update={"practice_format": "open"}), "mock")
    with pytest.raises(StudyError, match="SESSION_BUSY"):
        store.command(cmd.model_copy(update={"request_key": "second"}), "mock")


def test_cancelled_choice_run_cannot_publish_and_keeps_budgets(setup):
    store, _, runtime, scope = setup
    started = store.command(
        StudyCommand(
            **scope,
            operation="START",
            goal="Course evidence",
            request_key="cancel-choice",
            practice_format="choice",
        ),
        "mock",
    )
    run = next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"])
    store.command(StudyCommand(**scope, operation="CANCEL", run_id=run["run_id"]), "mock")
    runtime.execute(run)
    result = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert result["run"]["status"] == "cancelled" and result["artifact"] is None
    assert result["run"]["model_calls"] == result["run"]["tool_calls"] == 0


def test_unsupported_key_or_foreign_citation_fails_without_publication(setup):
    store, _, runtime, scope = setup
    original = MockChoiceProvider()

    class BadProvider:
        def decide(self, messages, schemas, timeout):
            result = original.decide(messages, schemas, timeout)
            if result["name"] == "create_evidence_practice":
                result = copy.deepcopy(result)
                result["arguments"]["choice"]["correct_option_id"] = next(
                    o["id"]
                    for o in result["arguments"]["choice"]["options"]
                    if o["text"].startswith("本题没有")
                )
            return result

    runtime.choice_provider = BadProvider()
    started = store.command(
        StudyCommand(
            **scope,
            operation="START",
            goal="Course evidence",
            request_key="bad-key",
            practice_format="choice",
        ),
        "mock",
    )
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == started["run"]["run_id"]))
    result = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert result["run"]["status"] == "failed" and result["run"]["error_code"] == "CHOICE_KEY_NOT_GROUNDED"
    assert result["artifact"] is None


def test_choice_checkpoint_recovers_publication_once_without_repeating_model_calls(setup):
    from lecturelens_agent.study.store import RunStopped

    store, _, runtime, scope = setup
    original = store.save_tool
    interrupted = False

    def crash(*args, **kwargs):
        nonlocal interrupted
        result = original(*args, **kwargs)
        if kwargs.get("artifact") and not interrupted:
            interrupted = True
            raise RunStopped()
        return result

    store.save_tool = crash
    response = store.command(
        StudyCommand(
            **scope,
            operation="START",
            goal="Course evidence",
            request_key="recover",
            practice_format="choice",
        ),
        "mock",
    )
    queued = next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"])
    runtime.execute(queued)
    hidden = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert hidden["artifact"] is None and hidden["run"]["status"] == "running"
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == queued["run_id"]))
    recovered = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert recovered["run"]["status"] == "succeeded" and recovered["run"]["model_calls"] == 2
    assert recovered["artifact"]["questions"][0]["kind"] == "choice"
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM study_artifact WHERE run_id=%s", (queued["run_id"],)
            ).fetchone()["n"]
            == 1
        )


def test_cancellation_fences_a_choice_returned_by_an_inflight_mock(setup):
    store, _, runtime, scope = setup
    original = MockChoiceProvider()

    class Cancelling:
        def decide(self, messages, schemas, timeout):
            result = original.decide(messages, schemas, timeout)
            if result["name"] == "create_evidence_practice":
                store.command(StudyCommand(**scope, operation="CANCEL"), "mock")
            return result

    runtime.choice_provider = Cancelling()
    response = store.command(
        StudyCommand(
            **scope,
            operation="START",
            goal="Course evidence",
            request_key="inflight",
            practice_format="choice",
        ),
        "mock",
    )
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"]))
    result = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert result["run"]["status"] == "cancelled" and result["artifact"] is None


def test_no_course_evidence_stops_without_question_or_judgment(setup):
    store, authority, runtime, scope = setup
    original = authority.read
    authority.read = lambda context, action="CHECK", **args: (
        original(context, action, **args) | {"evidence": []}
    )
    response = store.command(
        StudyCommand(
            **scope,
            operation="START",
            goal="Unsupported material",
            request_key="empty",
            practice_format="choice",
        ),
        "mock",
    )
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"]))
    result = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert result["run"]["status"] == "succeeded"
    assert result["artifact"]["kind"] == "insufficient_evidence" and result["artifact"]["questions"] == []
    assert result["attempts"] == []


def test_choice_uses_persisted_budget_and_is_invisible_to_legacy_workers(setup):
    import psycopg

    store, _, runtime, scope = setup
    response = store.command(
        StudyCommand(
            **scope, operation="START", goal="Course evidence", request_key="budget", practice_format="choice"
        ),
        "mock",
    )
    queued = next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"])
    with store.connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM study_run WHERE run_id=%s AND status IN ('queued','running')", (queued["run_id"],)
        ).fetchone()
        conn.execute("UPDATE study_run SET model_calls=6 WHERE run_id=%s", (queued["run_id"],))
    with pytest.raises(psycopg.Error), store.connect() as conn:
        conn.execute("UPDATE study_run SET practice_format='open' WHERE run_id=%s", (queued["run_id"],))
    runtime.execute(queued)
    result = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert result["run"]["status"] == "budget_exceeded" and result["artifact"] is None
    assert result["run"]["model_calls"] == 6


def test_new_choice_runtime_cannot_inherit_the_frozen_p7_evaluation_identity():
    from lecturelens_agent.study.acceptance_cost import CostDenied, verify_development_agent

    # The immutable P7 manifest is not repinned to present this new runtime as that candidate.
    with pytest.raises(CostDenied, match="IDENTITY_CHANGED"):
        verify_development_agent()


def test_failed_event_commit_rolls_back_choice_and_judgment_together(choice, monkeypatch):
    store = choice[0]
    original = store._event

    def fail(conn, run_id, name, payload):
        if name == "attempt_saved":
            raise RuntimeError("synthetic commit failure")
        return original(conn, run_id, name, payload)

    monkeypatch.setattr(store, "_event", fail)
    with pytest.raises(RuntimeError, match="synthetic commit failure"):
        save(choice, choice[-1]["questions"][0]["correct_option_id"])
    assert read(choice)["attempts"] == []


def test_clients_cannot_supply_their_own_correct_key_or_grade(choice):
    store, _, _, scope, private = choice
    for forged in ({"correct_option_id": "A"}, {"choice_result": {"is_correct": True}}):
        with pytest.raises(ValueError):
            store.command(
                StudyCommand(
                    **scope,
                    operation="SAVE_ATTEMPT",
                    question_index=0,
                    request_key="forged",
                    expected_version=0,
                    selected_option_id=private["questions"][0]["correct_option_id"],
                    **forged,
                ),
                "mock",
            )
    assert read(choice)["attempts"] == []
