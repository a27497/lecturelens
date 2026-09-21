import json
import os
import threading
import uuid

import pytest
from langgraph.checkpoint.postgres import PostgresSaver

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyError, StudyStore


class Authority:
    def __init__(self):
        self.valid = True
        self.reads = []

    def read(self, scope, action="CHECK", **arguments):
        if not self.valid:
            raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED")
        self.reads.append(action)
        ids = arguments.get("evidence_ids", ["e1", "e2"])
        return {k: scope[k] for k in ("owner_id", "course_id", "revision")} | {
            "evidence": []
            if action == "CHECK"
            else [
                {
                    "evidence_id": key,
                    "text": "An algorithm needs a stopping condition.",
                    "start_ms": i * 1000,
                    "end_ms": (i + 1) * 1000,
                    "source_type": "SUBTITLE",
                }
                for i, key in enumerate(ids)
            ]
        }


@pytest.fixture
def setup():
    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Real PostgreSQL required")
    store = StudyStore(dsn)
    authority = Authority()
    runtime = StudyRuntime(store, authority, MockProvider())
    runtime.initialize()
    scope = dict(owner_id=42, course_id="study-test-" + uuid.uuid4().hex, revision=1)
    session = store.command(
        StudyCommand(**scope, operation="CREATE_SESSION", request_key="session-key"), "mock"
    )["session_id"]
    scope["session_id"] = session
    yield store, authority, runtime, scope
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.delete_thread(session)
    with store.connect() as conn:
        conn.execute("DELETE FROM study_run WHERE session_id=%s", (session,))
        conn.execute("DELETE FROM study_session WHERE session_id=%s", (session,))


def start(setup, key="run-key"):
    store, _, _, scope = setup
    response = store.command(
        StudyCommand(**scope, operation="START", request_key=key, goal="解释停止条件并出两道题"), "mock"
    )
    return next(row for row in store.candidates() if row["run_id"] == response["run"]["run_id"])


def read(setup, operation="READ"):
    store, _, _, scope = setup
    return store.command(StudyCommand(**scope, operation=operation), "mock")


def test_session_and_run_idempotency_with_one_active_run(setup):
    store, _, _, scope = setup
    duplicate = {k: v for k, v in scope.items() if k != "session_id"}
    assert (
        store.command(
            StudyCommand(**duplicate, operation="CREATE_SESSION", request_key="session-key"), "mock"
        )["session_id"]
        == scope["session_id"]
    )
    assert start(setup)["run_id"] == start(setup)["run_id"]
    with pytest.raises(StudyError, match="SESSION_BUSY"):
        start(setup, "other-key")
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        store.command(
            StudyCommand(**scope, operation="START", request_key="run-key", goal="different"), "mock"
        )


def test_explain_practice_persists_events_citations_and_hides_answers(setup):
    store, authority, runtime, _ = setup
    runtime.execute(start(setup))
    response = read(setup)
    assert response["run"]["status"] == "succeeded"
    assert response["run"]["model_calls"] == 4 and response["run"]["tool_calls"] == 3
    assert response["artifact"]["revision"] == 1 and len(response["artifact"]["questions"]) == 2
    assert all(
        "answer" not in q and "rubric" not in q and "answer_points" not in q
        for q in response["artifact"]["questions"]
    )
    assert read(setup, "ANSWERS")["questions"][0]["answer"]
    events = read(setup, "EVENTS")["events"]
    assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
    assert sum(e["event_type"] == "artifact_created" for e in events) == 1
    assert events[-1]["payload"]["status"] == "succeeded"
    assert "SEARCH" in authority.reads and "WINDOW" in authority.reads
    assert "An algorithm" not in json.dumps(events)


def test_insufficient_evidence_is_a_persisted_outcome_without_fake_practice(setup):
    _, _, runtime, _ = setup
    original = runtime.provider.decide

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        if context["history"]:
            return {
                "name": "report_insufficient_evidence",
                "arguments": {"reason": "The retrieved course does not describe the requested topic."},
            }
        return original(messages, timeout)

    runtime.provider.decide = decide
    runtime.execute(start(setup))
    result = read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["artifact"]["kind"] == "insufficient_evidence"
    assert result["artifact"]["questions"] == result["artifact"]["citations"] == []
    assert read(setup, "ANSWERS")["questions"] == []
    events = read(setup, "EVENTS")["events"]
    assert sum(event["event_type"] == "model_finished" for event in events) == 3
    assert all(
        event["payload"]["duration_ms"] >= 0 for event in events if event["event_type"] == "model_finished"
    )


def test_insufficient_evidence_cannot_skip_search(setup):
    _, _, runtime, _ = setup
    runtime.provider.decide = lambda *_: {
        "name": "report_insufficient_evidence",
        "arguments": {"reason": "There is not enough evidence for this topic."},
    }
    runtime.execute(start(setup))
    assert read(setup)["run"]["error_code"] == "SEARCH_REQUIRED"


def test_invented_unrequested_time_filter_cannot_hide_course_evidence(setup):
    _, authority, runtime, _ = setup
    original_decide, original_read = runtime.provider.decide, authority.read
    searches = []

    def decide(messages, timeout):
        result = original_decide(messages, timeout)
        if result["name"] == "search_course_evidence":
            result["arguments"].update(start_ms=1633500000000, end_ms=1633510000000)
        return result

    def evidence(scope, action="CHECK", **arguments):
        if action == "SEARCH":
            searches.append(arguments)
        return original_read(scope, action, **arguments)

    runtime.provider.decide, authority.read = decide, evidence
    runtime.execute(start(setup))
    assert read(setup)["run"]["status"] == "succeeded"
    assert searches and all(
        "start_ms" not in arguments and "end_ms" not in arguments for arguments in searches
    )


class Crash(BaseException):
    pass


def test_crash_after_artifact_commit_before_checkpoint_does_not_duplicate(setup):
    store, authority, runtime, _ = setup
    run = start(setup)
    original = store.save_tool

    def crash_after_commit(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[3] == "create_practice_set":
            raise Crash()
        return result

    store.save_tool = crash_after_commit
    with pytest.raises(Crash):
        runtime.execute(run)
    store.save_tool = original
    assert read(setup)["run"]["status"] == "running"
    StudyRuntime(StudyStore(store.dsn), authority, MockProvider()).execute(run)
    response = read(setup)
    assert response["run"]["status"] == "succeeded"
    assert response["run"]["model_calls"] == 4 and response["run"]["tool_calls"] == 3
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM study_artifact WHERE run_id=%s", (run["run_id"],)
            ).fetchone()["n"]
            == 1
        )
    assert any(e["event_type"] == "run_resumed" for e in read(setup, "EVENTS")["events"])


def test_cancel_during_model_io_fences_late_result(setup):
    store, _, runtime, scope = setup
    entered, release = threading.Event(), threading.Event()
    original = runtime.provider.decide

    def slow(*args):
        entered.set()
        assert release.wait(5)
        return original(*args)

    runtime.provider.decide = slow
    run = start(setup)
    worker = threading.Thread(target=runtime.execute, args=(run,))
    worker.start()
    try:
        assert entered.wait(5)
        command = StudyCommand(**scope, operation="CANCEL", run_id=run["run_id"])
        assert store.command(command, "mock")["run"]["status"] == "cancelled"
        assert store.command(command, "mock")["run"]["status"] == "cancelled"
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive()
    assert read(setup)["artifact"] is None and read(setup)["run"]["tool_calls"] == 0
    runtime.provider.decide = original
    runtime.execute(start(setup, "after-cancel"))
    assert read(setup)["run"]["status"] == "succeeded"
    assert read(setup)["run"]["run_id"] != run["run_id"]


def test_worker_lock_prevents_overlapping_checkpoints(setup):
    store, _, runtime, scope = setup
    run = start(setup)
    with store.execution_lock(scope["session_id"]) as acquired:
        assert acquired
        runtime.execute(run)
        assert read(setup)["run"]["status"] == "queued"
    runtime.execute(run)
    assert read(setup)["run"]["status"] == "succeeded"


@pytest.mark.parametrize(
    "fault", ["unknown", "repeated", "forged_citation", "provider_failure", "source_change"]
)
def test_model_tool_and_source_failures_are_explicit(setup, fault):
    _, authority, runtime, _ = setup
    original = runtime.provider.decide

    def decide(messages, timeout):
        if fault == "unknown":
            return {"name": "shell", "arguments": {}}
        if fault == "repeated":
            return {"name": "search_course_evidence", "arguments": {"query": "same query"}}
        if fault == "provider_failure":
            raise RuntimeError("secret-provider-key")
        if fault == "source_change":
            authority.valid = False
        result = original(messages, timeout)
        if fault == "forged_citation" and result["name"] == "create_practice_set":
            result["arguments"]["questions"][0]["evidence_ids"] = ["foreign-course"]
        return result

    runtime.provider.decide = decide
    runtime.execute(start(setup))
    response = read(setup)
    assert response["run"]["status"] == "failed" and response["artifact"] is None
    assert "secret-provider-key" not in json.dumps(response, default=str)


@pytest.mark.parametrize("counter", ["model_calls", "tool_calls", "reserved_tokens", "deadline"])
def test_budget_is_not_reset_on_recovery(setup, counter):
    store, _, runtime, _ = setup
    run = start(setup)
    assignment = {
        "model_calls": "model_calls=6",
        "tool_calls": "tool_calls=8",
        "reserved_tokens": "reserved_tokens=64000",
        "deadline": "deadline=now()-interval '1 second'",
    }[counter]
    with store.connect() as conn:
        conn.execute(f"UPDATE study_run SET {assignment} WHERE run_id=%s", (run["run_id"],))
    runtime.execute(run)
    assert read(setup)["run"]["status"] == "budget_exceeded" and read(setup)["artifact"] is None


def test_owner_course_revision_and_session_scope(setup):
    store, _, _, scope = setup
    run = start(setup)
    for field, value in [
        ("owner_id", 99),
        ("course_id", "other"),
        ("revision", 2),
        ("session_id", "missing"),
    ]:
        with pytest.raises(StudyError):
            store.command(
                StudyCommand(**(scope | {field: value}), operation="READ", run_id=run["run_id"]), "mock"
            )


def test_event_cursor_replays_only_new_events(setup):
    store, _, runtime, scope = setup
    runtime.execute(start(setup))
    events = read(setup, "EVENTS")["events"]
    tail = store.command(StudyCommand(**scope, operation="EVENTS", after=events[2]["sequence"]), "mock")[
        "events"
    ]
    assert tail == events[3:]


def test_next_run_has_its_own_artifact(setup):
    _, _, runtime, _ = setup
    runtime.execute(start(setup))
    first = read(setup)["artifact"]["artifact_id"]
    runtime.execute(start(setup, "second"))
    assert read(setup)["run"]["status"] == "succeeded" and read(setup)["artifact"]["artifact_id"] != first


def test_delete_sync_purges_artifacts_and_framework_checkpoints(setup):
    from lecturelens_agent.contracts import SyncRequest
    from lecturelens_agent.store import VectorStore

    store, _, runtime, scope = setup
    runtime.execute(start(setup))
    vectors = VectorStore(store.dsn)
    vectors.initialize()
    vectors.delete(
        SyncRequest(
            request_id="delete",
            owner_id=scope["owner_id"],
            course_id=scope["course_id"],
            revision=1,
            sequence=1,
            operation="DELETE",
        ),
        "test",
    )
    runtime.purge_deleted()
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM study_session WHERE session_id=%s", (scope["session_id"],)
            ).fetchone()["n"]
            == 0
        )
        assert (
            conn.execute(
                "SELECT count(*) AS n FROM checkpoints WHERE thread_id=%s", (scope["session_id"],)
            ).fetchone()["n"]
            == 0
        )
        conn.execute(
            "DELETE FROM evidence_index WHERE owner_id=%s AND course_id=%s",
            (scope["owner_id"], scope["course_id"]),
        )


def test_http_study_context_signature_and_scope(setup):
    import time
    from types import SimpleNamespace

    from fastapi.testclient import TestClient

    from lecturelens_agent.app import create_app
    from lecturelens_agent.app import signature as retrieval_signature
    from lecturelens_agent.study.authority import COMMAND_PATH, signature

    _, _, runtime, scope = setup
    runtime.start = lambda: None
    secret = "test-study-context-only-32-byte-secret"
    body = StudyCommand(**scope, operation="READ").model_dump_json().encode()
    timestamp = str(int(time.time()))
    headers = {
        "X-LectureLens-Timestamp": timestamp,
        "X-LectureLens-Signature": signature(secret, timestamp, body, COMMAND_PATH),
    }
    with TestClient(create_app(SimpleNamespace(), secret, runtime)) as client:
        response = client.post(COMMAND_PATH, content=body, headers=headers)
        assert response.status_code == 200 and response.json()["run"] is None
        assert response.json()["owner_id"] == scope["owner_id"]
        headers["X-LectureLens-Signature"] = retrieval_signature(secret, timestamp, body, COMMAND_PATH)
        assert client.post(COMMAND_PATH, content=body, headers=headers).status_code == 401


def _crash_worker(dsn, run):
    import signal

    store = StudyStore(dsn)
    runtime = StudyRuntime(store, Authority(), MockProvider())
    original = store.save_tool

    def kill_after_commit(*args, **kwargs):
        result = original(*args, **kwargs)
        if args[3] == "create_practice_set":
            os.kill(os.getpid(), signal.SIGKILL)
        return result

    store.save_tool = kill_after_commit
    runtime.execute(run)


def test_process_kill_releases_lock_and_resumes_without_duplicate_artifact(setup):
    import multiprocessing
    import signal

    store, _, runtime, _ = setup
    run = start(setup)
    process = multiprocessing.get_context("spawn").Process(target=_crash_worker, args=(store.dsn, run))
    process.start()
    process.join(timeout=15)
    try:
        assert process.exitcode == -signal.SIGKILL
        runtime.execute(run)
        assert read(setup)["run"]["status"] == "succeeded"
        with store.connect() as conn:
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM study_artifact WHERE run_id=%s", (run["run_id"],)
                ).fetchone()["n"]
                == 1
            )
    finally:
        if process.is_alive():
            process.kill()
            process.join()


def test_model_receives_standard_tool_messages_but_checkpoint_keeps_refs(setup):
    store, _, runtime, scope = setup
    recorded = []
    original = runtime.provider.decide

    def record(messages, timeout):
        recorded.append(messages)
        return original(messages, timeout)

    runtime.provider.decide = record
    runtime.execute(start(setup))
    assert read(setup)["run"]["status"] == "succeeded"
    assert [message["role"] for message in recorded[1]] == ["system", "user", "assistant", "tool"]
    assert recorded[1][-1]["tool_call_id"] == recorded[1][-2]["tool_calls"][0]["id"]
    assert json.loads(recorded[1][-1]["content"])["evidence"]
    with PostgresSaver.from_conn_string(store.dsn) as saver:
        state = saver.get_tuple({"configurable": {"thread_id": scope["session_id"]}}).checkpoint[
            "channel_values"
        ]
    assert "An algorithm needs a stopping condition." not in json.dumps(state, default=str)


def test_recovery_cannot_change_real_mock_mode(setup):
    _, _, runtime, _ = setup
    run = start(setup)
    runtime.provider.mode = "real"
    runtime.execute(run)
    assert read(setup)["run"]["error_code"] == "MODEL_MODE_CHANGED"


def test_multiple_model_tool_calls_execute_serially_with_individual_checkpoints(setup):
    _, _, runtime, _ = setup
    original = runtime.provider.decide

    def batch(messages, timeout):
        context = json.loads(messages[-1]["content"])
        if context["evidence"] and not any(
            item["tool"] == "read_evidence_window" for item in context["history"]
        ):
            return {
                "calls": [
                    {"name": "read_evidence_window", "arguments": {"evidence_id": item["evidence_id"]}}
                    for item in context["evidence"][:2]
                ]
            }
        return original(messages, timeout)

    runtime.provider.decide = batch
    runtime.execute(start(setup))
    response = read(setup)
    assert response["run"]["status"] == "succeeded"
    assert response["run"]["model_calls"] == 4 and response["run"]["tool_calls"] == 4
    names = [
        e["payload"].get("tool")
        for e in read(setup, "EVENTS")["events"]
        if e["event_type"] == "tool_finished"
    ]
    assert names == [
        "search_course_evidence",
        "read_evidence_window",
        "read_evidence_window",
        "create_practice_set",
    ]


def repair_provider(runtime, accept_second=True):
    original = runtime.provider.decide
    reviews, observations = [], []

    def decide(messages, timeout):
        result = original(messages, timeout)
        context = json.loads(messages[-1]["content"])
        if context.get("quality"):
            observations.append(context["quality"])
            result["arguments"]["title"] = "Revised candidate"
        return result

    def review(messages, timeout):
        reviews.append(json.loads(messages[-1]["content"]))
        return {
            "review": {
                "issues": [] if accept_second and len(reviews) == 2 else ["incorrect_answer"],
                "feedback": "PRIVATE CRITIQUE: correct the example result before saving.",
                "grounds": {
                    "question_1": [
                        {"source": "question_1.answer", "quote": "PRIVATE QUOTED ANSWER"},
                        {"source": "e1", "quote": "PRIVATE QUOTED EVIDENCE"},
                    ]
                }
                if not (accept_second and len(reviews) == 2)
                else {},
                "answer_observations": [
                    {
                        "field": "question_1",
                        "expected_answer": "PRIVATE COMPUTED ANSWER",
                        "matches_reference": False,
                        "grounds": [{"source": "e1", "quote": "PRIVATE ANSWER EVIDENCE"}],
                    }
                ],
                "rubric_observations": [
                    {
                        "field": "question_1",
                        "status": "needs_verification",
                        "question": {"source": "question_1.question", "quote": "PRIVATE RULE QUESTION"},
                        "answer": {"source": "question_1.answer", "quote": "PRIVATE RULE ANSWER"},
                        "rules": [
                            {"source": "question_1.rubric", "quote": "PRIVATE RULE CLAUSE", "result": "unmet"}
                        ],
                    }
                ]
                if not (accept_second and len(reviews) == 2)
                else [],
            }
        }

    runtime.provider.decide, runtime.provider.review = decide, review
    return reviews, observations


def test_rejected_draft_becomes_observation_then_repaired_artifact(setup):
    _, _, runtime, _ = setup
    reviews, observations = repair_provider(runtime)
    runtime.execute(start(setup))
    result = read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == 6  # search, window, draft, review, repair, review
    assert result["artifact"]["title"] == "Revised candidate"
    assert len(reviews) == 2 and len(observations) == 1
    assert observations[0]["issues"] == ["incorrect_answer"]
    assert observations[0]["grounds"]["question_1"][0]["quote"] == "PRIVATE QUOTED ANSWER"
    assert observations[0]["rubric_observations"][0]["rules"][0]["result"] == "unmet"
    assert observations[0]["answer_observations"][0]["expected_answer"] == "PRIVATE COMPUTED ANSWER"
    assert reviews[0]["candidate"]["questions"][0]["answer"]
    assert reviews[0]["evidence"][0]["text"] == "An algorithm needs a stopping condition."
    events = read(setup, "EVENTS")["events"]
    assert [e["payload"]["accepted"] for e in events if e["event_type"] == "quality_checked"] == [False, True]
    assert sum(e["event_type"] == "artifact_created" for e in events) == 1
    assert "PRIVATE CRITIQUE" not in json.dumps(events) + json.dumps(result, default=str)
    assert "PRIVATE QUOTED" not in json.dumps(events) + json.dumps(result, default=str)
    assert "PRIVATE RULE" not in json.dumps(events) + json.dumps(result, default=str)
    assert "PRIVATE COMPUTED" not in json.dumps(events) + json.dumps(result, default=str)
    assert "PRIVATE ANSWER" not in json.dumps(events) + json.dumps(result, default=str)


def test_two_rejected_drafts_end_without_publishing_or_false_abstention(setup):
    _, _, runtime, _ = setup
    reviews, _ = repair_provider(runtime, accept_second=False)
    runtime.execute(start(setup))
    result = read(setup)
    assert result["run"]["error_code"] == "QUALITY_REPAIR_EXHAUSTED"
    assert result["artifact"] is None and len(reviews) == 2
    assert not any(e["event_type"] == "artifact_created" for e in read(setup, "EVENTS")["events"])


def test_rejection_quote_provenance_is_stored_with_canonical_evidence_id(setup):
    store, authority, runtime, _ = setup
    original = authority.read

    def canonical_read(*args, **kwargs):
        result = original(*args, **kwargs)
        for item in result["evidence"]:
            if item["evidence_id"] in {"e1", "e2"}:
                item["evidence_id"] = "canonical-" + item["evidence_id"]
        return result

    authority.read = canonical_read
    _, observations = repair_provider(runtime)
    run = start(setup)
    runtime.execute(run)
    assert read(setup)["run"]["status"] == "succeeded"
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s", (run["run_id"],)
        ).fetchall()
    quality = next(
        row["result"]["quality"] for row in rows if row["result"].get("quality", {}).get("accepted") is False
    )
    assert quality["grounds"]["question_1"][1]["source"] == "canonical-e1"
    assert quality["answer_observations"][0]["grounds"][0]["source"] == "canonical-e1"
    assert observations[0]["answer_observations"][0]["grounds"][0]["source"] == "e1"
    assert observations[0]["grounds"]["question_1"][1]["source"] == "e1"


def test_rejected_review_commit_replays_without_repeat_model_call(setup):
    store, authority, runtime, _ = setup
    reviews, observations = repair_provider(runtime)
    original = store.save_tool

    def crash(*args, **kwargs):
        result = original(*args, **kwargs)
        if "quality" in result:
            raise Crash()
        return result

    store.save_tool = crash
    run = start(setup)
    with pytest.raises(Crash):
        runtime.execute(run)
    assert read(setup)["artifact"] is None
    store.save_tool = original
    StudyRuntime(store, authority, runtime.provider).execute(run)
    assert read(setup)["run"]["status"] == "succeeded"
    assert read(setup)["run"]["model_calls"] == 6
    assert len(reviews) == 2 and len(observations) == 1
    assert observations[0]["grounds"]["question_1"][1]["quote"] == "PRIVATE QUOTED EVIDENCE"
    assert observations[0]["rubric_observations"][0]["answer"]["quote"] == "PRIVATE RULE ANSWER"
    assert observations[0]["answer_observations"][0]["expected_answer"] == "PRIVATE COMPUTED ANSWER"


@pytest.mark.parametrize("failure", ["cancel", "revision", "budget", "malformed"])
def test_review_cannot_publish_after_stop_or_invalid_result(setup, failure):
    store, authority, runtime, scope = setup

    def review(messages, timeout):
        if failure == "cancel":
            store.command(StudyCommand(**scope, operation="CANCEL"), "mock")
        elif failure == "revision":
            authority.valid = False
        elif failure == "budget":
            with store.connect() as conn:
                conn.execute(
                    "UPDATE study_run SET deadline=now()-interval '1 second' WHERE session_id=%s",
                    (scope["session_id"],),
                )
        return {
            "review": {"issues": ["invented_code"] if failure == "malformed" else [], "feedback": "checked"}
        }

    runtime.provider.review = review
    runtime.execute(start(setup))
    response = read(setup)
    assert response["artifact"] is None
    assert response["run"]["status"] == {"cancel": "cancelled", "budget": "budget_exceeded"}.get(
        failure, "failed"
    )


def test_false_abstention_feedback_can_lead_to_grounded_practice(setup):
    _, _, runtime, _ = setup
    observed = []

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        if not context["history"]:
            return {"name": "search_course_evidence", "arguments": {"query": "stopping condition"}}
        if not context.get("quality"):
            return {
                "name": "report_insufficient_evidence",
                "arguments": {"reason": "The passages do not support the learner goal."},
            }
        observed.append(context["quality"])
        context["history"].append({"tool": "read_evidence_window"})
        return MockProvider().decide([{"content": json.dumps(context)}], timeout)

    def review(messages, timeout):
        candidate = json.loads(messages[-1]["content"])["candidate"]
        return {
            "review": {
                "issues": ["unjustified_abstention"] if candidate["kind"] == "insufficient_evidence" else [],
                "feedback": "The passage explicitly describes a stopping condition; address that goal.",
            }
        }

    runtime.provider.decide, runtime.provider.review = decide, review
    runtime.execute(start(setup))
    response = read(setup)
    assert response["run"]["status"] == "succeeded" and response["run"]["model_calls"] == 5
    assert response["artifact"]["kind"] == "practice"
    assert observed[0]["issues"] == ["unjustified_abstention"]


@pytest.mark.parametrize("repair", [True, False])
def test_inline_citation_mismatch_returns_bounded_repair_observation(setup, repair):
    _, _, runtime, _ = setup
    original = runtime.provider.decide
    observations, reviews = [], []

    def decide(messages, timeout):
        call = original(messages, timeout)
        context = json.loads(messages[-1]["content"])
        if call["name"] == "create_practice_set":
            quality = context.get("quality")
            if quality:
                observations.append(quality)
                call["arguments"]["title"] = "Second candidate"
            call["arguments"]["explanation"] = "A stopping condition is needed." + (
                "" if quality and repair else " [e2]"
            )
            call["arguments"]["evidence_ids"] = ["e1"]
        return call

    def review(messages, timeout):
        reviews.append(messages)
        return {"review": {"issues": [], "feedback": "OK"}}

    runtime.provider.decide, runtime.provider.review = decide, review
    runtime.execute(start(setup))
    result = read(setup)
    assert observations[0]["issues"] == ["citation_mismatch"]
    assert len(reviews) == (1 if repair else 0)
    assert result["run"]["status"] == ("succeeded" if repair else "failed")
    if not repair:
        assert result["run"]["error_code"] == "QUALITY_REPAIR_EXHAUSTED"
        assert result["artifact"] is None
    events = read(setup, "EVENTS")["events"]
    checks = [e["payload"] for e in events if e["event_type"] == "quality_checked"]
    assert checks[0]["source"] == "citation_check" and not checks[0]["accepted"]
    assert "Fields:" not in json.dumps(events)


def test_failed_review_event_records_usage_without_private_response(setup):
    from lecturelens_agent.study.provider import ModelResponseError

    _, _, runtime, _ = setup

    def review(messages, timeout):
        raise ModelResponseError(
            "MODEL_REVIEW_CONTRACT",
            {"prompt_tokens": 42, "completion_tokens": 12},
            {"stage": "review_schema", "validation": [{"field": "issues", "type": "literal_error"}]},
        )

    runtime.provider.review = review
    runtime.execute(start(setup))
    result = read(setup)
    assert result["run"]["error_code"] == "MODEL_REVIEW_CONTRACT"
    assert result["artifact"] is None
    failed = [e for e in read(setup, "EVENTS")["events"] if e["event_type"] == "model_failed"]
    assert len(failed) == 2
    assert all(e["payload"]["purpose"] == "review" for e in failed)
    assert all(e["payload"]["completion_tokens"] == 12 for e in failed)


@pytest.mark.parametrize("always_fail", [False, True])
@pytest.mark.parametrize("failure_code", ["MODEL_TOOL_CONTRACT", "MODEL_OUTPUT_TRUNCATED"])
def test_tool_format_retry_is_visible_counted_and_bounded(setup, always_fail, failure_code):
    from lecturelens_agent.study.provider import ModelResponseError

    _, _, runtime, _ = setup
    original = runtime.provider.decide
    calls = []

    def decide(messages, timeout):
        calls.append(messages)
        if len(calls) == 1 or always_fail:
            raise ModelResponseError(
                failure_code,
                {"prompt_tokens": 8, "completion_tokens": 3},
                {"stage": "tool_contract", "reason": "arguments_json"},
            )
        if messages[-1]["role"] == "user" and "NO tools" in messages[-1]["content"]:
            messages = messages[:-1]
        return original(messages, timeout)

    runtime.provider.decide = decide
    runtime.execute(start(setup))
    response = read(setup)
    events = read(setup, "EVENTS")["events"]
    assert sum(e["event_type"] == "protocol_retry_scheduled" for e in events) == 1
    assert "NO tools" in calls[1][-1]["content"]
    assert response["run"]["model_calls"] == (2 if always_fail else 5)
    assert response["run"]["status"] == ("failed" if always_fail else "succeeded")
    if always_fail:
        assert response["artifact"] is None and response["run"]["tool_calls"] == 0


def test_failed_model_usage_counts_without_relabeling_the_call_successful():
    import importlib.util
    from pathlib import Path

    path = Path(__file__).resolve().parents[2] / "scripts/eval/report-study.py"
    spec = importlib.util.spec_from_file_location("failed_usage_report", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    row = {
        "case_id": "bad",
        "run": {"status": "failed", "model_calls": 1},
        "artifact": None,
        "elapsed_seconds": 2,
        "events": [
            {"event_type": "model_failed", "payload": {"prompt_tokens": 10, "completion_tokens": 300}}
        ],
    }
    result = module.summarize([{"id": "bad", "expected_outcome": "practice"}], [row], {})
    assert result["reported_completion_tokens"] == 300
    assert result["model_calls_without_complete_usage"] == 0
    assert not result["passed"] and result["status_counts"] == {"failed": 1}


@pytest.mark.parametrize("repair", [True, False])
def test_code_format_observation_drives_revision_without_executing_snippets(setup, repair):
    _, _, runtime, _ = setup
    original = runtime.provider.decide
    observations = []

    def decide(messages, timeout):
        call = original(messages, timeout)
        context = json.loads(messages[-1]["content"])
        if call["name"] == "create_practice_set":
            quality = context.get("quality")
            call["arguments"]["explanation"] = "A stopping condition is needed." + (
                "" if quality and repair else " [e2]"
            )
            call["arguments"]["evidence_ids"] = ["e1"]
            if quality:
                observations.append(quality)
                call["arguments"]["title"] = "Revised example"
            call["arguments"]["questions"][1]["question"] = (
                "What prints?\n```python\ndef f():\n    print('hello')\nf()\n```"
                if quality and repair
                else "What prints?\\ndef f():\\n    print('hello')\\nf()"
            )
        return call

    runtime.provider.decide = decide
    runtime.execute(start(setup))
    response = read(setup)
    assert observations[0]["issues"] == ["invalid_code", "citation_mismatch"]
    assert "question_2_question" in observations[0]["feedback"]
    assert response["run"]["status"] == ("succeeded" if repair else "failed")
    if not repair:
        assert response["run"]["error_code"] == "QUALITY_REPAIR_EXHAUSTED"
        assert response["artifact"] is None
    events = read(setup, "EVENTS")["events"]
    checks = [e["payload"] for e in events if e["event_type"] == "quality_checked"]
    assert checks[0]["source"] == "code_format_check"
    assert "question_2_question" not in json.dumps(events)


def test_inline_definition_is_review_observation_not_automatic_rejection(setup):
    _, _, runtime, _ = setup
    decide_original, review_original = runtime.provider.decide, runtime.provider.review
    observed = []

    def decide(messages, timeout):
        call = decide_original(messages, timeout)
        if call["name"] == "create_practice_set":
            call["arguments"]["questions"][1]["question"] = (
                "Given def f(): print('hello'), what does f return?"
            )
        return call

    def review(messages, timeout):
        observed.extend(json.loads(messages[-1]["content"])["code_observations"])
        return review_original(messages, timeout)

    runtime.provider.decide, runtime.provider.review = decide, review
    runtime.execute(start(setup))
    assert read(setup)["run"]["status"] == "succeeded"
    assert {"field": "question_2_question", "kind": "inline_definition"} in observed


@pytest.mark.parametrize("repeat_failure", [False, True])
def test_review_format_retry_keeps_candidate_charges_budget_and_is_bounded(setup, repeat_failure):
    store, _, runtime, _ = setup
    from lecturelens_agent.study.provider import ModelResponseError

    original = runtime.provider.review
    inputs = []

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        inputs.append(body)
        if len(inputs) == 1 or repeat_failure:
            raise ModelResponseError(
                "MODEL_REVIEW_CONTRACT",
                {"prompt_tokens": 100, "completion_tokens": 20},
                {"stage": "review_schema"},
            )
        return original(messages, timeout)

    runtime.provider.review = review
    run = start(setup)
    runtime.execute(run)
    result = read(setup)
    assert len(inputs) == 2
    assert inputs[0]["candidate"] == inputs[1]["candidate"]
    assert inputs[0]["evidence"] == inputs[1]["evidence"]
    assert "protocol_feedback" not in inputs[0]
    assert inputs[1]["protocol_feedback"]["error"] == "MODEL_REVIEW_CONTRACT"
    assert result["run"]["model_calls"] == 5
    if repeat_failure:
        assert result["run"]["status"] == "failed"
        assert result["run"]["error_code"] == "MODEL_REVIEW_CONTRACT"
        assert result["artifact"] is None
    else:
        assert result["run"]["status"] == "succeeded"
        assert "protocol_feedback" not in json.dumps(result["artifact"])
    with store.connect() as conn:
        failures = conn.execute(
            "SELECT payload FROM study_event WHERE run_id=%s AND event_type='model_failed'", (run["run_id"],)
        ).fetchall()
    assert len(failures) == (2 if repeat_failure else 1)
