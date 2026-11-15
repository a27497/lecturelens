import hashlib
import threading

from .contracts import Evidence, RetrieveRequest, RetrieveResponse, SyncRequest
from .embedding import validate_vectors


class BusyError(Exception):
    pass


def split_evidence(evidence: list[Evidence]) -> list[tuple[Evidence, str]]:
    chunks = []
    for item in evidence:
        # Preserve the source evidence range; do not fabricate sub-caption timestamps.
        for offset in range(0, len(item.text), 200):
            chunks.append((item, item.text[offset : offset + 240]))
            if offset + 240 >= len(item.text):
                break
    if len(chunks) > 5000:
        raise ValueError("Chunk limit exceeded")
    return chunks


DEFAULT_QUERY_CONCURRENCY = 4
MAX_QUERY_CONCURRENCY = 16


class Retriever:
    def __init__(self, store, embedder, *, query_concurrency=DEFAULT_QUERY_CONCURRENCY):
        if not 1 <= query_concurrency <= MAX_QUERY_CONCURRENCY:
            raise ValueError("Query concurrency out of range")
        self.store = store
        self.embedder = embedder
        self.query_concurrency = query_concurrency
        # Queries and index builds are admitted separately: a long document embedding
        # never makes short query embeddings busy, and queries never delay publication.
        # Both remain non-blocking, so neither path builds an unbounded in-process queue.
        # Same-course consistency is fenced in PostgreSQL (snapshot_id / sequence checks).
        self.query_slots = threading.BoundedSemaphore(query_concurrency)
        self.index_lock = threading.Lock()

    def search(self, request: RetrieveRequest) -> RetrieveResponse:
        # Bounded CPU admission, no unbounded queue of cold-index requests per worker.
        if not self.query_slots.acquire(blocking=False):
            raise BusyError()
        try:
            key = self.store.ready_snapshot(request, self.embedder.index_version)
            if key is None:
                raise IndexNotReady()
            query_vectors = self.embedder.embed([request.query])
            validate_vectors(query_vectors, 1, self.embedder.dimensions)
            hits = self.store.search(key, request, self.embedder.index_version, query_vectors[0])
            return RetrieveResponse(
                request_id=request.request_id,
                owner_id=request.owner_id,
                course_id=request.course_id,
                revision=request.revision,
                index_version=self.embedder.index_version,
                snapshot_id=key,
                cache_hit=True,
                hits=hits,
            )
        finally:
            self.query_slots.release()

    def sync(self, request: SyncRequest):
        version = self.embedder.index_version
        if request.operation == "DELETE":
            # Deletion must not wait for the index admission lock.
            return self.store.delete(request, version)
        if request.operation == "PLAN":
            return self.store.plan(request, version)
        if request.index_version != version:
            raise ValueError("Index version changed; plan again")
        if not self.index_lock.acquire(blocking=False):
            raise BusyError()
        try:
            chunks = split_evidence(request.upserts)
            hashes = [hashlib.sha256(text.encode()).hexdigest() for _, text in chunks]
            reused = self.store.reusable_vectors(request, version, hashes)
            missing = dict(
                (key, text) for key, (_, text) in zip(hashes, chunks, strict=True) if key not in reused
            )
            if missing:
                vectors = self.embedder.embed(list(missing.values()))
                validate_vectors(vectors, len(missing), self.embedder.dimensions)
                reused.update(zip(missing, vectors, strict=True))
            return self.store.apply(request, version, chunks, hashes, [reused[key] for key in hashes])
        finally:
            self.index_lock.release()


class IndexNotReady(Exception):
    pass
