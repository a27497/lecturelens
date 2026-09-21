import copy
import hashlib
import json
import os
import time
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from lecturelens_agent.app import PATH, SYNC_PATH, create_app, signature
from lecturelens_agent.contracts import Evidence, EvidenceMetadata, RetrieveRequest, SyncRequest, TimeWindow
from lecturelens_agent.embedding import validate_vectors
from lecturelens_agent.retrieval import BusyError, IndexNotReady, Retriever, split_evidence
from lecturelens_agent.store import StaleSync, VectorStore

SECRET = "test-only-execution-context-key-123456789"


def evidence():
    return [
        Evidence(evidence_id="e1", text="bread recipe", start_ms=0, end_ms=1000),
        Evidence(evidence_id="e2", text="matrix vectors", start_ms=2000, end_ms=3000),
    ]


def payload():
    return dict(
        request_id="test-request",
        owner_id=1,
        course_id="course-" + uuid.uuid4().hex,
        revision=1,
        query="bread",
        top_k=2,
        allowed_evidence_ids=["e1", "e2"],
    )


def sync_request(query, sequence=1, items=None, operation="APPLY"):
    items = evidence() if items is None else items
    return SyncRequest(
        request_id=query.request_id,
        owner_id=query.owner_id,
        course_id=query.course_id,
        revision=query.revision,
        sequence=sequence,
        operation=operation,
        manifest=[
            EvidenceMetadata(
                evidence_id=e.evidence_id,
                content_hash=hashlib.sha256(e.text.encode()).hexdigest(),
                start_ms=e.start_ms,
                end_ms=e.end_ms,
            )
            for e in items
        ],
        upserts=items if operation == "APPLY" else [],
        index_version=FakeEmbedding.index_version,
    )


class FakeEmbedding:
    dimensions = 3
    index_version = "test-vectors-only-v1"

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [[1.0, 0.0, 0.0] if "bread" in text else [0.0, 1.0, 0.0] for text in texts]


class UnusedStore:
    def ready_snapshot(self, *args):
        raise AssertionError("Unauthorized request reached retrieval")


def signed(body, timestamp=None, path=PATH):
    timestamp = str(timestamp if timestamp is not None else int(time.time()))
    return {
        "X-LectureLens-Timestamp": timestamp,
        "X-LectureLens-Signature": signature(SECRET, timestamp, body, path),
        "Content-Type": "application/json",
    }


@pytest.mark.parametrize("path", [PATH, SYNC_PATH])
@pytest.mark.parametrize("mutation", ["unsigned", "expired", "tampered_owner", "wrong_path"])
def test_rejects_invalid_execution_context(path, mutation):
    body = json.dumps(payload()).encode()
    headers = signed(body, path=path)
    if mutation == "unsigned":
        headers = {}
    elif mutation == "expired":
        headers = signed(body, int(time.time()) - 120, path)
    elif mutation == "tampered_owner":
        body = body.replace(b'"owner_id": 1', b'"owner_id": 2')
    else:
        headers = signed(body, path="/another-path")
    with TestClient(create_app(Retriever(UnusedStore(), FakeEmbedding()), SECRET)) as client:
        assert client.post(path, content=body, headers=headers).status_code == 401


def test_query_rejects_full_text_contract_without_echo():
    data = payload()
    data["evidence"] = [e.model_dump() for e in evidence()]
    body = json.dumps(data).encode()
    with TestClient(create_app(Retriever(UnusedStore(), FakeEmbedding()), SECRET)) as client:
        response = client.post(PATH, content=body, headers=signed(body))
        assert response.status_code == 422
        assert "bread" not in response.text


@pytest.mark.parametrize("change", ["blank", "oversized", "reversed", "extra_owner"])
def test_invalid_contract(change):
    data = payload()
    if change == "blank":
        data["query"] = " "
    elif change == "oversized":
        data["query"] = "q" * 501
    elif change == "reversed":
        data["time_window"] = {"start_ms": 20, "end_ms": 10}
    else:
        data["user_id"] = 2
    with pytest.raises(ValidationError):
        RetrieveRequest.model_validate(data)


@pytest.mark.parametrize("vectors", [[[1, 2]], [[0, 0, 0]], [[float("nan"), 1, 2]], []])
def test_invalid_embeddings(vectors):
    with pytest.raises(ValueError):
        validate_vectors(vectors, 1, 3)


def test_chunks_preserve_full_text_and_original_timestamps():
    text = "abcdefghij" * 61
    chunks = split_evidence([Evidence(evidence_id="long", text=text, start_ms=3, end_ms=9)])
    assert len(chunks) == 3
    assert chunks[0][1] + "".join(c[1][40:] for c in chunks[1:]) == text
    assert all(c[0].start_ms == 3 and c[0].end_ms == 9 for c in chunks)


def test_busy_admission_does_not_queue_embedding():
    retriever = Retriever(UnusedStore(), FakeEmbedding())
    with retriever.lock, pytest.raises(BusyError):
        retriever.search(RetrieveRequest.model_validate(payload()))


def test_busy_http_response():
    retriever = Retriever(UnusedStore(), FakeEmbedding())
    body = json.dumps(payload()).encode()
    with TestClient(create_app(retriever, SECRET)) as client, retriever.lock:
        response = client.post(PATH, content=body, headers=signed(body))
        assert response.status_code == 503
        assert response.headers["Retry-After"] == "1"


def test_database_failure_is_redacted():
    class FailedStore:
        def ready_snapshot(self, *args):
            raise RuntimeError("postgresql://private-credential@internal-db")

    body = json.dumps(payload()).encode()
    with TestClient(create_app(Retriever(FailedStore(), FakeEmbedding()), SECRET)) as client:
        response = client.post(PATH, content=body, headers=signed(body))
        assert response.status_code == 503
        assert "private-credential" not in response.text


def test_missing_execution_key_fails_startup():
    with pytest.raises(RuntimeError), TestClient(create_app(Retriever(UnusedStore(), FakeEmbedding()), "")):
        pass


@pytest.fixture
def store():
    dsn = os.environ.get("AGENT_TEST_DATABASE_URL")
    if not dsn:
        pytest.skip("Set AGENT_TEST_DATABASE_URL for real pgvector integration tests")
    instance = VectorStore(dsn)
    instance.initialize()
    return instance


def test_real_http_background_sync_then_query_only_embeddings(store):
    embedder = FakeEmbedding()
    query = RetrieveRequest.model_validate(payload())
    with TestClient(create_app(Retriever(store, embedder), SECRET)) as client:
        body = query.model_dump_json().encode()
        assert client.post(PATH, content=body, headers=signed(body)).status_code == 409
        assert embedder.calls == []
        plan = sync_request(query, operation="PLAN").model_dump_json().encode()
        assert client.post(SYNC_PATH, content=plan, headers=signed(plan, path=SYNC_PATH)).json()[
            "missing_ids"
        ] == ["e1", "e2"]
        delta = sync_request(query).model_dump_json().encode()
        response = client.post(SYNC_PATH, content=delta, headers=signed(delta, path=SYNC_PATH))
        assert response.status_code == 200, response.text
        assert response.json()["state"] == "READY"
        for _ in range(2):
            result = client.post(PATH, content=body, headers=signed(body))
            assert result.status_code == 200, result.text
            assert result.json()["hits"][0]["evidence_id"] == "e1"
        assert embedder.calls == [["bread recipe", "matrix vectors"], ["bread"], ["bread"]]
        query.time_window = TimeWindow(start_ms=2100, end_ms=2200)
        body = query.model_dump_json().encode()
        assert [
            h["evidence_id"] for h in client.post(PATH, content=body, headers=signed(body)).json()["hits"]
        ] == ["e2"]


def test_restart_retains_ready_index_without_reembedding(store):
    query = RetrieveRequest.model_validate(payload())
    Retriever(store, FakeEmbedding()).sync(sync_request(query))
    new_embedding = FakeEmbedding()
    recovered = Retriever(VectorStore(store.dsn), new_embedding)
    assert recovered.sync(sync_request(query, operation="PLAN"))["state"] == "READY"
    assert recovered.search(query).hits[0].evidence_id == "e1"
    assert new_embedding.calls == [["bread"]]


def test_incremental_update_reuses_unchanged_chunks_and_removes_old_rows(store):
    query = RetrieveRequest.model_validate(payload())
    embedder = FakeEmbedding()
    retriever = Retriever(store, embedder)
    retriever.sync(sync_request(query))
    query.revision = 2
    # Evidence IDs change with revision; identical text must still reuse its vector.
    items = [
        evidence()[0].model_copy(update={"evidence_id": "e3"}),
        Evidence(evidence_id="e4", text="new bread fact", start_ms=4000, end_ms=5000),
    ]
    request = sync_request(query, 2, items)
    plan = retriever.sync(request.model_copy(update={"operation": "PLAN", "upserts": []}))
    assert plan["missing_ids"] == ["e4"]
    # Unchanged e3 has a new versioned ID but no text is sent.
    request = request.model_copy(update={"upserts": [items[1]]})
    retriever.sync(request)
    assert embedder.calls == [["bread recipe", "matrix vectors"], ["new bread fact"]]
    assert (
        retriever.sync(request.model_copy(update={"operation": "PLAN", "upserts": []}))["missing_ids"] == []
    )
    # Replayed apply is idempotent and performs no embedding.
    retriever.sync(request)
    assert len(embedder.calls) == 2
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT evidence_id FROM indexed_evidence WHERE course_id=%s", (query.course_id,)
        ).fetchall()
        assert sorted(r[0] for r in rows) == ["e3", "e4"]
        assert (
            conn.execute(
                "SELECT count(*) FROM evidence_vector WHERE course_id=%s", (query.course_id,)
            ).fetchone()[0]
            == 2
        )


def test_manifest_only_removal_and_empty_snapshot(store):
    query = RetrieveRequest.model_validate(payload())
    embedder = FakeEmbedding()
    retriever = Retriever(store, embedder)
    retriever.sync(sync_request(query))
    query.revision = 2
    delta = sync_request(query, 2, [evidence()[1]]).model_copy(update={"upserts": []})
    retriever.sync(delta)
    assert [h.evidence_id for h in retriever.search(query).hits] == ["e2"]
    query.revision = 3
    retriever.sync(sync_request(query, 3, []))
    assert retriever.search(query).hits == []
    assert len([call for call in embedder.calls if call != ["bread"]]) == 1


def test_delete_without_queries_and_late_apply_cannot_resurrect(store):
    query = RetrieveRequest.model_validate(payload())
    retriever = Retriever(store, FakeEmbedding())
    original = sync_request(query)
    retriever.sync(original)
    # Deletion is admitted even while another document embedding holds the CPU lock.
    with retriever.lock:
        result = retriever.sync(sync_request(query, 2, [], "DELETE"))
    assert result["state"] == "DELETED"
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM evidence_vector WHERE course_id=%s", (query.course_id,)
            ).fetchone()[0]
            == 0
        )
    with pytest.raises(IndexNotReady):
        retriever.search(query)
    with pytest.raises(StaleSync):
        retriever.sync(original)
    with pytest.raises(StaleSync):
        retriever.sync(original.model_copy(update={"sequence": 999}))
    assert retriever.sync(sync_request(query, 2, [], "DELETE"))["state"] == "DELETED"


def test_older_revision_cannot_replace_newer_projection(store):
    query = RetrieveRequest.model_validate(payload())
    retriever = Retriever(store, FakeEmbedding())
    old = sync_request(query)
    query.revision = 2
    retriever.sync(sync_request(query, 2))
    with pytest.raises(StaleSync):
        retriever.sync(old)
    assert store.ready_snapshot(query, FakeEmbedding.index_version)


def test_authority_and_allowed_language_ids_are_hard_filters(store):
    query = RetrieveRequest.model_validate(payload())
    retriever = Retriever(store, FakeEmbedding())
    retriever.sync(sync_request(query))
    for field, value in [("owner_id", 2), ("course_id", "different"), ("revision", 2)]:
        with pytest.raises(IndexNotReady):
            retriever.search(query.model_copy(update={field: value}))
    query.allowed_evidence_ids = ["e2"]
    assert [h.evidence_id for h in retriever.search(query).hits] == ["e2"]


def test_atomic_publication_rolls_back_failed_vector_batch(store):
    query = RetrieveRequest.model_validate(payload())
    request = sync_request(query)
    chunks = split_evidence(request.upserts)
    with pytest.raises(psycopg.Error):
        store.apply(
            request, FakeEmbedding.index_version, chunks, ["h1", "h2"], [[1, 0, 0], [float("nan"), 0, 0]]
        )
    assert store.ready_snapshot(query, FakeEmbedding.index_version) is None


def test_incomplete_delta_keeps_previous_revision(store):
    query = RetrieveRequest.model_validate(payload())
    retriever = Retriever(store, FakeEmbedding())
    retriever.sync(sync_request(query))
    old = copy.deepcopy(query)
    query.revision = 2
    incomplete = sync_request(query, 2).model_copy(
        update={
            "manifest": [
                EvidenceMetadata(evidence_id="missing", content_hash="0" * 64, start_ms=0, end_ms=1)
            ],
            "upserts": [],
        }
    )
    with pytest.raises(ValueError):
        retriever.sync(incomplete)
    assert store.ready_snapshot(old, FakeEmbedding.index_version)
    assert store.ready_snapshot(query, FakeEmbedding.index_version) is None


def test_index_version_change_requires_rebuild_and_cleans_old_vectors(store):
    query = RetrieveRequest.model_validate(payload())
    Retriever(store, FakeEmbedding()).sync(sync_request(query))
    embedder = FakeEmbedding()
    embedder.index_version = "new-model-and-chunker"
    retriever = Retriever(store, embedder)
    with pytest.raises(IndexNotReady):
        retriever.search(query)
    assert retriever.sync(sync_request(query, operation="PLAN"))["missing_ids"] == ["e1", "e2"]
    retriever.sync(sync_request(query).model_copy(update={"index_version": embedder.index_version}))
    assert embedder.calls == [["bread recipe", "matrix vectors"]]
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM evidence_vector WHERE course_id=%s", (query.course_id,)
            ).fetchone()[0]
            == 2
        )


def test_manifest_hash_cannot_disagree_with_source_or_existing_id(store):
    query = RetrieveRequest.model_validate(payload())
    retriever = Retriever(store, FakeEmbedding())
    original = sync_request(query)
    retriever.sync(original)
    conflicting = original.model_dump()
    conflicting["manifest"][0]["content_hash"] = "0" * 64
    with pytest.raises(ValidationError):
        SyncRequest.model_validate(conflicting)
    conflicting["operation"] = "PLAN"
    conflicting["upserts"] = []
    with pytest.raises(ValueError):
        retriever.sync(SyncRequest.model_validate(conflicting))
