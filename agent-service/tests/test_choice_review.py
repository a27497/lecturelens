"""Real PG: latest submitted choice facts only, with owner/course/revision isolation."""

import uuid
from datetime import datetime

import pytest
import test_study_choices
from psycopg.types.json import Jsonb
from pydantic import ValidationError

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.store import StudyError

setup = test_study_choices.setup
choice = test_study_choices.choice
save = test_study_choices.save


def review(choice, **overrides):
    scope = {k: choice[3][k] for k in ("owner_id", "course_id", "revision")}
    return choice[0].command(StudyCommand(**(scope | overrides), operation="CHOICE_REVIEW"), "mock")


@pytest.fixture
def clone(choice):
    store, _, _, scope, content = choice
    sessions = []

    def create(**changes):
        ids = {key: str(uuid.uuid4()) for key in ("session_id", "run_id", "artifact_id")}
        target = scope | ids | changes
        sessions.append(target["session_id"])
        with store.connect() as conn:
            conn.execute(
                "INSERT INTO study_session(session_id,owner_id,course_id,revision) VALUES (%s,%s,%s,%s)",
                tuple(target[k] for k in ("session_id", "owner_id", "course_id", "revision")),
            )
            conn.execute(
                "INSERT INTO study_run(run_id,session_id,request_key,goal,status,model_mode,task_kind,practice_format) "
                "VALUES (%s,%s,'cloned','Synthetic review fixture','succeeded','mock','practice','choice')",
                (target["run_id"], target["session_id"]),
            )
            conn.execute(
                "INSERT INTO study_artifact(artifact_id,run_id,call_id,content) VALUES (%s,%s,'fixture',%s)",
                (target["artifact_id"], target["run_id"], Jsonb(content)),
            )
        copied = (store, choice[1], choice[2], target, content)
        save(copied, wrong_option(copied))
        return copied

    yield create
    with store.connect() as conn:
        for session in sessions:
            conn.execute("DELETE FROM study_run WHERE session_id=%s", (session,))
            conn.execute("DELETE FROM study_session WHERE session_id=%s", (session,))


def wrong_option(choice):
    question = choice[4]["questions"][0]
    return next(o["id"] for o in question["options"] if o["id"] != question["correct_option_id"])


def test_review_empty_unsubmitted_and_open_answers_are_not_judgments(choice):
    assert review(choice) == {
        "revision": 1,
        "correct_count": 0,
        "wrong_count": 0,
        "items": [],
        "next_after": None,
    }
    with pytest.raises((StudyError, ValidationError)):
        save(choice, None)
    store, _, _, scope, _ = choice
    store.command(
        StudyCommand(
            **scope,
            operation="SAVE_ATTEMPT",
            question_index=1,
            answer_text="Synthetic open answer",
            request_key="open",
            expected_version=0,
        ),
        "mock",
    )
    assert review(choice)["correct_count"] == review(choice)["wrong_count"] == 0
    assert review(choice)["items"] == []


def test_review_returns_traceable_public_question_and_only_saved_judgment(choice):
    saved = save(choice, wrong_option(choice))
    result = review(choice)
    assert result["correct_count"] == 0 and result["wrong_count"] == 1
    [item] = result["items"]
    assert item["session_id"] == choice[3]["session_id"]
    assert item["run_id"] == choice[3]["run_id"]
    assert item["artifact_id"] == saved["artifact_id"] and item["question_index"] == 0
    assert {k: v for k, v in item["attempt"].items() if k != "created_at"} == {
        k: v for k, v in saved.items() if k != "created_at"
    }
    assert datetime.fromisoformat(item["attempt"]["created_at"]) == saved["created_at"]
    assert item["question"] == {
        k: choice[4]["questions"][0][k] for k in ("kind", "question", "options", "evidence_ids")
    }
    assert "correct_option_id" not in item["question"]
    assert item["attempt"]["choice_result"]["citations"]


def test_latest_correct_version_removes_wrong_question_and_wrong_again_uses_latest(choice):
    save(choice, wrong_option(choice))
    assert review(choice)["wrong_count"] == 1
    correct = choice[4]["questions"][0]["correct_option_id"]
    save(choice, correct, version=1, key="correct-v2")
    result = review(choice)
    assert result["items"] == [] and result["wrong_count"] == 0 and result["correct_count"] == 1
    last = save(choice, wrong_option(choice), version=2, key="wrong-v3")
    result = review(choice)
    assert result["correct_count"] == 0 and result["wrong_count"] == 1
    assert result["items"][0]["attempt"]["attempt_id"] == last["attempt_id"]
    assert result["items"][0]["attempt"]["version"] == 3


def test_review_aggregates_across_sessions_without_creating_runs_or_model_calls(choice, clone):
    save(choice, wrong_option(choice))
    other = clone()

    def facts():
        with choice[0].connect() as conn:
            return conn.execute(
                "SELECT count(*) AS runs,sum(model_calls) AS models,sum(tool_calls) AS tools FROM study_run"
            ).fetchone()

    before = facts()
    result = review(choice)
    assert facts() == before
    assert result["wrong_count"] == 2
    assert {item["session_id"] for item in result["items"]} == {
        choice[3]["session_id"],
        other[3]["session_id"],
    }


@pytest.mark.parametrize("override", [{"owner_id": 43}, {"course_id": "other-course"}, {"revision": 2}])
def test_owner_course_revision_fences_prevent_record_and_count_disclosure(choice, override):
    save(choice, wrong_option(choice))
    result = review(choice, **override)
    assert result["items"] == [] and result["correct_count"] == result["wrong_count"] == 0


def test_other_scopes_do_not_inflate_current_course_counts(choice, clone):
    clone(owner_id=43)
    clone(course_id="another-course")
    clone(revision=2)
    assert review(choice)["items"] == []
    assert review(choice)["wrong_count"] == review(choice)["correct_count"] == 0


def test_bounded_pages_cover_every_latest_wrong_question_once(choice, clone):
    for _ in range(22):
        clone()
    first = review(choice)
    assert first["wrong_count"] == 22 and len(first["items"]) == 20 and first["next_after"] == 20
    second = review(choice, after=20)
    assert second["wrong_count"] == 22 and len(second["items"]) == 2 and second["next_after"] is None
    assert len({item["attempt"]["attempt_id"] for item in first["items"] + second["items"]}) == 22


@pytest.mark.parametrize("status", ["failed", "cancelled", "budget_exceeded"])
def test_unpublished_runs_do_not_contribute_review_items(choice, status):
    save(choice, wrong_option(choice))
    with choice[0].connect() as conn:
        conn.execute("UPDATE study_run SET status=%s WHERE run_id=%s", (status, choice[3]["run_id"]))
    assert review(choice)["items"] == [] and review(choice)["wrong_count"] == 0


def test_deleting_artifact_removes_its_review_record(choice):
    save(choice, wrong_option(choice))
    with choice[0].connect() as conn:
        conn.execute("DELETE FROM study_artifact WHERE artifact_id=%s", (choice[3]["artifact_id"],))
    assert review(choice)["items"] == [] and review(choice)["wrong_count"] == 0


def test_review_rejects_unbounded_offset_before_querying():
    with pytest.raises(ValidationError):
        StudyCommand(owner_id=42, course_id="course", revision=1, operation="CHOICE_REVIEW", after=2**63)


def test_review_runtime_has_independent_identity_and_cannot_claim_p9():
    from lecturelens_agent.study.acceptance_cost import CostDenied, verify_development_agent, verify_p9_agent

    assert verify_development_agent() == 63
    with pytest.raises(CostDenied, match="IDENTITY_CHANGED"):
        verify_p9_agent()
