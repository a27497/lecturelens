import copy
import json
import os
import time
import uuid

import psycopg
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from lecturelens_agent.app import PATH, create_app, signature
from lecturelens_agent.contracts import RetrieveRequest
from lecturelens_agent.embedding import validate_vectors
from lecturelens_agent.retrieval import BusyError, Retriever, snapshot_id, split_evidence
from lecturelens_agent.store import VectorStore

SECRET = "test-only-execution-context-key-123456789"


def payload():
    return {
        "request_id": "test-request",
        "owner_id": 1,
        "course_id": "course-" + uuid.uuid4().hex,
        "revision": 1,
        "query": "bread",
        "top_k": 2,
        "evidence": [
            {"evidence_id": "e1", "text": "bread recipe", "start_ms": 0, "end_ms": 1000},
            {"evidence_id": "e2", "text": "matrix vectors", "start_ms": 2000, "end_ms": 3000},
        ],
    }


class FakeEmbedding:
    dimensions = 3
    index_version = "test-vectors-only-v1"

    def __init__(self):
        self.calls = []

    def embed(self, texts):
        self.calls.append(texts)
        return [[1.0, 0.0, 0.0] if "bread" in text else [0.0, 1.0, 0.0] for text in texts]


class UnusedStore:
    def contains(self, key):
        raise AssertionError("Unauthorized request reached retrieval")


def signed(body, timestamp=None):
    timestamp = str(timestamp if timestamp is not None else int(time.time()))
    return {
        "X-LectureLens-Timestamp": timestamp,
        "X-LectureLens-Signature": signature(SECRET, timestamp, body),
        "Content-Type": "application/json",
    }


@pytest.mark.parametrize("mutation", ["unsigned", "expired", "tampered_owner", "wrong_audience"])
def test_rejects_invalid_execution_context(mutation):
    body = json.dumps(payload()).encode()
    headers = signed(body)
    if mutation == "unsigned":
        headers = {}
    elif mutation == "expired":
        headers = signed(body, int(time.time()) - 120)
    elif mutation == "tampered_owner":
        body = body.replace(b'"owner_id": 1', b'"owner_id": 2')
    else:
        headers["X-LectureLens-Signature"] = "0" * 64
    with TestClient(create_app(Retriever(UnusedStore(), FakeEmbedding()), SECRET)) as client:
        assert client.post(PATH, content=body, headers=headers).status_code == 401


def test_contract_errors_do_not_echo_evidence():
    data = payload()
    data["evidence"][0]["end_ms"] = -1
    body = json.dumps(data).encode()
    with TestClient(create_app(Retriever(UnusedStore(), FakeEmbedding()), SECRET)) as client:
        response = client.post(PATH, content=body, headers=signed(body))
        assert response.status_code == 422
        assert "bread" not in response.text


@pytest.mark.parametrize("change", ["duplicate", "oversized", "reversed", "extra_owner"])
def test_invalid_contract(change):
    data = payload()
    if change == "duplicate":
        data["evidence"].append(data["evidence"][0])
    elif change == "oversized":
        data["query"] = "q" * 501
    elif change == "reversed":
        data["time_window"] = {"start_ms": 20, "end_ms": 10}
    else:
        data["evidence"][0]["owner_id"] = 2
    with pytest.raises(ValidationError):
        RetrieveRequest.model_validate(data)


@pytest.mark.parametrize("vectors", [[[1, 2]], [[0, 0, 0]], [[float("nan"), 1, 2]], []])
def test_invalid_embeddings(vectors):
    with pytest.raises(ValueError):
        validate_vectors(vectors, 1, 3)


def test_snapshot_fingerprint_includes_scope_version_and_content():
    data = payload()
    request = RetrieveRequest.model_validate(data)
    original = snapshot_id(request, "v1")
    for field, value in [("owner_id", 2), ("course_id", "other"), ("revision", 2)]:
        changed = copy.deepcopy(data)
        changed[field] = value
        assert snapshot_id(RetrieveRequest.model_validate(changed), "v1") != original
    changed = copy.deepcopy(data)
    changed["evidence"][0]["text"] = "changed source"
    assert snapshot_id(RetrieveRequest.model_validate(changed), "v1") != original
    assert snapshot_id(request, "v2") != original
    request.evidence.reverse()
    assert snapshot_id(request, "v1") == original


def test_chunks_preserve_full_text_and_original_timestamps():
    data = payload()
    text = "abcdefghij" * 61
    data["evidence"] = [{"evidence_id": "long", "text": text, "start_ms": 3, "end_ms": 9}]
    chunks = split_evidence(RetrieveRequest.model_validate(data).evidence)
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
        def contains(self, key):
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


def test_real_pgvector_http_retrieval_and_cache(store):
    embedder = FakeEmbedding()
    data = payload()
    body = json.dumps(data).encode()
    with TestClient(create_app(Retriever(store, embedder), SECRET)) as client:
        first = client.post(PATH, content=body, headers=signed(body))
        assert first.status_code == 200, first.text
        assert first.json()["hits"][0]["evidence_id"] == "e1"
        assert not first.json()["cache_hit"]
        second = client.post(PATH, content=body, headers=signed(body))
        assert second.json()["cache_hit"]
        assert len(embedder.calls) == 3  # one document batch, two queries
        data["time_window"] = {"start_ms": 2100, "end_ms": 2200}
        body = json.dumps(data).encode()
        filtered = client.post(PATH, content=body, headers=signed(body)).json()
        assert [h["evidence_id"] for h in filtered["hits"]] == ["e2"]
        data["time_window"] = {"start_ms": 9000, "end_ms": 10000}
        body = json.dumps(data).encode()
        assert client.post(PATH, content=body, headers=signed(body)).json()["hits"] == []


def test_store_rejects_cross_owner_course_revision_and_index(store):
    request = RetrieveRequest.model_validate(payload())
    retriever = Retriever(store, FakeEmbedding())
    result = retriever.search(request)
    for field, value in [("owner_id", 2), ("course_id", "different"), ("revision", 2)]:
        other = request.model_copy(update={field: value})
        assert store.search(result.snapshot_id, other, retriever.embedder.index_version, [1, 0, 0]) == []
    assert store.search(result.snapshot_id, request, "different-index", [1, 0, 0]) == []


def test_changed_snapshot_never_reuses_old_vectors(store):
    request = RetrieveRequest.model_validate(payload())
    retriever = Retriever(store, FakeEmbedding())
    old = retriever.search(request)
    request.revision = 2
    request.evidence = [request.evidence[1]]
    new = retriever.search(request)
    assert old.snapshot_id != new.snapshot_id
    assert [h.evidence_id for h in new.hits] == ["e2"]


def test_atomic_publication_rolls_back_failed_vector_batch(store):
    request = RetrieveRequest.model_validate(payload())
    key = snapshot_id(request, "invalid-test")
    chunks = split_evidence(request.evidence)
    # PostgreSQL rejects NaN vectors; even the first successful insert must roll back.
    with pytest.raises(psycopg.Error):
        store.save(key, request, "invalid-test", chunks, [[1, 0, 0], [float("nan"), 0, 0]])
    assert not store.contains(key)


def test_expired_snapshot_is_unreadable_and_rebuilt(store):
    request = RetrieveRequest.model_validate(payload())
    retriever = Retriever(store, FakeEmbedding())
    first = retriever.search(request)
    with store.connect() as conn:
        conn.execute(
            "UPDATE retrieval_snapshot SET created_at=now()-interval '25 hours' WHERE snapshot_id=%s",
            (first.snapshot_id,),
        )
    assert store.search(first.snapshot_id, request, retriever.embedder.index_version, [1, 0, 0]) == []
    assert not retriever.search(request).cache_hit
