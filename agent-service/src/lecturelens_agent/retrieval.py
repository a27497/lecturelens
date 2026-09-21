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


class Retriever:
    def __init__(self, store, embedder):
        self.store = store
        self.embedder = embedder
        self.lock = threading.Lock()

    def search(self, request: RetrieveRequest) -> RetrieveResponse:
        # Bounded CPU admission, no unbounded queue of cold-index requests per worker.
        if not self.lock.acquire(blocking=False):
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
            self.lock.release()

    def sync(self, request: SyncRequest):
        version = self.embedder.index_version
        if request.operation == "DELETE":
            # Deletion must not wait for the embedding admission lock.
            return self.store.delete(request, version)
        if request.operation == "PLAN":
            return self.store.plan(request, version)
        if request.index_version != version:
            raise ValueError("Index version changed; plan again")
        if not self.lock.acquire(blocking=False):
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
            self.lock.release()


class IndexNotReady(Exception):
    pass
