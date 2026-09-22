import json

import pytest
import test_study
import test_study_attempts

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.store import BudgetExceeded, RunStopped, StudyError

setup = test_study.setup
practice = test_study_attempts.practice


@pytest.fixture
def feedback(practice, setup, monkeypatch):
    monkeypatch.setenv("STUDY_FEEDBACK_ENABLED", "true")
    store, scope = practice
    _, authority, runtime, _ = setup
    attempt = test_study_attempts.save(practice, text="It stops automatically.")
    command = StudyCommand(
        **scope, operation="START_FEEDBACK", request_key="feedback-1", attempt_id=attempt["attempt_id"]
    )
    calls = []

    def respond(messages, schemas, timeout, *, review=False):
        body = json.loads(messages[-1]["content"])
        calls.append((review, body))
        if review:
            return test_study.MockProvider().feedback(messages, schemas, timeout, review=True)
        if not body["observations"]:
            return {"calls": [{"name": "read_question_evidence", "arguments": {}}]}
        return {
            "calls": [
                {
                    "name": "submit_answer_feedback",
                    "arguments": {
                        "observations": [
                            {
                                "learner_quote": "It stops automatically.",
                                "observation": "Make the stopping condition explicit.",
                                "action": "clarify",
                                "evidence_ids": [body["evidence"][0]["evidence_id"]],
                            }
                        ]
                    },
                }
            ]
        }

    runtime.provider.feedback = respond
    response = store.command(command, "mock")
    run = next(row for row in store.candidates() if row["run_id"] == response["run"]["run_id"])
    return store, scope, runtime, authority, attempt, command, run, calls


def view(feedback):
    store, scope, _, _, _, _, run, _ = feedback
    return store.command(StudyCommand(**(scope | {"run_id": run["run_id"]}), operation="READ"), "mock")


def test_stalled_basis_retries_within_persisted_budget_and_still_reviews(feedback):
    store, _, runtime, _, _, _, run, calls = feedback
    original = runtime.provider.feedback
    stalled = False
    timeouts = []

    def transient(messages, schemas, timeout, *, review=False):
        nonlocal stalled
        timeouts.append(timeout)
        if schemas[0]["function"]["name"] == "derive_feedback_basis" and not stalled:
            stalled = True
            raise BudgetExceeded()
        return original(messages, schemas, timeout, review=review)

    runtime.provider.feedback = transient
    runtime.execute(run)
    result = view(feedback)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == 5
    assert result["feedback"] is not None
    assert all(0 < value <= 20 for value in timeouts)
    assert any(review and "candidate" in body for review, body in calls)
    with store.connect() as conn:
        failed = conn.execute(
            "SELECT payload FROM study_event WHERE run_id=%s AND event_type='model_failed'", (run["run_id"],)
        ).fetchall()
    assert [row["payload"]["error_code"] for row in failed] == ["MODEL_TIMEOUT"]


def test_repeated_transport_timeout_stops_after_one_retry_without_feedback(feedback):
    _, _, runtime, _, _, _, run, _ = feedback

    def unavailable(*args, **kwargs):
        raise StudyError("MODEL_UNAVAILABLE")

    runtime.provider.feedback = unavailable
    runtime.execute(run)
    result = view(feedback)
    assert result["run"]["model_calls"] == 2
    assert result["run"]["error_code"] == "MODEL_UNAVAILABLE"
    assert result["feedback"] is None


def test_feedback_is_separate_from_answer_and_is_recovered_with_parent_practice(feedback):
    store, scope, runtime, _, attempt, command, run, calls = feedback
    runtime.execute(run)
    result = view(feedback)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == 4
    assert result["run"]["tool_calls"] == 2
    assert result["feedback"]["attempt_id"] == attempt["attempt_id"]
    assert result["feedback"]["answer_text"] == "It stops automatically."
    assert result["feedback"]["content"]["observations"][0]["evidence_id"] == "e1"
    parent = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert parent["attempts"] == [attempt]
    assert parent["feedback_runs"][0]["feedback"] == result["feedback"]
    assert store.command(command, "mock")["run"]["run_id"] == run["run_id"]
    assert len(calls) == 4
    for _, body in calls:
        assert set(body["question"]) == {"question", "evidence_ids"}
    basis_body = next(body for review, body in calls if review and "candidate" not in body)
    assert set(basis_body) == {"question", "evidence"}
    review_body = next(body for review, body in calls if review and "candidate" in body)
    assert {e["evidence_id"] for e in review_body["evidence"]} == {"e1", "e2"}
    latest = store.command(
        StudyCommand(
            **{k: scope[k] for k in ("owner_id", "course_id", "revision", "session_id")}, operation="READ"
        ),
        "mock",
    )
    assert latest["run"]["run_id"] == scope["run_id"]
    events = store.command(StudyCommand(**(scope | {"run_id": run["run_id"]}), operation="EVENTS"), "mock")[
        "events"
    ]
    assert "It stops automatically" not in json.dumps(events)
    assert "stopping condition" not in json.dumps(events)


def test_feedback_is_disabled_by_default_and_cannot_invent_an_answer(practice, monkeypatch):
    store, scope = practice
    monkeypatch.delenv("STUDY_FEEDBACK_ENABLED", raising=False)
    command = StudyCommand(**scope, operation="START_FEEDBACK", request_key="missing", attempt_id="not-saved")
    with pytest.raises(StudyError, match="FEEDBACK_DISABLED"):
        store.command(command, "mock")
    monkeypatch.setenv("STUDY_FEEDBACK_ENABLED", "true")
    with pytest.raises(StudyError, match="ATTEMPT_NOT_FOUND"):
        store.command(command, "mock")


def test_model_cannot_smuggle_new_facts_into_the_generated_action_instruction(feedback):
    _, _, runtime, _, _, _, run, _ = feedback
    original = runtime.provider.feedback

    def extra_instruction(messages, schemas, timeout, *, review=False):
        result = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return result
        call = result["calls"][0]
        if call["name"] == "submit_answer_feedback":
            call["arguments"]["observations"][0]["next_step"] = "Invent an unrelated course fact."
        return result

    runtime.provider.feedback = extra_instruction
    runtime.execute(run)
    assert view(feedback)["run"]["error_code"] == "INVALID_TOOL_ARGUMENTS"
    assert view(feedback)["feedback"] is None


def test_citation_context_fills_observed_gaps_without_crossing_modality():
    from lecturelens_agent.study.feedback import observation_quotes

    evidence = [
        {
            "evidence_id": f"s{i}",
            "text": f"Original {i}",
            "source_type": "SUBTITLE",
            "start_ms": i * 1000,
            "end_ms": (i + 1) * 1000,
        }
        for i in range(7)
    ]
    evidence.append(
        {
            "evidence_id": "frame",
            "text": "Different modality",
            "source_type": "FRAME",
            "start_ms": 3000,
            "end_ms": 4000,
        }
    )
    rows = observation_quotes([{"evidence_ids": ["s2", "s4"], "action": "retain"}], evidence)
    assert rows[0]["anchor_evidence_ids"] == ["s2", "s4"]
    assert rows[0]["evidence_ids"] == [f"s{i}" for i in range(7)]
    assert rows[0]["evidence_quote"] == "\n\n".join(f"Original {i}" for i in range(7))


def test_compound_feedback_preserves_all_selected_quotes_and_review_bindings(feedback):
    _, _, runtime, authority, _, _, run, calls = feedback
    original = runtime.provider.feedback
    read = authority.read

    def sources(*args, **kwargs):
        result = read(*args, **kwargs)
        for item in result["evidence"]:
            if item["evidence_id"] == "e2":
                item["text"] = "Stop when no candidates remain."
        return result

    authority.read = sources

    def compound(messages, schemas, timeout, *, review=False):
        result = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return result
        call = result["calls"][0]
        if call["name"] == "submit_answer_feedback":
            call["arguments"]["observations"][0]["evidence_ids"] = ["e1", "e2"]
        return result

    runtime.provider.feedback = compound
    runtime.execute(run)
    result = view(feedback)
    assert result["run"]["status"] == "succeeded"
    observation = result["feedback"]["content"]["observations"][0]
    assert observation["evidence_ids"] == ["e1", "e2"]
    assert observation["evidence_quote"] == (
        "An algorithm needs a stopping condition.\n\nStop when no candidates remain."
    )
    reviewed = next(body for review, body in calls if review and "candidate" in body)
    assert {e["evidence_id"] for e in reviewed["evidence"]} == {"e1", "e2"}


@pytest.mark.parametrize("covers,faithful", [(False, True), (True, True), (False, False)])
def test_abstention_review_distinguishes_unsupported_topic_from_bad_abstention(feedback, covers, faithful):
    _, _, runtime, _, _, _, run, _ = feedback
    original = runtime.provider.feedback

    def abstain(messages, schemas, timeout, *, review=False):
        response = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return response
        call = response["calls"][0]
        if review:
            assert call["name"] == "review_feedback_insufficiency"
            call["arguments"].update(course_covers_topic=covers, reason_faithful=faithful)
        elif call["name"] == "submit_answer_feedback":
            call.update(name="report_feedback_insufficient", arguments={"reason": "The topic is absent."})
        return response

    runtime.provider.feedback = abstain
    runtime.execute(run)
    result = view(feedback)
    if not covers and faithful:
        assert result["run"]["status"] == "succeeded"
        assert result["feedback"]["content"]["kind"] == "insufficient_evidence"
    else:
        assert result["run"]["error_code"] == "FEEDBACK_REPAIR_EXHAUSTED"
        assert result["feedback"] is None


@pytest.mark.parametrize("fail_feedback", [False, True])
def test_practice_after_feedback_uses_fresh_graph_state_in_same_session(feedback, setup, fail_feedback):
    store, scope, runtime, _, _, _, run, _ = feedback
    if fail_feedback:

        def broken(*args, **kwargs):
            raise StudyError("MODEL_UNAVAILABLE")

        runtime.provider.feedback = broken
    runtime.execute(run)
    previous = view(feedback)
    assert previous["run"]["status"] == ("failed" if fail_feedback else "succeeded")
    next_run = test_study.start(setup, key="practice-after-feedback")
    runtime.execute(next_run)
    latest = test_study.read(setup)
    assert latest["run"]["status"] == "succeeded"
    assert latest["run"]["run_id"] == next_run["run_id"]
    assert latest["artifact"]["artifact_id"] != scope["artifact_id"]
    assert latest["run"]["model_calls"] == 4
    assert latest["attempts"] == [] and latest["feedback_runs"] == []
    assert view(feedback)["feedback"] == previous["feedback"]


def test_feedback_notes_are_versioned_and_do_not_rewrite_the_model_or_learner(feedback):
    store, scope, runtime, _, attempt, _, run, _ = feedback
    runtime.execute(run)
    original = view(feedback)["feedback"]
    args = scope | {
        "run_id": run["run_id"],
        "feedback_id": original["feedback_id"],
        "operation": "SAVE_FEEDBACK_NOTE",
        "request_key": "note-1",
        "expected_version": 0,
        "disposition": "disputed",
        "note_text": "I already named the condition in my example.",
    }
    first = store.command(StudyCommand(**args), "mock")["note"]
    assert store.command(StudyCommand(**args), "mock")["note"] == first
    with pytest.raises(StudyError, match="FEEDBACK_VERSION_CONFLICT"):
        store.command(StudyCommand(**(args | {"request_key": "note-stale"})), "mock")
    second = store.command(
        StudyCommand(
            **(
                args
                | {
                    "request_key": "note-2",
                    "expected_version": 1,
                    "disposition": "acknowledged",
                    "note_text": "After rereading I want to clarify it.",
                }
            )
        ),
        "mock",
    )["note"]
    result = view(feedback)["feedback"]
    assert result["content"] == original["content"]
    assert result["answer_text"] == attempt["answer_text"]
    assert result["note"] == second
    history = store.command(
        StudyCommand(
            **(scope | {"run_id": run["run_id"]}),
            operation="FEEDBACK_NOTES",
            feedback_id=original["feedback_id"],
        ),
        "mock",
    )
    assert history["notes"] == [second, first]


@pytest.mark.parametrize("kind", ["learner", "evidence", "review"])
def test_feedback_rejects_fabricated_quotes(feedback, kind):
    _, _, runtime, _, _, _, run, _ = feedback
    original = runtime.provider.feedback

    def malformed(messages, schemas, timeout, *, review=False):
        response = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return response
        call = response["calls"][0]
        if kind == "review" and review:
            call["arguments"]["checks"][0]["evidence_ids"] = ["fabricated"]
        elif kind != "review" and not review and call["name"] == "submit_answer_feedback":
            call["arguments"]["observations"][0]["learner_quote" if kind == "learner" else "evidence_ids"] = (
                "fabricated" if kind == "learner" else ["fabricated"]
            )
        return response

    runtime.provider.feedback = malformed
    runtime.execute(run)
    assert view(feedback)["run"]["status"] == "failed"
    assert view(feedback)["feedback"] is None


def test_rejection_observation_changes_next_candidate_within_persistent_budget(feedback):
    _, _, runtime, _, _, _, run, calls = feedback
    original = runtime.provider.feedback
    reviews = 0

    def revise(messages, schemas, timeout, *, review=False):
        nonlocal reviews
        response = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return response
        if review:
            reviews += 1
            if reviews == 1:
                response["calls"][0]["arguments"]["checks"][0].update(
                    next_step_verdict="reject", reason="Make the suggestion more specific"
                )
        elif response["calls"][0]["name"] == "submit_answer_feedback":
            body = json.loads(messages[-1]["content"])
            if body["observations"][-1]["result"].get("issues"):
                response["calls"][0]["arguments"]["observations"][0]["observation"] = (
                    "Name when the algorithm stops."
                )
        return response

    runtime.provider.feedback = revise
    runtime.execute(run)
    result = view(feedback)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == len(calls) == 6
    assert result["feedback"]["content"]["observations"][0]["observation"] == "Name when the algorithm stops."


def test_feedback_reserves_final_two_calls_for_revision(feedback):
    _, _, runtime, _, _, _, run, calls = feedback
    original = runtime.provider.feedback
    reviews = 0

    def revise(messages, schemas, timeout, *, review=False):
        nonlocal reviews
        response = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return response
        body = json.loads(messages[-1]["content"])
        if review:
            reviews += 1
            if reviews == 1:
                response["calls"][0]["arguments"]["checks"][0].update(
                    observation_verdict="reject", reason="Explain the stopping condition"
                )
            return response
        names = {s["function"]["name"] for s in schemas}
        if body["observations"]:
            assert "read_question_evidence" not in names
            assert body["independent_course_basis"]["explanation"]
        if body["latest_review"]:
            assert body["latest_review"]["issues"][0]["reason"] == "Explain the stopping condition"
            assert body["budget"]["model_calls_remaining"] == 2
            assert names == {"submit_answer_feedback", "report_feedback_insufficient"}
            response["calls"][0]["arguments"]["observations"][0]["observation"] = (
                "State the condition that ends the algorithm."
            )
        elif body["observations"]:
            assert body["budget"]["model_calls_remaining"] == 4
            assert "read_feedback_window" in names
        return response

    runtime.provider.feedback = revise
    runtime.execute(run)
    result = view(feedback)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == len(calls) == 6
    assert reviews == 2
    assert result["feedback"]["content"]["observations"][0]["observation"] == (
        "State the condition that ends the algorithm."
    )


def test_window_keeps_independent_basis_without_another_derivation(feedback):
    _, _, runtime, _, _, _, run, calls = feedback
    original = runtime.provider.feedback
    window = False

    def expand(messages, schemas, timeout, *, review=False):
        nonlocal window
        response = original(messages, schemas, timeout, review=review)
        if not review and response["calls"][0]["name"] == "submit_answer_feedback" and not window:
            window = True
            return {"calls": [{"name": "read_feedback_window", "arguments": {"evidence_id": "e1"}}]}
        return response

    runtime.provider.feedback = expand
    runtime.execute(run)
    assert view(feedback)["run"]["status"] == "succeeded"
    assert len(calls) == 5
    basis_calls = [body for review, body in calls if review and "candidate" not in body]
    assert len(basis_calls) == 1
    assert set(basis_calls[0]) == {"question", "evidence"}
    after_window = next(
        body
        for review, body in calls
        if not review and body["observations"] and body["observations"][-1]["tool"] == "read_feedback_window"
    )
    assert after_window["independent_course_basis"]["explanation"]


def test_feedback_checkpoint_replay_does_not_repeat_completed_model_work(feedback, monkeypatch):
    store, _, runtime, _, _, _, run, calls = feedback
    save = store.save_tool
    interrupted = False

    def crash(*args, **kwargs):
        nonlocal interrupted
        result = save(*args, **kwargs)
        if kwargs.get("feedback") is not None and not interrupted:
            interrupted = True
            raise RunStopped()
        return result

    monkeypatch.setattr(store, "save_tool", crash)
    runtime.execute(run)
    assert view(feedback)["run"]["status"] == "running"
    assert view(feedback)["feedback"] is None
    runtime.execute(run)
    assert view(feedback)["run"]["status"] == "succeeded"
    assert len(calls) == 4
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM study_feedback WHERE run_id=%s", (run["run_id"],)
            ).fetchone()["n"]
            == 1
        )


@pytest.mark.parametrize("failure", ["cancel", "version", "budget"])
def test_late_feedback_is_not_published_after_stop_conditions(feedback, failure):
    store, scope, runtime, authority, _, _, run, _ = feedback
    original = runtime.provider.feedback

    def stop(messages, schemas, timeout, *, review=False):
        response = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return response
        if review:
            if failure == "cancel":
                store.command(StudyCommand(**(scope | {"run_id": run["run_id"]}), operation="CANCEL"), "mock")
            elif failure == "version":
                authority.valid = False
            else:
                with store.connect() as conn:
                    conn.execute(
                        "UPDATE study_run SET deadline=now()-interval '1 second' WHERE run_id=%s",
                        (run["run_id"],),
                    )
        return response

    runtime.provider.feedback = stop
    runtime.execute(run)
    assert (
        view(feedback)["run"]["status"]
        == {"cancel": "cancelled", "version": "failed", "budget": "budget_exceeded"}[failure]
    )
    assert view(feedback)["feedback"] is None


def test_new_answer_never_relabels_feedback_for_the_old_answer(feedback, practice):
    _, _, runtime, _, first, _, run, _ = feedback
    second = test_study_attempts.save(practice, "revised-answer", 1, "A precise condition")
    runtime.execute(run)
    assert view(feedback)["feedback"]["attempt_id"] == first["attempt_id"]
    assert second["attempt_id"] != first["attempt_id"]


def test_course_deletion_cascades_feedback_and_correction_records(feedback):
    store, scope, runtime, _, _, _, run, _ = feedback
    runtime.execute(run)
    fid = view(feedback)["feedback"]["feedback_id"]
    store.command(
        StudyCommand(
            **(scope | {"run_id": run["run_id"]}),
            operation="SAVE_FEEDBACK_NOTE",
            feedback_id=fid,
            request_key="note",
            expected_version=0,
            disposition="disputed",
            note_text="Please check",
        ),
        "mock",
    )
    with store.connect() as conn:
        conn.execute("DELETE FROM study_run WHERE run_id=%s", (scope["run_id"],))
        assert conn.execute("SELECT 1 FROM study_feedback WHERE feedback_id=%s", (fid,)).fetchone() is None
        assert (
            conn.execute("SELECT 1 FROM study_feedback_note WHERE feedback_id=%s", (fid,)).fetchone() is None
        )
        assert conn.execute("SELECT 1 FROM study_run WHERE run_id=%s", (run["run_id"],)).fetchone() is None


def test_two_rejected_drafts_stop_without_spending_a_third_decision(feedback):
    _, _, runtime, _, _, _, run, calls = feedback
    original = runtime.provider.feedback

    def reject(messages, schemas, timeout, *, review=False):
        response = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return response
        if review:
            response["calls"][0]["arguments"]["checks"][0].update(
                next_step_verdict="reject", reason="unsupported suggestion"
            )
        return response

    runtime.provider.feedback = reject
    runtime.execute(run)
    assert view(feedback)["run"]["error_code"] == "FEEDBACK_REPAIR_EXHAUSTED"
    assert len(calls) == 6
    assert view(feedback)["feedback"] is None


@pytest.mark.parametrize("invalid", ["missing", "duplicate", "unseen_source"])
def test_structured_review_must_check_every_observation_with_its_own_source(feedback, invalid):
    _, _, runtime, _, _, _, run, _ = feedback
    original = runtime.provider.feedback

    def malformed(messages, schemas, timeout, *, review=False):
        response = original(messages, schemas, timeout, review=review)
        if schemas[0]["function"]["name"] == "derive_feedback_basis":
            return response
        if review:
            checks = response["calls"][0]["arguments"]["checks"]
            if invalid == "missing":
                checks.clear()
            elif invalid == "duplicate":
                checks.append(dict(checks[0]))
            else:
                checks[0]["evidence_ids"] = ["e2"]
        return response

    runtime.provider.feedback = malformed
    runtime.execute(run)
    assert view(feedback)["run"]["status"] == "failed"
    assert view(feedback)["feedback"] is None


@pytest.mark.parametrize("change", [{"owner_id": 777777}, {"revision": 999}, {"course_id": "other"}])
def test_feedback_and_corrections_are_owner_and_revision_scoped(feedback, change):
    store, scope, runtime, _, _, command, run, _ = feedback
    runtime.execute(run)
    with pytest.raises(StudyError) as error:
        store.command(StudyCommand(**(command.model_dump() | change)), "mock")
    assert error.value.status == 404
    fid = view(feedback)["feedback"]["feedback_id"]
    with pytest.raises(StudyError) as error:
        store.command(
            StudyCommand(
                **(scope | {"run_id": run["run_id"]} | change),
                operation="SAVE_FEEDBACK_NOTE",
                feedback_id=fid,
                request_key="unauthorized",
                expected_version=0,
                disposition="disputed",
                note_text="mine",
            ),
            "mock",
        )
    assert error.value.status == 404
