"""Step 6: bounded parallel lanes for retrieval, indexing, Study Runs and the event stream.

Concurrency is proven with events and barriers that would deadlock (and then time out)
if the paths were still serialized; no assertion depends on a sleep.
"""

import json
import threading
import time
import uuid

import httpx
import pytest
import test_retrieval
import test_study
from fastapi.testclient import TestClient
from langgraph.checkpoint.postgres import PostgresSaver

from lecturelens_agent.app import EVENT_STREAM_PATH, PATH, bounded_setting, create_app, flag
from lecturelens_agent.contracts import RetrieveRequest
from lecturelens_agent.retrieval import BusyError, Retriever
from lecturelens_agent.store import StaleSync
from lecturelens_agent.study.authority import signature as study_signature
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import DEFAULT_RUN_CONCURRENCY, StudyRuntime
from lecturelens_agent.study.store import StudyStore
from lecturelens_agent.study.telemetry import _span

store = test_retrieval.store
setup = test_study.setup
WAIT = 10
SECRET = "test-study-context-only-32-byte-secret"


# --- Retrieval: queries and index builds are admitted separately -------------------------


class GatedEmbedding(test_retrieval.FakeEmbedding):
    """Blocks document embeddings (never the query text) until released."""

    def __init__(self, query="bread"):
        super().__init__()
        self.query, self.entered, self.release = query, threading.Event(), threading.Event()

    def embed(self, texts):
        if texts != [self.query]:
            self.entered.set()
            assert self.release.wait(WAIT)
        return super().embed(texts)


def query_for(course=None):
    data = test_retrieval.payload()
    if course:
        data["course_id"] = course
    return RetrieveRequest.model_validate(data)


def test_query_is_served_while_another_course_index_build_embeds(store):
    embedder = GatedEmbedding()
    retriever = Retriever(store, embedder)
    ready = query_for()
    embedder.release.set()
    retriever.sync(test_retrieval.sync_request(ready))
    embedder.release.clear()
    building = query_for()
    errors, done = [], threading.Event()

    def index():
        try:
            assert retriever.sync(test_retrieval.sync_request(building))["state"] == "READY"
        except BaseException as error:  # noqa: BLE001 -- surfaced in the parent test
            errors.append(error)
        finally:
            done.set()

    worker = threading.Thread(target=index)
    worker.start()
    try:
        assert embedder.entered.wait(WAIT)
        # Previously the shared lock made this BusyError (HTTP 503) for the whole build.
        assert [hit.evidence_id for hit in retriever.search(ready).hits] == ["e1", "e2"]
        assert not done.is_set()
    finally:
        embedder.release.set()
        worker.join(WAIT)
    assert not errors and not worker.is_alive()
    assert [hit.evidence_id for hit in retriever.search(building).hits][0] == "e1"


def test_index_build_is_not_blocked_by_queries_and_stays_single_lane(store):
    retriever = Retriever(store, test_retrieval.FakeEmbedding(), query_concurrency=2)
    query = query_for()
    for _ in range(2):
        assert retriever.query_slots.acquire(blocking=False)
    try:
        with pytest.raises(BusyError):
            retriever.search(query)
        assert retriever.sync(test_retrieval.sync_request(query))["state"] == "READY"
    finally:
        retriever.query_slots.release()
        retriever.query_slots.release()
    with retriever.index_lock:
        with pytest.raises(BusyError):
            retriever.sync(test_retrieval.sync_request(query, 2))
        assert retriever.search(query).hits
        # Planning and deletion never need the index admission lock.
        assert retriever.sync(test_retrieval.sync_request(query, 2, operation="PLAN"))["state"] == "PENDING"
        assert retriever.sync(test_retrieval.sync_request(query, 3, [], "DELETE"))["state"] == "DELETED"


class ReadyStore:
    def ready_snapshot(self, *args):
        return "snapshot"

    def search(self, *args):
        return [{"evidence_id": "e1", "score": 1.0}]


def test_queries_overlap_up_to_the_bound_then_reject_without_queueing():
    lanes = 3
    entered, release = threading.Barrier(lanes + 1, timeout=WAIT), threading.Event()

    class Embedding(test_retrieval.FakeEmbedding):
        def embed(self, texts):
            if not release.is_set():
                entered.wait()  # all `lanes` queries are inside embedding at the same time
                assert release.wait(WAIT)
            return super().embed(texts)

    retriever = Retriever(ReadyStore(), Embedding(), query_concurrency=lanes)
    results, errors = [], []

    def query():
        try:
            results.append(retriever.search(query_for()))
        except BaseException as error:  # noqa: BLE001 -- surfaced in the parent test
            errors.append(error)

    workers = [threading.Thread(target=query) for _ in range(lanes)]
    for worker in workers:
        worker.start()
    try:
        entered.wait()
        with pytest.raises(BusyError):
            retriever.search(query_for())
    finally:
        release.set()
        for worker in workers:
            worker.join(WAIT)
    assert not errors and len(results) == lanes
    assert retriever.search(query_for()).hits[0].evidence_id == "e1"


def test_query_concurrency_is_bounded_and_validated(monkeypatch):
    for invalid in (0, 17):
        with pytest.raises(ValueError):
            Retriever(ReadyStore(), test_retrieval.FakeEmbedding(), query_concurrency=invalid)
    monkeypatch.delenv("AGENT_RUN_CONCURRENCY", raising=False)
    assert bounded_setting("AGENT_RUN_CONCURRENCY", DEFAULT_RUN_CONCURRENCY, 1, 8) == 2
    for raw in ("0", "9", "two", "1.5"):
        monkeypatch.setenv("AGENT_RUN_CONCURRENCY", raw)
        with pytest.raises(RuntimeError, match="between 1 and 8"):
            bounded_setting("AGENT_RUN_CONCURRENCY", DEFAULT_RUN_CONCURRENCY, 1, 8)
    monkeypatch.setenv("AGENT_RUN_CONCURRENCY", "8")
    assert bounded_setting("AGENT_RUN_CONCURRENCY", DEFAULT_RUN_CONCURRENCY, 1, 8) == 8
    monkeypatch.delenv("AGENT_EVENT_STREAM_ENABLED", raising=False)
    assert flag("AGENT_EVENT_STREAM_ENABLED") is False
    monkeypatch.setenv("AGENT_EVENT_STREAM_ENABLED", "yes")
    with pytest.raises(RuntimeError):
        flag("AGENT_EVENT_STREAM_ENABLED")


def test_same_course_republish_during_query_is_a_retryable_conflict():
    class Republished(ReadyStore):
        def search(self, *args):
            raise StaleSync("Index changed during retrieval")

    body = json.dumps(test_retrieval.payload()).encode()
    retriever = Retriever(Republished(), test_retrieval.FakeEmbedding())
    with TestClient(create_app(retriever, test_retrieval.SECRET)) as client:
        response = client.post(PATH, content=body, headers=test_retrieval.signed(body))
    assert response.status_code == 409 and response.headers["Retry-After"] == "1"
    assert response.json() == {"detail": "Evidence index changed"}


# --- Study Runs: different Sessions in parallel, one Session serialized ------------------


class FakeStudyStore:
    """Candidate rows only; the dispatcher never needs SQL for these unit tests."""

    def __init__(self, rows):
        self.rows, self.done = rows, set()
        self.lock = threading.Lock()

    def candidates(self):
        with self.lock:
            return [row for row in self.rows if row["run_id"] not in self.done]


def lanes_runtime(rows, concurrency):
    runtime = StudyRuntime(
        FakeStudyStore(rows), test_study.Authority(), MockProvider(), concurrency=concurrency
    )
    runtime.purge_deleted = lambda: None
    log, gates, lock = [], {row["run_id"]: threading.Event() for row in rows}, threading.Lock()
    started = {row["run_id"]: threading.Event() for row in rows}
    state = {"active": 0, "peak": 0}

    def execute(run):
        with lock:
            state["active"] += 1
            state["peak"] = max(state["peak"], state["active"])
            log.append(("start", run["run_id"]))
        started[run["run_id"]].set()
        try:
            assert gates[run["run_id"]].wait(WAIT)
        finally:
            with lock:
                state["active"] -= 1
                log.append(("end", run["run_id"]))
            with runtime.store.lock:
                runtime.store.done.add(run["run_id"])

    runtime.execute = execute
    return runtime, log, gates, started, state


def test_dispatcher_overlaps_sessions_and_serializes_one_session_in_order():
    rows = [
        {"run_id": "a1", "session_id": "s-a"},
        {"run_id": "a2", "session_id": "s-a"},
        {"run_id": "b1", "session_id": "s-b"},
    ]
    runtime, log, gates, started, state = lanes_runtime(rows, concurrency=3)
    runtime.start()
    try:
        # a1 and b1 are in flight together: different Sessions overlap.
        assert started["a1"].wait(WAIT) and started["b1"].wait(WAIT)
        assert not started["a2"].is_set()
        gates["b1"].set()
        # b1's completion wakes the dispatcher, but a2 still waits for its own Session.
        assert not started["a2"].wait(0.3)
        gates["a1"].set()
        assert started["a2"].wait(WAIT)
        gates["a2"].set()
    finally:
        for gate in gates.values():
            gate.set()
        runtime.close()
    assert log.index(("end", "a1")) < log.index(("start", "a2"))
    assert state["peak"] == 2
    assert [thread.is_alive() for thread in [runtime.thread, *runtime.workers]] == [False] * 4


def test_parallel_runs_never_exceed_the_configured_lanes():
    rows = [{"run_id": f"r{i}", "session_id": f"s{i}"} for i in range(5)]
    runtime, log, gates, started, state = lanes_runtime(rows, concurrency=2)
    runtime.start()
    try:
        assert started["r0"].wait(WAIT) and started["r1"].wait(WAIT)
        assert not started["r2"].wait(0.3)
        assert len(runtime.workers) == 2 and len(runtime._inflight) == 2
        for key in ("r0", "r1", "r2", "r3", "r4"):
            gates[key].set()
        for key in ("r2", "r3", "r4"):
            assert started[key].wait(WAIT)
    finally:
        for gate in gates.values():
            gate.set()
        runtime.close()
    assert state["peak"] == 2
    starts = [run for kind, run in log if kind == "start"]
    # Oldest candidates are dispatched first; every Run eventually gets a lane.
    assert set(starts[:2]) == {"r0", "r1"} and sorted(starts) == ["r0", "r1", "r2", "r3", "r4"]


def test_run_concurrency_is_validated_and_one_restores_a_single_lane():
    for invalid in (0, 9):
        with pytest.raises(ValueError):
            StudyRuntime(FakeStudyStore([]), test_study.Authority(), MockProvider(), concurrency=invalid)
    rows = [{"run_id": f"r{i}", "session_id": f"s{i}"} for i in range(2)]
    runtime, log, gates, started, state = lanes_runtime(rows, concurrency=1)
    runtime.start()
    try:
        assert started["r0"].wait(WAIT)
        assert not started["r1"].wait(0.3)
        gates["r0"].set()
        gates["r1"].set()
        assert started["r1"].wait(WAIT)
    finally:
        for gate in gates.values():
            gate.set()
        runtime.close()
    assert state["peak"] == 1


def test_close_stops_dispatch_and_joins_all_lanes():
    closed = []
    authority = test_study.Authority()
    authority.close = lambda: closed.append(True)
    rows = [{"run_id": "r0", "session_id": "s0"}]
    runtime, _, gates, started, _ = lanes_runtime(rows, concurrency=3)
    runtime.authority.authority = authority
    runtime.start()
    assert started["r0"].wait(WAIT)
    gates["r0"].set()
    runtime.close()
    assert closed == [True]
    assert not runtime.thread.is_alive() and not any(worker.is_alive() for worker in runtime.workers)


# --- Real PostgreSQL: two Sessions' Runs overlap with intact fencing ----------------------


class ScopedStore(StudyStore):
    """The real store, but the dispatcher only sees this test's Sessions."""

    def __init__(self, dsn, sessions):
        super().__init__(dsn)
        self.sessions = sessions

    def candidates(self):
        # Same projection and order as StudyStore.candidates, restricted to this test's
        # Sessions so leftovers in a shared test database cannot occupy its 20-row window.
        with self.connect() as conn:
            return conn.execute(
                """SELECT r.*,s.owner_id,s.course_id,s.revision FROM study_run r
                JOIN study_session s USING(session_id) WHERE r.session_id=ANY(%s) AND r.status IN
                ('queued','running','queued_scoped_v1','running_scoped_v1','queued_cards_v1',
                 'running_cards_v1','queued_choice_v1','running_choice_v1') ORDER BY r.created_at""",
                (sorted(self.sessions),),
            ).fetchall()


class ScopedAuthority(test_study.Authority):
    def __init__(self):
        super().__init__()
        self.scopes = []
        self.lock = threading.Lock()

    def read(self, scope, action="CHECK", **arguments):
        span = _span.get() or {}
        with self.lock:
            self.scopes.append((span.get("run_id"), scope["owner_id"], scope["course_id"], action))
        return super().read(scope, action, **arguments)


@pytest.fixture
def two_sessions():
    import os

    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Real PostgreSQL required")
    base = StudyStore(dsn)
    StudyRuntime(base, test_study.Authority(), MockProvider()).initialize()
    scopes = []
    for owner in (42, 43):
        scope = dict(owner_id=owner, course_id="lanes-" + uuid.uuid4().hex, revision=1)
        scope["session_id"] = base.command(
            StudyCommand(**scope, operation="CREATE_SESSION", request_key="lanes"), "mock"
        )["session_id"]
        scopes.append(scope)
    yield dsn, scopes
    for scope in scopes:
        with PostgresSaver.from_conn_string(dsn) as saver:
            saver.delete_thread(scope["session_id"])
        with base.connect() as conn:
            conn.execute("DELETE FROM study_run WHERE session_id=%s", (scope["session_id"],))
            conn.execute("DELETE FROM study_session WHERE session_id=%s", (scope["session_id"],))


def start_run(store, scope, key="lanes-run"):
    command = StudyCommand(**scope, operation="START", request_key=key, goal="解释停止条件并出两道题")
    return store.command(command, "mock")["run"]["run_id"]


def read_run(store, scope, operation="READ"):
    return store.command(StudyCommand(**scope, operation=operation), "mock")


def wait_terminal(store, scopes, timeout=60):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        views = [read_run(store, scope)["run"] for scope in scopes]
        if all(view["status"] in {"succeeded", "failed", "cancelled", "budget_exceeded"} for view in views):
            return views
        time.sleep(0.05)
    raise AssertionError("Runs did not finish")


def test_two_sessions_runs_overlap_with_isolated_scope_budget_and_privacy(two_sessions):
    dsn, scopes = two_sessions
    store = ScopedStore(dsn, {scope["session_id"] for scope in scopes})
    authority = ScopedAuthority()
    provider = MockProvider()
    both_in_model_io = threading.Barrier(2, timeout=WAIT)
    first_call = set()
    original = provider.decide

    def decide(messages, timeout):
        run_id = (_span.get() or {}).get("run_id")
        if run_id not in first_call:
            first_call.add(run_id)
            # Breaks (and fails both Runs) unless the two Runs are inside model I/O together.
            both_in_model_io.wait()
        return original(messages, timeout)

    provider.decide = decide
    runtime = StudyRuntime(store, authority, provider, concurrency=2)
    run_ids = [start_run(store, scope) for scope in scopes]
    runtime.start()
    try:
        views = wait_terminal(store, scopes)
    finally:
        runtime.close()
    assert [view["status"] for view in views] == ["succeeded", "succeeded"]
    assert not both_in_model_io.broken
    by_run = {run_id: scope for run_id, scope in zip(run_ids, scopes, strict=True)}
    for scope, run_id in zip(scopes, run_ids, strict=True):
        result = read_run(store, scope)
        # The same per-Run budget accounting as a serial Run (see test_study).
        assert result["run"]["model_calls"] == 4 and result["run"]["tool_calls"] == 3
        assert result["artifact"]["revision"] == 1 and len(result["artifact"]["questions"]) == 2
        assert all(
            "answer" not in q and "rubric" not in q and "answer_points" not in q
            for q in result["artifact"]["questions"]
        )
        assert result["artifact"]["citations"]
        assert {c["evidence_id"] for c in result["artifact"]["citations"]} <= {"e1", "e2"}
        events = read_run(store, scope, "EVENTS")["events"]
        assert sum(e["event_type"] == "artifact_created" for e in events) == 1
        assert "An algorithm" not in json.dumps(events, default=str)
        assert run_id in by_run
    # Every evidence read made inside a Run used that Run's own owner/course scope.
    inside = [entry for entry in authority.scopes if entry[0] is not None]
    assert {entry[0] for entry in inside} == set(run_ids)
    for run_id, owner, course, _ in inside:
        assert (owner, course) == (by_run[run_id]["owner_id"], by_run[run_id]["course_id"])


def test_cancelling_one_parallel_run_fences_only_that_run(two_sessions):
    dsn, scopes = two_sessions
    store = ScopedStore(dsn, {scope["session_id"] for scope in scopes})
    provider = MockProvider()
    original = provider.decide
    entered = {scope["session_id"]: threading.Event() for scope in scopes}
    release = threading.Event()
    sessions = {}

    def decide(messages, timeout):
        run_id = (_span.get() or {}).get("run_id")
        session = sessions[run_id]
        entered[session].set()
        assert release.wait(WAIT)
        return original(messages, timeout)

    provider.decide = decide
    runtime = StudyRuntime(store, test_study.Authority(), provider, concurrency=2)
    for scope in scopes:
        sessions[start_run(store, scope)] = scope["session_id"]
    cancelled_run = next(run for run, session in sessions.items() if session == scopes[0]["session_id"])
    runtime.start()
    try:
        assert all(event.wait(WAIT) for event in entered.values())
        command = StudyCommand(**scopes[0], operation="CANCEL", run_id=cancelled_run)
        assert store.command(command, "mock")["run"]["status"] == "cancelled"
        release.set()
        views = wait_terminal(store, scopes)
    finally:
        release.set()
        runtime.close()
    assert [view["status"] for view in views] == ["cancelled", "succeeded"]
    cancelled = read_run(store, scopes[0])
    assert cancelled["artifact"] is None and cancelled["run"]["tool_calls"] == 0
    assert read_run(store, scopes[1])["artifact"]["questions"]


# --- Optional event stream (server side; Java keeps polling EVENTS) ----------------------


def signed_command(command, path=EVENT_STREAM_PATH):
    body = command.model_dump_json().encode()
    timestamp = str(int(time.time()))
    return body, {
        "X-LectureLens-Timestamp": timestamp,
        "X-LectureLens-Signature": study_signature(SECRET, timestamp, body, path),
        "Content-Type": "application/json",
    }


class LiveServer:
    """A real loopback uvicorn server, so streamed bytes are observed as they are sent."""

    def __init__(self, app):
        import uvicorn

        self.server = uvicorn.Server(
            uvicorn.Config(app, host="127.0.0.1", port=0, log_level="warning", lifespan="on")
        )
        self.thread = threading.Thread(target=self.server.run, daemon=True)

    def __enter__(self):
        self.thread.start()
        deadline = time.monotonic() + WAIT
        while not self.server.started:
            assert time.monotonic() < deadline and self.thread.is_alive()
            time.sleep(0.01)
        port = self.server.servers[0].sockets[0].getsockname()[1]
        return f"http://127.0.0.1:{port}"

    def __exit__(self, *exc):
        self.server.should_exit = True
        self.thread.join(WAIT)


def parse(lines):
    event, data = None, None
    for line in lines:
        if line.startswith("event: "):
            event = line[7:]
        elif line.startswith("data: "):
            data = json.loads(line[6:])
        elif line == "" and event:
            yield event, data
            event, data = None, None


def stream_app(runtime, **kwargs):
    runtime.start = lambda: None
    return create_app(object(), SECRET, runtime, event_stream=True, **kwargs)


def test_event_stream_is_off_by_default(setup):
    _, _, runtime, scope = setup
    runtime.start = lambda: None
    run = test_study.start(setup)
    command = StudyCommand(**scope, operation="EVENTS", run_id=run["run_id"])
    body, headers = signed_command(command)
    with TestClient(create_app(object(), SECRET, runtime)) as client:
        response = client.post(EVENT_STREAM_PATH, content=body, headers=headers)
    assert response.status_code == 404 and "STUDY_EVENT_STREAM_DISABLED" in response.text


def test_event_stream_emits_incremental_public_events_then_a_final_event(setup):
    store, _, runtime, scope = setup
    run = test_study.start(setup)
    release, finished = threading.Event(), threading.Event()
    original = runtime.provider.decide

    def gated(messages, timeout):
        assert release.wait(WAIT)
        return original(messages, timeout)

    runtime.provider.decide = gated
    worker = threading.Thread(target=lambda: (runtime.execute(run), finished.set()))
    command = StudyCommand(**scope, operation="EVENTS", run_id=run["run_id"])
    seen = []
    with LiveServer(stream_app(runtime)) as url:
        body, headers = signed_command(command)
        with httpx.Client(timeout=WAIT) as client:
            with client.stream("POST", url + EVENT_STREAM_PATH, content=body, headers=headers) as response:
                assert response.status_code == 200
                assert response.headers["content-type"].startswith("text/event-stream")
                worker.start()
                for name, data in parse(response.iter_lines()):
                    seen.append((name, data))
                    if name == "run_started":
                        # Received while the Run is still blocked in model I/O.
                        assert not finished.is_set()
                        release.set()
                    if name in {"stream_end", "stream_pause", "stream_error"}:
                        break
    release.set()
    worker.join(WAIT)
    names = [name for name, _ in seen]
    assert names[0] == "run_queued" and "run_started" in names
    assert names[-2:] == ["run_finished", "stream_end"]
    assert seen[-1][1]["status"] == "succeeded"
    sequences = [data["sequence"] for name, data in seen if not name.startswith("stream_")]
    assert sequences == sorted(set(sequences))
    assert seen[-1][1]["cursor"] == sequences[-1]
    text = json.dumps(seen, ensure_ascii=False, default=str)
    assert "_trace" not in text and "An algorithm" not in text and "answer_points" not in text
    assert "node_started" not in names and "evidence_started" not in names
    events = store.command(StudyCommand(**scope, operation="EVENTS", run_id=run["run_id"]), "mock")
    assert [e["sequence"] for e in events["events"]] == sequences


def test_event_stream_resumes_from_cursor_and_pauses_at_its_time_limit(setup):
    _, _, runtime, scope = setup
    run = test_study.start(setup)
    with LiveServer(stream_app(runtime, stream_seconds=0.3, stream_poll_seconds=0.05)) as url:
        body, headers = signed_command(StudyCommand(**scope, operation="EVENTS", run_id=run["run_id"]))
        with httpx.Client(timeout=WAIT) as client:
            first = list(
                parse(client.post(url + EVENT_STREAM_PATH, content=body, headers=headers).iter_lines())
            )
            cursor = first[-1][1]["cursor"]
            body, headers = signed_command(
                StudyCommand(**scope, operation="EVENTS", run_id=run["run_id"], after=cursor)
            )
            second = list(
                parse(client.post(url + EVENT_STREAM_PATH, content=body, headers=headers).iter_lines())
            )
    assert [name for name, _ in first] == ["run_queued", "stream_pause"]
    assert first[-1][1] == {"status": "queued", "cursor": first[0][1]["sequence"]}
    assert second == [("stream_pause", {"status": "queued", "cursor": cursor})]


def test_event_stream_checks_ownership_before_bytes_and_authority_on_every_read(setup):
    store, authority, runtime, scope = setup
    run = test_study.start(setup)
    stranger = {**scope, "owner_id": scope["owner_id"] + 1}
    with LiveServer(stream_app(runtime, stream_seconds=5, stream_poll_seconds=0.05)) as url:
        with httpx.Client(timeout=WAIT) as client:
            body, headers = signed_command(StudyCommand(**stranger, operation="EVENTS", run_id=run["run_id"]))
            response = client.post(url + EVENT_STREAM_PATH, content=body, headers=headers)
            assert response.status_code == 404 and "SESSION_NOT_FOUND_OR_STALE" in response.text
            body, headers = signed_command(StudyCommand(**scope, operation="EVENTS", run_id=run["run_id"]))
            tampered = body.replace(b'"owner_id":42', b'"owner_id":43')
            assert client.post(url + EVENT_STREAM_PATH, content=tampered, headers=headers).status_code == 401
            other = StudyCommand(**scope, operation="READ", run_id=run["run_id"])
            body, headers = signed_command(other)
            assert client.post(url + EVENT_STREAM_PATH, content=body, headers=headers).status_code == 422
            authority.valid = False
            body, headers = signed_command(StudyCommand(**scope, operation="EVENTS", run_id=run["run_id"]))
            response = client.post(url + EVENT_STREAM_PATH, content=body, headers=headers)
            assert response.status_code == 409 and "COURSE_UNAVAILABLE_OR_CHANGED" in response.text
            authority.valid = True
            with client.stream("POST", url + EVENT_STREAM_PATH, content=body, headers=headers) as response:
                assert response.status_code == 200
                seen = []
                for name, data in parse(response.iter_lines()):
                    seen.append((name, data))
                    if name == "run_queued":
                        authority.valid = False  # e.g. the course is deleted or republished
                    if name.startswith("stream_"):
                        break
    assert [name for name, _ in seen] == ["run_queued", "stream_error"]
    assert seen[-1][1]["code"] == "COURSE_UNAVAILABLE_OR_CHANGED"
