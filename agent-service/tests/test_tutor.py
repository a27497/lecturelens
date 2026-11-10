"""Tutor mechanisms on real isolated PostgreSQL. Never a real provider."""

import json
import os
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor.contracts import ABSTENTION, Command
from lecturelens_real_eval.tutor.runtime import MAX_SEARCH_CALLS, MockTutor, TutorRuntime
from lecturelens_real_eval.tutor.store import TutorStore


class Authority:
    def __init__(self, scope):
        self.scope, self.valid, self.empty, self.missing = scope, True, False, False
        self.searches = []

    def read(self, scope, action="CHECK", **args):
        if not self.valid or any(scope[k] != self.scope[k] for k in ("owner_id", "course_id", "revision")):
            raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED", 404)
        rows = [
            {
                "evidence_id": "e1",
                "text": "BFS levels give shortest path distances in edges.",
                "start_ms": 1000,
                "end_ms": 2000,
                "source_type": "SUBTITLE",
            }
        ]
        if action == "SEARCH":
            self.searches.append(args["query"])
        if action == "CHECK" or self.empty or (self.missing and action == "READ"):
            rows = []
        return {**self.scope, "evidence": rows}


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = socket.socket.connect

    def local(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
            raise AssertionError("Tutor tests forbid external network")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local)


@pytest.fixture
def lab():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "tutor_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    store = TutorStore(make_conninfo(dsn, options=f"-csearch_path={schema},public"))
    scope = dict(owner_id=801, course_id="tutor-" + uuid.uuid4().hex, revision=1)
    authority = Authority(scope.copy())
    runtime = TutorRuntime(store, authority)
    runtime.initialize()
    session = runtime.command(Command(**scope, operation="CREATE", request_key="s"))["session"]
    scope["session_id"] = session["session_id"]
    yield store, authority, runtime, scope
    runtime.close()
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def command(lab, operation, **kw):
    return lab[2].command(Command(**{**lab[3], "operation": operation, **kw}))


def submit(lab, key="turn-1", text="Explain BFS levels", socratic=False):
    return command(lab, "TURN", client_turn_id=key, text=text, socratic=socratic)


def run(lab, key="turn-1", text="Explain BFS levels", socratic=False):
    submit(lab, key, text, socratic)
    lab[2].execute(lab[0].candidates()[0])
    return command(lab, "GET")["turns"][-1]


def test_persistence_multiturn_citations_and_idempotent_submit(lab):
    first = run(lab)
    assert first["outcome"] == "answered" and "[e1]" in first["answer"]
    assert first["citations"] == lab[1].read(lab[3], "READ")["evidence"]
    assert first["model_calls"] == 2 and first["tool_calls"] == 2
    assert len(first["usage"]) == 2
    replay = submit(lab)
    assert replay["replayed"] and replay["turns"] == command(lab, "GET")["turns"]
    second = run(lab, "t2", "Why is that?")
    assert second["outcome"] == "answered"
    assert "Explain BFS levels" in lab[1].searches[-1]
    restored = TutorRuntime(TutorStore(lab[0].dsn), lab[1])
    assert restored.command(Command(**lab[3], operation="GET"))["turns"][-1] == second
    assert command(lab, "LIST")["sessions"][0]["model_calls"] == 4


def test_same_client_id_changed_text_or_mode_conflicts(lab):
    submit(lab)
    for kw in ({"text": "changed"}, {"socratic": True}):
        with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
            submit(lab, **kw)
    with pytest.raises(StudyError, match="SESSION_BUSY"):
        submit(lab, key="other")


@pytest.mark.parametrize("same_key", [True, False])
def test_concurrent_submission_one_effect(lab, same_key):
    barrier = threading.Barrier(2)

    def send(i):
        barrier.wait()
        try:
            return submit(lab, key="same" if same_key else str(i))
        except StudyError as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        result = list(pool.map(send, [0, 1]))
    if same_key:
        assert sorted(r["replayed"] for r in result) == [False, True]
    else:
        assert result.count("SESSION_BUSY") == 1
    assert len(command(lab, "GET")["turns"]) == 1


@pytest.mark.parametrize("change", [{"owner_id": 999}, {"course_id": "other"}])
def test_ownership_at_authority_and_pg(lab, change):
    with pytest.raises(StudyError, match="COURSE_UNAVAILABLE"):
        command(lab, "GET", **change)
    with pytest.raises(StudyError, match="SESSION_NOT_FOUND"):
        lab[0].command(Command(**{**lab[3], **change}, operation="GET"))


def test_revision_marks_stale_and_prevents_read_and_submission(lab):
    run(lab)
    lab[1].scope["revision"] = 2
    with pytest.raises(StudyError, match="SESSION_STALE"):
        command(lab, "GET", revision=2)
    with lab[0].connect() as conn:
        assert conn.execute("SELECT status FROM tutor_session").fetchone()["status"] == "stale"
    with pytest.raises(StudyError, match="SESSION_STALE"):
        command(lab, "TURN", revision=2, client_turn_id="new", text="why?")


def test_revision_change_during_model_never_publishes(lab):
    original = lab[2].provider.decide

    def change(*args):
        response = original(*args)
        if response["name"] == "finish_tutor_turn":
            lab[1].valid = False
        return response

    lab[2].provider.decide = change
    submit(lab)
    lab[2].execute(lab[0].candidates()[0])
    with lab[0].connect() as conn:
        row = conn.execute("SELECT * FROM tutor_turn").fetchone()
        assert row["outcome"] == "failed" and row["answer"] is None and row["citations"] == []
        assert conn.execute("SELECT status FROM tutor_session").fetchone()["status"] == "stale"


@pytest.mark.parametrize("bad", ["invented", "wrong_inline", "missing", "unobserved", "evaluation"])
def test_invalid_citations_reject_answer_and_preserve_failed_proposal(lab, bad):
    original = lab[2].provider.decide

    def invalid(*args):
        response = original(*args)
        if response["name"] == "finish_tutor_turn":
            if bad == "missing":
                lab[1].missing = True
            elif bad == "wrong_inline":
                response["arguments"]["text"] = "A claim [e2]"
            elif bad == "unobserved":
                response["arguments"].update(evidence_ids=["e2"], text="A claim [e2]")
            elif bad == "evaluation":
                response["arguments"]["evaluation"] = "A claim [e2]"
            else:
                response["arguments"]["evidence_ids"] = ["fake"]
                response["arguments"]["text"] = "A claim [fake]"
        return response

    lab[2].provider.decide = invalid
    result = run(lab)
    assert result["outcome"] == "failed" and result["answer"] is None and not result["citations"]
    assert result["error_code"] == "TUTOR_CITATION_MISMATCH"
    with lab[0].connect() as conn:
        assert (
            conn.execute("SELECT checkpoint FROM tutor_turn").fetchone()["checkpoint"]["phase"] == "received"
        )


@pytest.mark.parametrize("bad", ["undeclared_inline", "duplicate", "evaluation_inline"])
def test_legacy_declarations_are_ignored_without_repair(lab, bad):
    original = lab[2].provider.decide

    def invalid_once(messages, *args):
        response = original(messages, *args)
        observations = json.loads(messages[-1]["content"])["observations"]
        if response["name"] == "finish_tutor_turn" and len(observations) == 1:
            if bad == "duplicate":
                response["arguments"]["evidence_ids"] = ["e1", "e1"]
            else:
                response["arguments"]["evidence_ids"] = []
                if bad == "evaluation_inline":
                    response["arguments"].update(
                        text="Compare with the course.", evaluation="BFS levels [e1]."
                    )
        return response

    lab[2].provider.decide = invalid_once
    result = run(lab)
    assert result["status"] == "completed" and result["tool_calls"] == result["model_calls"] == 2


@pytest.mark.parametrize("bad", ["citation", "evaluation"])
def test_unrepaired_finish_exhausts_budget_without_publication(lab, bad):
    if bad == "evaluation":
        run(lab, socratic=True)
    original = lab[2].provider.decide

    def invalid(messages, *args):
        response = original(messages, *args)
        if response["name"] == "finish_tutor_turn":
            if bad == "citation":
                response["arguments"]["text"] = "Missing inline citation."
            else:
                response["arguments"]["evaluation"] = " "
        return response

    lab[2].provider.decide = invalid
    result = run(lab, "unrepaired")
    assert result["status"] == "failed"
    assert result["error_code"] == (
        "TUTOR_CITATION_MISMATCH" if bad == "citation" else "TUTOR_BUDGET_EXHAUSTED"
    )
    assert result["answer"] is None and not result["citations"]
    assert result["model_calls"] == (2 if bad == "citation" else 4)
    assert result["tool_calls"] == (1 if bad == "citation" else 4)
    with lab[0].connect() as conn:
        state = conn.execute("SELECT checkpoint FROM tutor_turn ORDER BY ordinal DESC LIMIT 1").fetchone()[
            "checkpoint"
        ]
    assert len([o for o in state["observations"] if "error" in o]) == (0 if bad == "citation" else 3)


@pytest.mark.parametrize("empty", [False, True])
def test_search_limit_forces_finish_and_rejects_ignored_limit(lab, empty):
    lab[1].empty = empty
    original = lab[2].provider.decide
    calls = []

    def repeat(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        calls.append([s["function"]["name"] for s in schemas])
        if len(calls) <= 3:
            if len(calls) == 3:
                assert calls[-1] == ["finish_tutor_turn"]
                assert data["search_calls_remaining"] == 0
            return {"name": "search_tutor_evidence", "arguments": {"query": "BFS"}}
        assert data["observations"][-1]["error"] == "TUTOR_SEARCH_LIMIT_REACHED"
        assert data["evidence"] == ([] if empty else lab[1].read(lab[3], "READ")["evidence"])
        return original(messages, schemas, timeout)

    lab[2].provider.decide = repeat
    result = run(lab)
    assert result["status"] == "completed" and result["tool_calls"] == result["model_calls"] == 4
    assert len(lab[1].searches) == 2
    assert result["outcome"] == ("insufficient_evidence" if empty else "answered")


def test_missing_socratic_evaluation_observation_and_repair(lab):
    run(lab, socratic=True)
    original = lab[2].provider.decide
    repairs = []

    def omit_once(messages, *args):
        data = json.loads(messages[-1]["content"])
        assert data["evaluation_required"] is True
        response = original(messages, *args)
        if response["name"] == "finish_tutor_turn":
            if len(data["observations"]) == 1:
                response["arguments"]["evaluation"] = " "
            else:
                observation = data["observations"][-1]
                assert observation["error"] == "TUTOR_EVALUATION_REQUIRED"
                assert "non-empty evaluation" in observation["message"]
                repairs.append(observation)
        return response

    lab[2].provider.decide = omit_once
    result = run(lab, "reply", "One BFS level per step", socratic=True)
    assert result["status"] == "completed" and result["tool_calls"] == result["model_calls"] == 3
    assert result["evaluation"].strip() and "[e1]" in result["evaluation"] and repairs
    assert "?" in result["answer"]


def test_socratic_without_guiding_question_remains_fatal_after_repair(lab):
    original = lab[2].provider.decide

    def invalid(messages, *args):
        response = original(messages, *args)
        if response["name"] == "finish_tutor_turn":
            response["arguments"]["text"] = "BFS levels [e1]."
        return response

    lab[2].provider.decide = invalid
    result = run(lab, socratic=True)
    assert result["error_code"] == "TUTOR_SOCRATIC_CONTRACT" and result["answer"] is None


def test_exact_failed_live_answer_accepts_math_brackets_and_rereads_authority(lab):
    from lecturelens_real_eval.runner import SnapshotAuthority

    root = Path(__file__).resolve().parents[2]
    proposal = json.loads((Path(__file__).parent / "fixtures/p8_adjacency_answer.json").read_text())
    authority = SnapshotAuthority(json.loads((root / "eval/p7-real/snapshot.json").read_text()))
    authority.register(lab[3], "algorithms-l1")
    lab[2].authority = authority
    reads = []
    original = authority.read

    def capture(scope, action="CHECK", **args):
        if action == "READ":
            reads.append(args["evidence_ids"])
        return original(scope, action, **args)

    authority.read = capture

    def decide(messages, schemas, timeout):
        if not json.loads(messages[-1]["content"])["observations"]:
            return {
                "name": "search_tutor_evidence",
                "arguments": {"query": "graph adjacency list representation"},
            }
        return {"name": "finish_tutor_turn", "arguments": proposal}

    lab[2].provider.decide = decide
    result = run(lab)
    assert result["status"] == "completed" and result["outcome"] == "answered"
    assert result["answer"] == proposal["text"] and "Adj[u]" in result["answer"]
    assert {c["evidence_id"] for c in result["citations"]} == set(proposal["evidence_ids"])
    assert reads[-1] == proposal["evidence_ids"]


def test_insufficient_outcome_cannot_smuggle_uncited_substantive_claims(lab):
    lab[1].empty = True
    original = lab[2].provider.decide

    def smuggle(*args):
        response = original(*args)
        if response["name"] == "finish_tutor_turn":
            response["arguments"]["text"] = "Unknown, but the answer is 42."
        return response

    lab[2].provider.decide = smuggle
    result = run(lab)
    assert result["outcome"] == "failed" and result["answer"] is None
    assert result["error_code"] == "TUTOR_ABSTENTION_CONTRACT" and not result["citations"]


def test_socratic_prompt_followed_by_evaluation_of_learner_reply(lab):
    first = run(lab, socratic=True)
    assert first["outcome"] == "socratic_prompt" and "?" in first["answer"]
    second = run(lab, "reply", "Because BFS explores one level at a time", socratic=True)
    assert second["evaluation"] and "[e1]" in second["evaluation"]
    third = run(lab, "full", "Now explain it directly", socratic=False)
    assert third["outcome"] == "answered" and third["evaluation"]


def test_socratic_full_answer_is_protocol_failure(lab):
    original = lab[2].provider.decide

    def dump(*args):
        response = original(*args)
        if response["name"] == "finish_tutor_turn":
            response["arguments"]["outcome"] = "answered"
        return response

    lab[2].provider.decide = dump
    assert run(lab, socratic=True)["error_code"] == "TUTOR_SOCRATIC_CONTRACT"


def test_cancel_queued_and_late_model_result(lab):
    first = submit(lab)
    command(lab, "CANCEL", client_turn_id="turn-1")
    assert command(lab, "GET")["turns"][0]["status"] == "cancelled"
    assert not lab[0].candidates()
    original = lab[2].provider.decide

    def late(*args):
        response = original(*args)
        if response["name"] == "finish_tutor_turn":
            command(lab, "CANCEL", client_turn_id="late")
        return response

    lab[2].provider.decide = late
    result = run(lab, "late")
    assert result["status"] == "cancelled" and result["answer"] is None
    assert first["turns"][0]["client_turn_id"] == "turn-1"


def test_per_turn_and_persistent_session_budget(lab):
    lab[2].provider.decide = lambda *args: {"name": "search_tutor_evidence", "arguments": {"query": "BFS"}}
    result = run(lab)
    assert result["model_calls"] == 4 and result["error_code"] == "TUTOR_BUDGET_EXHAUSTED"
    with lab[0].connect() as conn:
        conn.execute("UPDATE tutor_session SET max_calls=4")
    with pytest.raises(StudyError, match="TUTOR_SESSION_BUDGET"):
        submit(lab, key="no-reset")
    lab[0].initialize()
    assert command(lab, "LIST")["sessions"][0]["model_calls"] == 4


def test_token_budget_and_deadline_are_persistent(lab):
    submit(lab)
    with lab[0].connect() as conn:
        conn.execute("UPDATE tutor_session SET max_tokens=1")
    lab[2].execute(lab[0].candidates()[0])
    assert command(lab, "GET")["turns"][0]["error_code"] == "TUTOR_BUDGET_EXHAUSTED"
    with lab[0].connect() as conn:
        conn.execute("UPDATE tutor_session SET max_tokens=640000")
    submit(lab, key="expired")
    with lab[0].connect() as conn:
        conn.execute(
            "UPDATE tutor_turn SET deadline=now()-interval '1 second' WHERE client_turn_id='expired'"
        )
    lab[2].execute(lab[0].candidates()[0])
    assert command(lab, "GET")["turns"][-1]["error_code"] == "TUTOR_DEADLINE"


def test_context_window_and_rolling_summary(lab):
    captures = []
    original = lab[2].provider.decide

    def capture(messages, *args):
        captures.append(json.loads(messages[-1]["content"]))
        return original(messages, *args)

    lab[2].provider.decide = capture
    for i in range(9):
        run(lab, str(i), "Explain BFS levels" if not i else "Why is that?")
    assert max(len(c["history"]) for c in captures) == 6
    assert captures[-1]["summary"] and "Explain BFS levels" in captures[-1]["summary"]
    assert len(captures[-1]["summary"]) <= 2000


def test_unknown_model_outcome_restart_never_resends(lab):
    def crash(*args):
        raise KeyboardInterrupt()

    lab[2].provider.decide = crash
    submit(lab)
    with pytest.raises(KeyboardInterrupt):
        lab[2].execute(lab[0].candidates()[0])
    restarted = TutorRuntime(lab[0], lab[1], MockTutor())
    restarted.execute(lab[0].candidates()[0])
    turn = command(lab, "GET")["turns"][0]
    assert turn["error_code"] == "TUTOR_UNKNOWN_MODEL_OUTCOME" and turn["model_calls"] == 1


def test_received_response_checkpoint_replays_without_second_model_call(lab, monkeypatch):
    original = lab[2].act
    submit(lab)
    monkeypatch.setattr(lab[2], "act", lambda *args: (_ for _ in ()).throw(KeyboardInterrupt()))
    with pytest.raises(KeyboardInterrupt):
        lab[2].execute(lab[0].candidates()[0])
    monkeypatch.setattr(lab[2], "act", original)
    lab[2].execute(lab[0].candidates()[0])
    result = command(lab, "GET")["turns"][0]
    assert result["status"] == "completed" and result["model_calls"] == 2
    assert len(lab[1].searches) == 1


def test_public_read_has_no_checkpoint_or_failed_answer(lab):
    result = submit(lab)
    assert "checkpoint" not in result["turns"][0] and result["turns"][0]["answer"] is None


def test_deleted_tombstone_purges_turns_and_blocks_inflight_result(lab):
    with lab[0].connect() as conn:
        conn.execute("CREATE TABLE evidence_index(owner_id bigint,course_id text,state text)")
    original = lab[2].provider.decide

    def deleted(*args):
        response = original(*args)
        if response["name"] == "finish_tutor_turn":
            with lab[0].connect() as conn:
                conn.execute(
                    "INSERT INTO evidence_index VALUES (%s,%s,'DELETED')",
                    (lab[3]["owner_id"], lab[3]["course_id"]),
                )
        return response

    lab[2].provider.decide = deleted
    submit(lab)
    lab[2].execute(lab[0].candidates()[0])
    with pytest.raises(StudyError, match="COURSE_UNAVAILABLE"):
        command(lab, "GET")
    lab[0].purge_deleted()
    with lab[0].connect() as conn:
        assert conn.execute("SELECT count(*) n FROM tutor_turn").fetchone()["n"] == 0
        assert conn.execute("SELECT count(*) n FROM tutor_session").fetchone()["n"] == 0


def test_http_signature_scope_and_redacted_errors(lab, monkeypatch):
    from fastapi.testclient import TestClient

    from lecturelens_agent.study.authority import signature
    from lecturelens_real_eval.tutor.app import PATH, create_app

    secret = "offline-only-tutor-test-secret-32-bytes"
    monkeypatch.setattr(lab[2], "start", lambda: None)
    app = create_app(tutor=lab[2], retriever=object(), secret=secret)
    body = json.dumps({**lab[3], "operation": "GET"}).encode()
    timestamp = str(int(time.time()))
    headers = {
        "X-LectureLens-Timestamp": timestamp,
        "X-LectureLens-Signature": signature(secret, timestamp, body, PATH),
    }
    with TestClient(app) as client:
        assert client.post(PATH, content=body, headers=headers).status_code == 200
        headers["X-LectureLens-Signature"] = signature(secret, timestamp, body, "/internal/v1/study/command")
        assert client.post(PATH, content=body, headers=headers).status_code == 401
        payload = b'{"text":"private"}'
        headers["X-LectureLens-Signature"] = signature(secret, timestamp, payload, PATH)
        response = client.post(PATH, content=payload, headers=headers)
        assert response.status_code == 422 and "private" not in response.text


def test_empty_evidence_explicit_abstention(lab):
    lab[1].empty = True
    result = run(lab)
    assert result["outcome"] == "insufficient_evidence" and result["answer"] == ABSTENTION
    assert result["citations"] == []


@pytest.mark.parametrize("mode", ["real", "invalid", ""])
def test_product_factory_rejects_non_mock_modes_without_reading_credentials(mode):
    from lecturelens_real_eval.tutor.app import require_mock

    with pytest.raises(RuntimeError, match="TUTOR_MOCK_ONLY"):
        require_mock(mode)


def test_product_factory_accepts_explicit_mock_mode():
    from lecturelens_real_eval.tutor.app import require_mock

    require_mock("mock")


def test_stale_session_fails_queued_turn_and_hides_summary_in_list(lab):
    submit(lab)
    lab[1].scope["revision"] = 2
    listed = command(lab, "LIST", revision=2)
    assert listed["sessions"][0]["status"] == "stale"
    assert "summary" not in listed["sessions"][0]
    with lab[0].connect() as conn:
        row = conn.execute("SELECT * FROM tutor_turn").fetchone()
        assert row["status"] == "failed" and row["error_code"] == "TUTOR_SESSION_STALE"


def install_eight_observations(lab, monkeypatch):
    """Expose eight authoritative observations; the provider cites all of them."""
    read = lab[1].read

    def many(scope, action="CHECK", **args):
        result = read(scope, action, **args)
        if result["evidence"]:
            rows = [{**result["evidence"][0], "evidence_id": f"e{i}"} for i in range(1, 9)]
            result["evidence"] = (
                [r for r in rows if r["evidence_id"] in args["evidence_ids"]] if action == "READ" else rows
            )
        return result

    monkeypatch.setattr(lab[1], "read", many)
    decide = lab[2].provider.decide

    def cite_all(messages, *args):
        response = decide(messages, *args)
        if response["name"] == "finish_tutor_turn":
            response["arguments"]["text"] = "Original " + " ".join(f"[e{i}]" for i in range(1, 9))
        return response

    lab[2].provider.decide = cite_all
    return cite_all


@pytest.mark.parametrize("fault", ["ids", "evaluation", "text"])
def test_finish_publishes_many_citations_and_fails_oversize_without_repair(lab, monkeypatch, fault):
    from lecturelens_real_eval.tutor.contracts import ANSWER_MAX_CHARS, EVALUATION_MAX_CHARS

    install_eight_observations(lab, monkeypatch)
    decide = MockTutor().decide
    ids = [f"e{i}" for i in range(1, 9)]

    def proposal(*args):
        response = decide(*args)
        if response["name"] == "finish_tutor_turn":
            args = response["arguments"]
            args["text"] = "Claim " + " ".join(f"[{eid}]" for eid in ids)
            if fault == "text":
                args["text"] += "T" * ANSWER_MAX_CHARS
            elif fault == "evaluation":
                args["evaluation"] = "E" * (EVALUATION_MAX_CHARS + 1)
        return response

    lab[2].provider.decide = proposal
    result = run(lab)
    assert result["model_calls"] == 2
    with lab[0].connect() as conn:
        row = conn.execute("SELECT checkpoint FROM tutor_turn").fetchone()
    assert not [o for o in row["checkpoint"]["observations"] if "error" in o]
    if fault == "ids":
        assert result["status"] == "completed"
        assert [c["evidence_id"] for c in result["citations"]] == ids
    else:
        assert result["error_code"] == "TUTOR_FINISH_FORMAT_INVALID"
        assert result["answer"] is None and not result["citations"]


def test_long_code_answer_publishes_unchanged(lab):
    decide = MockTutor().decide
    code = "for i in range(len(nums)):\n    total += nums[i]\n"
    text = "Explanation [e1]\n" + code * 80

    def proposal(*args):
        response = decide(*args)
        if response["name"] == "finish_tutor_turn":
            response["arguments"]["text"] = text
        return response

    lab[2].provider.decide = proposal
    result = run(lab)
    assert len(text) > 3000
    assert result["status"] == "completed" and result["answer"] == text
    assert [c["evidence_id"] for c in result["citations"]] == ["e1"]


@pytest.mark.parametrize("fault", ["unobserved", "authority_missing", "non_limit_schema"])
def test_finish_limit_does_not_hide_authority_or_other_schema_failure(lab, monkeypatch, fault):
    provider = install_eight_observations(lab, monkeypatch)

    def invalid(*args):
        response = provider(*args)
        if response["name"] == "finish_tutor_turn":
            if fault == "unobserved":
                response["arguments"]["text"] += " [e9]"
            elif fault == "authority_missing":
                lab[1].missing = True
            else:
                response["arguments"]["evaluation"] = 524
        return response

    lab[2].provider.decide = invalid
    result = run(lab)
    expected = "TUTOR_PROTOCOL_FAILURE" if fault == "non_limit_schema" else "TUTOR_CITATION_MISMATCH"
    assert result["error_code"] == expected and result["answer"] is None
    assert result["model_calls"] == 2 and result["tool_calls"] == 1


@pytest.mark.parametrize("declared", [["wrong"], ["e1", "e2", "e3", "e7", "e8"], None, 42])
def test_controller_publishes_extracted_order_dedupes_and_ignores_declarations(lab, monkeypatch, declared):
    install_eight_observations(lab, monkeypatch)
    decide = MockTutor().decide

    def proposal(*args):
        response = decide(*args)
        if response["name"] == "finish_tutor_turn":
            response["arguments"].update(text="[e8] [e2] [e8]", evaluation="[e7] [e2]", evidence_ids=declared)
        return response

    lab[2].provider.decide = proposal
    result = run(lab)
    assert result["status"] == "completed"
    assert [c["evidence_id"] for c in result["citations"]] == ["e8", "e2", "e7"]
    assert result["answer"] == "[e8] [e2] [e8]" and result["evaluation"] == "[e7] [e2]"
    assert result["model_calls"] == result["tool_calls"] == 2


@pytest.mark.parametrize(
    "legacy", ["TUTOR_FINISH_REPAIR_REQUIRED", "TUTOR_FINISH_LIMIT_EXCEEDED", "TUTOR_CITATION_MISMATCH"]
)
@pytest.mark.parametrize("oversized", [False, True])
def test_legacy_format_repair_journal_still_restricts_replay_to_finish(lab, monkeypatch, legacy, oversized):
    """Checkpoints committed by earlier builds keep their finish-only repair semantics."""
    from psycopg.types.json import Jsonb

    from lecturelens_real_eval.tutor.contracts import ANSWER_MAX_CHARS

    record = lab[2].record_observation

    def pause(turn_id, state):
        done = record(turn_id, state)
        if state["observations"][-1]["tool"] == "search_tutor_evidence":
            with lab[0].connect() as conn:
                checkpoint = conn.execute(
                    "SELECT checkpoint FROM tutor_turn WHERE turn_id=%s", (turn_id,)
                ).fetchone()["checkpoint"]
                checkpoint["observations"].append(
                    {"tool": "finish_tutor_turn", "error": legacy, "message": "legacy"}
                )
                conn.execute(
                    "UPDATE tutor_turn SET checkpoint=%s WHERE turn_id=%s", (Jsonb(checkpoint), turn_id)
                )
            raise KeyboardInterrupt()
        return done

    monkeypatch.setattr(lab[2], "record_observation", pause)
    submit(lab)
    with pytest.raises(KeyboardInterrupt):
        lab[2].execute(lab[0].candidates()[0])
    restored = TutorRuntime(TutorStore(lab[0].dsn), lab[1])
    decide = restored.provider.decide
    offered = []

    def proposal(messages, schemas, timeout):
        offered.append([s["function"]["name"] for s in schemas])
        response = decide(messages, schemas, timeout)
        if oversized:
            response["arguments"]["text"] = "[e1] " + "T" * ANSWER_MAX_CHARS
        return response

    restored.provider.decide = proposal
    restored.execute(lab[0].candidates()[0])
    result = command(lab, "GET")["turns"][-1]
    assert offered == [["finish_tutor_turn"]]
    if oversized:
        assert result["error_code"] == "TUTOR_FINISH_FORMAT_INVALID" and result["answer"] is None
    else:
        assert result["status"] == "completed" and result["citations"]


@pytest.mark.parametrize("socratic,fault", [(True, "outcome"), (True, "question"), (False, "outcome")])
@pytest.mark.parametrize("repeat", [False, True])
def test_socratic_one_shot_repair_and_restart(lab, monkeypatch, socratic, fault, repeat):
    decide = MockTutor().decide

    def proposal(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        response = decide(messages, schemas, timeout)
        if response["name"] == "finish_tutor_turn":
            if len(data["observations"]) == 1 or repeat:
                if fault == "question":
                    response["arguments"]["text"] = "A hint [e1]."
                else:
                    response["arguments"]["outcome"] = "answered" if socratic else "socratic_prompt"
            else:
                assert data["observations"][-1]["error"] == "TUTOR_SOCRATIC_REPAIR_REQUIRED"
                assert [s["function"]["name"] for s in schemas] == ["finish_tutor_turn"]
        return response

    lab[2].provider.decide = proposal
    record = lab[2].record_observation

    def pause(turn_id, state):
        done = record(turn_id, state)
        if state["observations"][-1].get("error") == "TUTOR_SOCRATIC_REPAIR_REQUIRED":
            raise KeyboardInterrupt()
        return done

    monkeypatch.setattr(lab[2], "record_observation", pause)
    submit(lab, socratic=socratic)
    with pytest.raises(KeyboardInterrupt):
        lab[2].execute(lab[0].candidates()[0])
    with lab[0].connect() as conn:
        row = conn.execute("SELECT * FROM tutor_turn").fetchone()
    assert row["model_calls"] == 3 and row["tool_calls"] == 2
    assert row["answer"] is None and row["checkpoint"]["repair_request"]
    restored = TutorRuntime(TutorStore(lab[0].dsn), lab[1])
    restored.provider.decide = proposal
    restored.execute(lab[0].candidates()[0])
    result = command(lab, "GET")["turns"][-1]
    if repeat:
        assert result["error_code"] == "TUTOR_SOCRATIC_CONTRACT" and result["answer"] is None
    else:
        assert result["status"] == "completed"
        assert result["outcome"] == ("socratic_prompt" if socratic else "answered")
        assert "?" in result["answer"] if socratic else result["answer"]
    assert result["model_calls"] == 3


def test_two_searches_then_socratic_repair_has_prepaid_finish_only_budget(lab):
    decide = MockTutor().decide
    calls = []

    def proposal(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        calls.append(data)
        if len(calls) <= 2:
            return {"name": "search_tutor_evidence", "arguments": {"query": "BFS"}}
        assert [s["function"]["name"] for s in schemas] == ["finish_tutor_turn"]
        if len(calls) > 3:
            with lab[0].connect() as conn:
                row = conn.execute("SELECT * FROM tutor_turn").fetchone()
            # Reservation committed with the repair, and is not charged twice on dispatch.
            assert row["model_calls"] == len(calls)
            assert row["tool_calls"] == len(calls) - 1
        response = decide(messages, schemas, timeout)
        if len(calls) == 3:
            response["arguments"]["outcome"] = "answered"
        return response

    lab[2].provider.decide = proposal
    result = run(lab, socratic=True)
    assert result["status"] == "completed" and result["error_code"] is None
    assert result["model_calls"] == result["tool_calls"] == 4
    assert len(lab[1].searches) == 2 and result["outcome"] == "socratic_prompt"
    with lab[0].connect() as conn:
        row = conn.execute("SELECT * FROM tutor_turn").fetchone()
        session = conn.execute("SELECT * FROM tutor_session").fetchone()
    assert row["model_calls"] <= 5 and row["reserved_tokens"] <= 64000
    assert session["model_calls"] == row["model_calls"]
    assert session["reserved_tokens"] == row["reserved_tokens"]
    assert len([o for o in row["checkpoint"]["observations"] if "error" in o]) == 1


def socratic_violation(decide):
    def proposal(*args):
        response = decide(*args)
        if response["name"] == "finish_tutor_turn":
            response["arguments"]["outcome"] = "answered"
        return response

    return proposal


def test_repair_call_rejects_search_without_authority_search(lab):
    decide = MockTutor().decide
    violate = socratic_violation(decide)

    def proposal(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        if len(data["observations"]) >= 2:
            assert [s["function"]["name"] for s in schemas] == ["finish_tutor_turn"]
            return {"name": "search_tutor_evidence", "arguments": {"query": "ignored"}}
        return violate(messages, schemas, timeout)

    lab[2].provider.decide = proposal
    result = run(lab, socratic=True)
    assert result["error_code"] == "TUTOR_PROTOCOL_FAILURE" and result["model_calls"] == 3
    assert len(lab[1].searches) == 1


@pytest.mark.parametrize("cap", ["session_calls", "session_tokens", "turn_tokens"])
def test_unavailable_repair_capacity_fails_before_issuing_observation(lab, cap):
    violate = socratic_violation(MockTutor().decide)

    def proposal(*args):
        response = violate(*args)
        if response["name"] == "finish_tutor_turn":
            with lab[0].connect() as conn:
                if cap == "session_calls":
                    conn.execute("UPDATE tutor_session SET max_calls=model_calls")
                elif cap == "session_tokens":
                    conn.execute("UPDATE tutor_session SET max_tokens=reserved_tokens")
                else:
                    conn.execute("UPDATE tutor_turn SET reserved_tokens=64000")
        return response

    lab[2].provider.decide = proposal
    result = run(lab, socratic=True)
    assert result["error_code"] == "TUTOR_REPAIR_BUDGET_UNAVAILABLE"
    with lab[0].connect() as conn:
        row = conn.execute("SELECT * FROM tutor_turn").fetchone()
    assert len(row["checkpoint"]["observations"]) == 1
    assert row["model_calls"] == 2 and row["answer"] is None


@pytest.mark.parametrize("stop", ["unknown", "cancel", "authority"])
def test_prepaid_repair_keeps_unknown_cancellation_and_authority_fences(lab, monkeypatch, stop):
    violate = socratic_violation(MockTutor().decide)
    calls = []

    def proposal(messages, schemas, timeout):
        calls.append(json.loads(messages[-1]["content"]))
        if len(calls) == 3:
            raise KeyboardInterrupt()
        return violate(messages, schemas, timeout)

    lab[2].provider.decide = proposal
    record = lab[2].record_observation

    def pause(turn_id, state):
        result = record(turn_id, state)
        if state["observations"][-1].get("error") == "TUTOR_SOCRATIC_REPAIR_REQUIRED":
            raise KeyboardInterrupt()
        return result

    if stop != "unknown":
        monkeypatch.setattr(lab[2], "record_observation", pause)
    submit(lab, socratic=True)
    with pytest.raises(KeyboardInterrupt):
        lab[2].execute(lab[0].candidates()[0])
    if stop == "cancel":
        command(lab, "CANCEL", client_turn_id="turn-1")
    elif stop == "authority":
        lab[1].missing = True
    restored = TutorRuntime(TutorStore(lab[0].dsn), lab[1])
    restored.provider.decide = lambda *args: pytest.fail("Stopped repair must not dispatch or replay")
    with lab[0].connect() as conn:
        candidate = conn.execute("SELECT turn_id,session_id FROM tutor_turn").fetchone()
    restored.execute(candidate)
    result = command(lab, "GET")["turns"][-1]
    assert result["answer"] is None and not result["citations"]
    assert result["model_calls"] == 3 and result["tool_calls"] == 2
    if stop == "cancel":
        assert result["status"] == "cancelled" and len(calls) == 2
    else:
        assert result["error_code"] == (
            "TUTOR_UNKNOWN_MODEL_OUTCOME" if stop == "unknown" else "TUTOR_CITATION_MISMATCH"
        )
        assert len(calls) == (3 if stop == "unknown" else 2)


@pytest.mark.parametrize("foreign", [None, "e999", "v2-algorithms-l2-p01-e00", "a" * 64])
def test_math_brackets_publish_unchanged_but_strict_foreign_id_fails(lab, foreign):
    decide = MockTutor().decide
    text = "Math [u] [v] [A] [x_1], course claim [e1]."
    evaluation = "Check [A] [x_1] [e1]." + (f" [{foreign}]" if foreign else "")

    def proposal(*args):
        response = decide(*args)
        if response["name"] == "finish_tutor_turn":
            response["arguments"].update(text=text, evaluation=evaluation)
        return response

    lab[2].provider.decide = proposal
    result = run(lab)
    assert result["model_calls"] == 2
    if foreign:
        assert result["error_code"] == "TUTOR_CITATION_MISMATCH"
        assert result["answer"] is None and not result["citations"]
    else:
        assert result["status"] == "completed"
        assert result["answer"] == text and result["evaluation"] == evaluation
        assert [c["evidence_id"] for c in result["citations"]] == ["e1"]


FINISH_V8_CASES = json.loads((Path(__file__).parent / "fixtures/p8_finish_v8.json").read_text())["cases"]


@pytest.mark.parametrize("case", FINISH_V8_CASES, ids=lambda c: c["case"])
def test_v8_failed_first_finish_now_publishes_on_first_proposal(lab, monkeypatch, case):
    """Historical v8 first proposals failed only the old 1600/4 caps; replay mechanics, not quality."""
    from lecturelens_real_eval.tutor.citations import assembled_citation_ids
    from lecturelens_real_eval.tutor.runtime import FINISH_LIMITS

    ids = list(dict.fromkeys(case["text_ids"] + case["evaluation_ids"]))
    read = lab[1].read

    def evidence(scope, action="CHECK", **args):
        result = read(scope, action, **args)
        if result["evidence"]:
            rows = [{**result["evidence"][0], "evidence_id": eid} for eid in ids]
            result["evidence"] = (
                [r for r in rows if r["evidence_id"] in args["evidence_ids"]] if action == "READ" else rows
            )
        return result

    monkeypatch.setattr(lab[1], "read", evidence)
    first = {"outcome": case["outcome"]}
    for key in ("text", "evaluation"):
        content = " ".join(f"[{eid}]" for eid in case[key + "_ids"])
        if key == "text":
            content += " " + " ".join(case["math_tokens"])
        assert len(content) <= case[key + "_chars"]
        first[key] = content + "T" * (case[key + "_chars"] - len(content))
    assert assembled_citation_ids(first["text"], first["evaluation"]) == ids
    decide = MockTutor().decide

    def proposal(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        for schema in schemas:
            if schema["function"]["name"] == "finish_tutor_turn":
                assert schema["function"]["description"] == FINISH_LIMITS
        if not data["observations"]:
            return decide(messages, schemas, timeout)
        return {"name": "finish_tutor_turn", "arguments": first.copy()}

    lab[2].provider.decide = proposal
    result = run(lab, socratic=case["socratic"])
    assert result["status"] == "completed" and result["model_calls"] == 2
    assert result["answer"] == first["text"]
    assert [c["evidence_id"] for c in result["citations"]] == ids


def install_search_batches(lab, monkeypatch, batches, *, text_size=50):
    """Authority READ deliberately returns reverse order, independent of search ranking."""
    read = lab[1].read
    reads = []
    rows = {
        eid: {**read(lab[3], "READ")["evidence"][0], "evidence_id": eid, "text": "X" * text_size}
        for batch in batches
        for eid in batch
    }

    def authority(scope, action="CHECK", **args):
        result = read(scope, action, **args)
        if action == "SEARCH":
            result["evidence"] = [rows[eid] for eid in batches[len(lab[1].searches) - 1]]
        elif action == "READ":
            assert len(args["evidence_ids"]) <= 8  # Preserve Java's authority request cap.
            reads.append(list(args["evidence_ids"]))
            result["evidence"] = [rows[eid] for eid in reversed(args["evidence_ids"])]
        return result

    monkeypatch.setattr(lab[1], "read", authority)
    return reads


@pytest.mark.parametrize("restart_after", [None, 1, 2])
def test_citable_union_publishes_first_search_id_after_second_and_restart(lab, monkeypatch, restart_after):
    first = "v2-quantum-l2-p05-e00"
    batches = [[first, "e2", first], ["e3", "e2", "e4"]]
    expected = [first, "e2", "e3", "e4"]
    reads = install_search_batches(lab, monkeypatch, batches)
    prompts = []

    def proposal(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        prompts.append(data)
        count = len(data["observations"])
        visible = list(dict.fromkeys(eid for o in data["observations"] for eid in o["evidence_ids"]))
        assert [e["evidence_id"] for e in data["evidence"]] == visible
        if count < 2:
            return {"name": "search_tutor_evidence", "arguments": {"query": "quantum"}}
        assert visible == expected
        assert [s["function"]["name"] for s in schemas] == ["finish_tutor_turn"]
        return {"name": "finish_tutor_turn", "arguments": {"outcome": "answered", "text": f"Claim [{first}]"}}

    lab[2].provider.decide = proposal
    record = lab[2].record_observation

    def pause(turn_id, state):
        done = record(turn_id, state)
        if len(state["observations"]) == restart_after:
            raise KeyboardInterrupt()
        return done

    monkeypatch.setattr(lab[2], "record_observation", pause)
    submit(lab)
    if restart_after is not None:
        with pytest.raises(KeyboardInterrupt):
            lab[2].execute(lab[0].candidates()[0])
        with lab[0].connect() as conn:
            checkpoint = conn.execute("SELECT checkpoint FROM tutor_turn").fetchone()["checkpoint"]
        assert checkpoint["selected"] == (expected[:2] if restart_after == 1 else expected)
        restored = TutorRuntime(TutorStore(lab[0].dsn), lab[1])
        restored.provider.decide = proposal
        restored.execute(lab[0].candidates()[0])
    else:
        lab[2].execute(lab[0].candidates()[0])
    result = command(lab, "GET")["turns"][-1]
    assert result["status"] == "completed" and result["answer"] == f"Claim [{first}]"
    assert [c["evidence_id"] for c in result["citations"]] == [first]
    assert len(prompts) == result["model_calls"] == result["tool_calls"] == 3
    assert len(lab[1].searches) == 2 and expected in reads and reads[-1] == [first]
    with lab[0].connect() as conn:
        row = conn.execute("SELECT * FROM tutor_turn").fetchone()
    assert row["checkpoint"]["selected"] == expected
    replay = submit(lab)
    assert replay["replayed"] and replay["turns"][-1] == result
    assert len(prompts) == 3


@pytest.mark.parametrize("foreign", ["v2-quantum-l2-p04-e00", "e999"])
def test_citable_union_excludes_prior_turn_citations_and_fabricated_ids(lab, monkeypatch, foreign):
    install_search_batches(lab, monkeypatch, [["v2-quantum-l2-p04-e00"], ["e2"], ["e3"]])
    assert run(lab)["status"] == "completed"
    prompts = []

    def proposal(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        prompts.append(data)
        assert foreign not in [e["evidence_id"] for e in data["evidence"]]
        assert "v2-quantum-l2-p04-e00" in data["history"][0]["answer"]
        if len(data["observations"]) < 2:
            return {"name": "search_tutor_evidence", "arguments": {"query": "new topic"}}
        return {
            "name": "finish_tutor_turn",
            "arguments": {"outcome": "answered", "text": f"Claim [{foreign}]"},
        }

    lab[2].provider.decide = proposal
    result = run(lab, key="turn-2")
    assert result["error_code"] == "TUTOR_CITATION_MISMATCH"
    assert result["answer"] is None and result["citations"] == []
    with lab[0].connect() as conn:
        row = conn.execute("SELECT checkpoint FROM tutor_turn WHERE ordinal=2").fetchone()
    assert row["checkpoint"]["selected"] == ["e2", "e3"]
    assert len(prompts) == 3


@pytest.mark.parametrize("text_size,completed", [(50, True), (3000, False)])
def test_citable_union_natural_bound_and_unchanged_reservation_cap(lab, monkeypatch, text_size, completed):
    batches = [[f"e{i}" for i in range(1, 9)], [f"e{i}" for i in range(9, 17)]]
    reads = install_search_batches(lab, monkeypatch, batches, text_size=text_size)
    visible_sizes = []

    def proposal(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        visible_sizes.append(len(data["evidence"]))
        if len(data["observations"]) < 2:
            return {"name": "search_tutor_evidence", "arguments": {"query": "bounded"}}
        assert [e["evidence_id"] for e in data["evidence"]] == [f"e{i}" for i in range(1, 17)]
        return {"name": "finish_tutor_turn", "arguments": {"outcome": "answered", "text": "Claim [e16]"}}

    lab[2].provider.decide = proposal
    result = run(lab)
    with lab[0].connect() as conn:
        row = conn.execute("SELECT * FROM tutor_turn").fetchone()
        session = conn.execute("SELECT * FROM tutor_session").fetchone()
    assert row["checkpoint"]["selected"] == [f"e{i}" for i in range(1, MAX_SEARCH_CALLS * 8 + 1)]
    assert row["reserved_tokens"] <= 64000
    assert session["reserved_tokens"] == row["reserved_tokens"]
    if completed:
        assert result["status"] == "completed" and visible_sizes == [0, 8, 16]
        assert reads[-3:-1] == batches and reads[-1] == ["e16"]
    else:
        assert result["error_code"] == "TUTOR_BUDGET_EXHAUSTED" and visible_sizes == [0, 8]
        assert result["answer"] is None and result["citations"] == []
        assert reads[-2:] == batches


def test_citable_union_publishes_six_ids_across_both_searches(lab, monkeypatch):
    batches = [["e5", "e1", "e2"], ["e3", "e4", "e6"]]
    install_search_batches(lab, monkeypatch, batches)
    union = ["e5", "e1", "e2", "e3", "e4", "e6"]
    proposed = ["e5", "e2", "e3", "e1", "e6", "e4"]

    def proposal(messages, schemas, timeout):
        data = json.loads(messages[-1]["content"])
        if len(data["observations"]) < 2:
            return {"name": "search_tutor_evidence", "arguments": {"query": "union"}}
        assert [e["evidence_id"] for e in data["evidence"]] == union
        text = "Claim " + " ".join(f"[{eid}]" for eid in proposed)
        return {"name": "finish_tutor_turn", "arguments": {"outcome": "answered", "text": text}}

    lab[2].provider.decide = proposal
    result = run(lab)
    assert result["status"] == "completed" and result["model_calls"] == result["tool_calls"] == 3
    assert [c["evidence_id"] for c in result["citations"]] == proposed
