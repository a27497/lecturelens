import hashlib
import json
import threading

from .contracts import Evidence, RetrieveRequest, RetrieveResponse
from .embedding import validate_vectors


class BusyError(Exception):
    pass


def snapshot_id(request: RetrieveRequest, index_version: str) -> str:
    snapshot = {
        "owner": request.owner_id,
        "course": request.course_id,
        "revision": request.revision,
        "index": index_version,
        "evidence": [e.model_dump() for e in sorted(request.evidence, key=lambda e: e.evidence_id)],
    }
    return hashlib.sha256(json.dumps(snapshot, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


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
            key = snapshot_id(request, self.embedder.index_version)
            cached = self.store.contains(key)
            if not cached:
                chunks = split_evidence(request.evidence)
                vectors = self.embedder.embed([text for _, text in chunks])
                validate_vectors(vectors, len(chunks), self.embedder.dimensions)
                self.store.save(key, request, self.embedder.index_version, chunks, vectors)
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
                cache_hit=cached,
                hits=hits,
            )
        finally:
            self.lock.release()
