import os
import socket
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pytest
from langgraph.checkpoint.postgres import PostgresSaver
from pydantic import ValidationError

from lecturelens_agent.store import VectorStore
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import RunStopped, StudyError, StudyStore


class Authority:
    def __init__(self, scope):
        self.scope = scope
        self.valid = True
        self.empty = False
        self.missing = False

    def read(self, scope, action="CHECK", **arguments):
        if not self.valid or any(scope[k] != self.scope[k] for k in ("owner_id", "course_id", "revision")):
            raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED", 404)
        keys = arguments.get("evidence_ids", ["e1", "e2", "e3"])
        if self.empty or action == "CHECK":
            keys = []
        if self.missing and action == "READ":
            keys = keys[:-1]
        return {
            **self.scope,
            "evidence": [
                {
                    "evidence_id": key,
                    "text": "Binary search halves the remaining interval.",
                    "start_ms": 1000 * (int(key[1:]) - 1),
                    "end_ms": 1000 * int(key[1:]),
                    "source_type": "SUBTITLE",
                }
                for key in keys
            ],
        }


@pytest.fixture
def lab(monkeypatch):
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    from psycopg.conninfo import conninfo_to_dict

    info = conninfo_to_dict(dsn)
    assert info["host"] in {"127.0.0.1", "localhost"} and info["dbname"].endswith("_test")
    scope = dict(owner_id=427, course_id="p7-" + uuid.uuid4().hex, revision=1)
    store = StudyStore(dsn)
    authority = Authority(scope.copy())
    runtime = StudyRuntime(store, authority, MockProvider())
    runtime.initialize()
    session = store.command(StudyCommand(**scope, operation="CREATE_SESSION", request_key="s"), "mock")
    scope["session_id"] = session["session_id"]
    # The Mock path may reach local PostgreSQL but can never open an external Python socket.
    original = socket.socket.connect

    def local_only(sock, address):
        if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1", "localhost"}:
            raise AssertionError("External network forbidden in Mock tests")
        return original(sock, address)

    monkeypatch.setattr(socket.socket, "connect", local_only)
    yield store, authority, runtime, scope
    runtime.close()
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.delete_thread(scope["session_id"])
    with store.connect() as conn:
        conn.execute("DELETE FROM study_run WHERE session_id=%s", (scope["session_id"],))
        conn.execute("DELETE FROM study_session WHERE session_id=%s", (scope["session_id"],))
        conn.execute(
            "DELETE FROM evidence_index WHERE owner_id=%s AND course_id=%s",
            (scope["owner_id"], scope["course_id"]),
        ) if conn.execute("SELECT to_regclass('evidence_index') AS t").fetchone()["t"] else None


def command(lab, operation, **kw):
    store, _, _, scope = lab
    return store.command(StudyCommand(**{**scope, **kw, "operation": operation}), "mock")


def start(lab, **kw):
    response = command(lab, "GENERATE_CARDS", request_key="generate", **kw)
    return next(r for r in lab[0].candidates() if r["run_id"] == response["run"]["run_id"])


def generated(lab):
    run = start(lab)
    lab[2].execute(run)
    result = command(lab, "DUE_CARDS")
    assert result["generation"]["status"] == "succeeded", result
    return result


def review(lab, card, key="review", rating="Good", **kw):
    return command(
        lab,
        "REVIEW_CARD",
        card_id=card["card_id"],
        request_key=key,
        expected_version=card["version"],
        rating=rating,
        **kw,
    )


def test_generation_citations_all_resolve_current_snapshot_and_reads_are_side_effect_free(lab):
    result = generated(lab)
    assert result["due_count"] == 3
    before = result["generation"]
    for card in result["cards"]:
        canonical = lab[1].read(lab[3], "READ", evidence_ids=[c["evidence_id"] for c in card["citations"]])
        assert card["citations"] == canonical["evidence"] and card["revision"] == 1
        assert command(lab, "READ_CARD", card_id=card["card_id"])["card"]["version"] == 0
    for _ in range(3):
        after = command(lab, "DUE_CARDS")
        assert after["generation"] == before
    with lab[0].connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) n FROM study_run WHERE session_id=%s", (lab[3]["session_id"],)
            ).fetchone()["n"]
            == 1
        )
    assert before["model_calls"] == 2 and before["tool_calls"] == 2


def test_review_replay_conflict_refresh_and_not_due(lab):
    card = generated(lab)["cards"][0]
    first = review(lab, card)
    assert not first["replayed"]
    replay = review(lab, card)
    assert replay["replayed"] and replay["review"] == first["review"]
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        review(lab, card, rating="Easy")
    with pytest.raises(StudyError, match="CARD_VERSION_CONFLICT"):
        review(lab, card, key="other")
    with pytest.raises(StudyError, match="CARD_NOT_DUE"):
        review(lab, {**card, "version": 1}, key="early")
    restored = command(lab, "DUE_CARDS")
    assert restored["due_count"] == 2 and restored["reviewed_today"] == 1
    assert card["card_id"] not in [c["card_id"] for c in restored["cards"]]
    assert restored["generation"]["model_calls"] == 2


@pytest.mark.parametrize("same_key", [False, True])
def test_concurrent_review_is_one_effect_or_version_conflict(lab, same_key):
    card = generated(lab)["cards"][0]
    barrier = threading.Barrier(2)

    def submit(key):
        barrier.wait()
        try:
            return review(lab, card, key=key)
        except StudyError as error:
            return error.code

    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(submit, ["same", "same" if same_key else "other"]))
    if same_key:
        assert sorted(r["replayed"] for r in results) == [False, True]
    else:
        assert results.count("CARD_VERSION_CONFLICT") == 1
    with lab[0].connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) n FROM study_review_log WHERE card_id=%s", (card["card_id"],)
            ).fetchone()["n"]
            == 1
        )


@pytest.mark.parametrize("change", [{"owner_id": 999}, {"course_id": "another-course"}, {"revision": 2}])
def test_scope_fence_for_reads_reviews_and_generation(lab, change):
    card = generated(lab)["cards"][0]
    assert command(lab, "DUE_CARDS", **change)["cards"] == []
    for operation in ["READ_CARD", "REVIEW_CARD"]:
        with pytest.raises(StudyError, match="CARD_NOT_FOUND_OR_STALE"):
            command(
                lab,
                operation,
                card_id=card["card_id"],
                rating="Good",
                request_key="attack",
                expected_version=0,
                **change,
            )
    with pytest.raises(StudyError, match="SESSION_NOT_FOUND_OR_STALE"):
        command(lab, "GENERATE_CARDS", request_key="attack", **change)


def test_revision_changes_during_generation_never_publish(lab):
    original = lab[2].provider.flashcards

    def changed(messages, schemas, timeout):
        response = original(messages, schemas, timeout)
        if response["name"] == "create_evidence_cards":
            lab[1].valid = False
        return response

    lab[2].provider.flashcards = changed
    lab[2].execute(start(lab))
    assert command(lab, "DUE_CARDS")["total_count"] == 0
    assert command(lab, "DUE_CARDS")["generation"]["status"] == "failed"


def test_cancel_late_model_result_cannot_publish(lab):
    original = lab[2].provider.flashcards

    def cancel(messages, schemas, timeout):
        response = original(messages, schemas, timeout)
        if response["name"] == "create_evidence_cards":
            run = command(lab, "DUE_CARDS")["generation"]
            command(lab, "CANCEL", run_id=run["run_id"])
        return response

    lab[2].provider.flashcards = cancel
    lab[2].execute(start(lab))
    assert command(lab, "DUE_CARDS")["generation"]["status"] == "cancelled"
    assert command(lab, "DUE_CARDS")["total_count"] == 0


def test_checkpoint_after_publication_replays_without_duplicate_deck_or_model(lab):
    original = lab[0].save_tool
    interrupted = False

    def crash(*args, **kw):
        nonlocal interrupted
        response = original(*args, **kw)
        if kw.get("cards") and not interrupted:
            interrupted = True
            raise RunStopped()
        return response

    lab[0].save_tool = crash
    run = start(lab)
    lab[2].execute(run)
    assert command(lab, "DUE_CARDS")["total_count"] == 0  # Unfinished Run is private.
    lab[2].execute(next(r for r in lab[0].candidates() if r["run_id"] == run["run_id"]))
    result = command(lab, "DUE_CARDS")
    assert result["total_count"] == 3 and result["generation"]["model_calls"] == 2


def test_empty_evidence_stops_without_cards(lab):
    lab[1].empty = True
    lab[2].execute(start(lab))
    result = command(lab, "DUE_CARDS")
    assert result["total_count"] == 0 and result["generation"]["status"] == "succeeded"


def test_missing_citation_fails_closed(lab):
    lab[1].missing = True
    lab[2].execute(start(lab))
    assert command(lab, "DUE_CARDS")["total_count"] == 0
    assert command(lab, "DUE_CARDS")["generation"]["error_code"] == "CARD_CITATION_MISMATCH"


def test_model_loop_budget_and_legacy_worker_isolation(lab):
    run = start(lab)
    with lab[0].connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM study_run WHERE run_id=%s AND status IN ('queued','running')", (run["run_id"],)
        ).fetchone()
    lab[2].provider.flashcards = lambda *a: {"name": "search_card_evidence", "arguments": {"query": "again"}}
    lab[2].execute(run)
    result = command(lab, "DUE_CARDS")
    assert result["generation"]["status"] == "budget_exceeded"
    assert result["generation"]["model_calls"] == 6 and result["total_count"] == 0


def test_real_mode_rejected_before_resolving_model_credentials(lab):
    lab[0].model_resolver = lambda _: pytest.fail("must not read provider credentials")
    with pytest.raises(StudyError, match="FLASHCARDS_MOCK_ONLY"):
        lab[0].command(StudyCommand(**lab[3], operation="GENERATE_CARDS", request_key="x"), "real")


def test_delete_propagation_cascades_decks_reviews_and_checkpoints(lab):
    cards = generated(lab)["cards"]
    review(lab, cards[0])
    VectorStore(lab[0].dsn).initialize()
    with lab[0].connect() as conn:
        conn.execute(
            "INSERT INTO evidence_index VALUES (%s,%s,1,1,'test','DELETED','',now())",
            (lab[3]["owner_id"], lab[3]["course_id"]),
        )
    lab[2].purge_deleted()
    with lab[0].connect() as conn:
        assert not conn.execute(
            "SELECT 1 FROM study_card WHERE card_id=ANY(%s)", ([c["card_id"] for c in cards],)
        ).fetchone()
        assert not conn.execute(
            "SELECT 1 FROM study_review_log WHERE card_id=%s", (cards[0]["card_id"],)
        ).fetchone()
    with PostgresSaver.from_conn_string(lab[0].dsn) as saver:
        assert saver.get_tuple({"configurable": {"thread_id": lab[3]["session_id"]}}) is None


@pytest.mark.parametrize(
    "operation,kwargs",
    [
        ("GENERATE_CARDS", {}),
        ("READ_CARD", {}),
        ("REVIEW_CARD", {"card_id": "c", "rating": "Good"}),
        ("REVIEW_CARD", {"card_id": "c", "rating": "Unknown", "expected_version": 0, "request_key": "k"}),
    ],
)
def test_card_contracts_reject_incomplete_commands(operation, kwargs):
    with pytest.raises(ValidationError):
        StudyCommand(owner_id=1, course_id="c", revision=1, operation=operation, **kwargs)


def test_mock_socket_guard_is_live(lab):
    with socket.socket() as sock, pytest.raises(AssertionError, match="External network"):
        sock.connect(("203.0.113.1", 443))


def test_due_clock_boundary_and_server_owned_review_time(lab, monkeypatch):
    cards = generated(lab)["cards"]
    now = datetime.now(timezone.utc)
    with lab[0].connect() as conn:
        conn.execute(
            "UPDATE study_card SET due_at=%s WHERE card_id=%s",
            (now + timedelta(seconds=1), cards[0]["card_id"]),
        )
    monkeypatch.setattr("lecturelens_agent.study.flashcards.utc_now", lambda: now)
    assert command(lab, "DUE_CARDS")["due_count"] == 2
    monkeypatch.setattr("lecturelens_agent.study.flashcards.utc_now", lambda: now + timedelta(seconds=1))
    assert command(lab, "DUE_CARDS")["due_count"] == 3
    assert review(lab, cards[0])["review"]["reviewed_at"] == now + timedelta(seconds=1)


def test_generation_idempotency_does_not_create_second_run(lab):
    run = start(lab)
    assert start(lab)["run_id"] == run["run_id"]
    with pytest.raises(StudyError, match="SESSION_BUSY"):
        command(lab, "GENERATE_CARDS", request_key="different")
    with pytest.raises(StudyError, match="REQUEST_KEY_CONFLICT"):
        command(lab, "GENERATE_CARDS", request_key="generate", goal="changed goal")
    lab[2].execute(run)
    assert command(lab, "GENERATE_CARDS", request_key="generate")["run"]["run_id"] == run["run_id"]
