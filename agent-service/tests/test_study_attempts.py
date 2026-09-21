import json
from concurrent.futures import ThreadPoolExecutor

import pytest
import test_study
from pydantic import ValidationError
from test_study import read, start

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.store import StudyError, StudyStore

setup = test_study.setup


@pytest.fixture
def practice(setup):
    store, _, runtime, scope = setup
    runtime.execute(start(setup))
    result = read(setup)
    return store, scope | {
        "run_id": result["run"]["run_id"],
        "artifact_id": result["artifact"]["artifact_id"],
        "question_index": 0,
    }


def save(practice, key="answer-1", version=0, text="My actual answer", **changes):
    store, scope = practice
    return store.command(
        StudyCommand(
            **(
                scope
                | {
                    "operation": "SAVE_ATTEMPT",
                    "request_key": key,
                    "expected_version": version,
                    "answer_text": text,
                }
                | changes
            )
        ),
        "mock",
    )["attempt"]


def test_attempts_survive_restart_keep_history_and_never_reveal_reference_answers(practice):
    store, scope = practice
    first = save(practice)
    second = save(practice, "answer-2", 1, "My corrected answer")
    restarted = StudyStore(store.dsn)
    restarted.initialize()
    result = restarted.command(StudyCommand(**scope, operation="READ"), "mock")
    assert result["attempts"] == [second]
    assert "answer" not in result["artifact"]["questions"][0]
    history = store.command(StudyCommand(**scope, operation="ATTEMPT_HISTORY"), "mock")
    assert history["attempts"] == [second, first]
    assert history["next_before_version"] is None
    events = store.command(StudyCommand(**scope, operation="EVENTS"), "mock")["events"]
    assert "My actual answer" not in json.dumps(events)
    assert "My corrected answer" not in json.dumps(events)
    assert sum(e["event_type"] == "attempt_saved" for e in events) == 2


def test_retry_returns_original_even_after_a_later_revision(practice):
    first = save(practice)
    save(practice, "answer-2", 1, "Edited")
    assert save(practice) == first
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        save(practice, text="Different payload")
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        save(practice, version=2)
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        save(practice, question_index=1)


def test_concurrent_edits_never_silently_overwrite(practice):
    def attempt(key):
        try:
            return save(practice, key)["version"]
        except StudyError as error:
            return error.code

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(attempt, ["a", "b"]))
    assert sorted(map(str, results)) == ["1", "ATTEMPT_VERSION_CONFLICT"]


@pytest.mark.parametrize(
    "changes",
    [
        {"owner_id": 987654321},
        {"course_id": "another-course"},
        {"revision": 99},
        {"session_id": "another-session"},
        {"run_id": "another-run"},
        {"artifact_id": "another-artifact"},
    ],
)
def test_attempts_remain_bound_to_authorized_course_and_artifact(practice, changes):
    with pytest.raises(StudyError) as error:
        save(practice, **changes)
    assert error.value.status == 404


@pytest.mark.parametrize("text", ["", " \n\t", "a" * 4001])
def test_blank_and_oversized_answers_do_not_create_attempts(practice, text):
    with pytest.raises(ValidationError):
        save(practice, text=text)
    store, scope = practice
    assert store.command(StudyCommand(**scope, operation="READ"), "mock")["attempts"] == []


def test_history_is_bounded_and_paginated(practice):
    for version in range(23):
        save(practice, f"v{version}", version, f"answer {version}")
    store, scope = practice
    first = store.command(StudyCommand(**scope, operation="ATTEMPT_HISTORY"), "mock")
    assert len(first["attempts"]) == 20
    assert first["next_before_version"] == 4
    second = store.command(StudyCommand(**scope, operation="ATTEMPT_HISTORY", before_version=4), "mock")
    assert [row["version"] for row in second["attempts"]] == [3, 2, 1]
    assert second["next_before_version"] is None


def test_deleting_parent_artifact_cascades_all_answer_revisions(practice):
    saved = save(practice)
    store, scope = practice
    with store.connect() as conn:
        conn.execute("DELETE FROM study_run WHERE run_id=%s", (scope["run_id"],))
        assert (
            conn.execute("SELECT 1 FROM study_attempt WHERE attempt_id=%s", (saved["attempt_id"],)).fetchone()
            is None
        )


def test_questions_have_independent_versions_and_abstention_has_no_answer_slot(practice):
    first = save(practice)
    second = save(practice, "question-2", question_index=1)
    assert first["version"] == second["version"] == 1
    store, scope = practice
    with store.connect() as conn:
        conn.execute(
            "UPDATE study_artifact SET content=jsonb_set(content,'{questions}','[]') WHERE artifact_id=%s",
            (scope["artifact_id"],),
        )
    with pytest.raises(StudyError, match="QUESTION_NOT_FOUND"):
        save(practice, "absent")


def test_signed_http_attempt_write_rechecks_authority_and_redacts_invalid_input(practice, setup):
    import time
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from lecturelens_agent.app import create_app
    from lecturelens_agent.study.authority import COMMAND_PATH, signature

    store, scope = practice
    _, authority, runtime, _ = setup
    runtime.start = lambda: None
    secret = "study-attempt-http-test-secret-32-characters"
    retriever = SimpleNamespace(embedder=SimpleNamespace(index_version="test"))
    data = scope | {
        "operation": "SAVE_ATTEMPT",
        "request_key": "http",
        "expected_version": 0,
        "answer_text": "private learner response",
    }

    def send(client, value, signed=True):
        body = json.dumps(value).encode()
        timestamp = str(int(time.time()))
        headers = (
            {
                "X-LectureLens-Timestamp": timestamp,
                "X-LectureLens-Signature": signature(secret, timestamp, body, COMMAND_PATH),
            }
            if signed
            else {}
        )
        return client.post(COMMAND_PATH, content=body, headers=headers)

    with TestClient(create_app(retriever, secret, study_runtime=runtime)) as client:
        assert send(client, data, signed=False).status_code == 401
        assert send(client, data).status_code == 200
        invalid = send(client, data | {"answer_text": "sensitive-invalid-answer" * 300})
        assert invalid.status_code == 422
        assert "sensitive-invalid-answer" not in invalid.text
        authority.valid = False
        assert (
            send(client, data | {"request_key": "after-deletion", "expected_version": 1}).status_code == 409
        )
    assert len(store.command(StudyCommand(**scope, operation="ATTEMPT_HISTORY"), "mock")["attempts"]) == 1
