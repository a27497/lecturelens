"""Local acceptance factory: real product app with deterministic offline embedding only."""

import hashlib
import os

from lecturelens_agent.retrieval import Retriever
from lecturelens_agent.store import VectorStore
from lecturelens_real_eval.tutor.app import create_app as real_app


class OfflineEmbedding:
    dimensions = 384
    index_version = "p9-acceptance-hash-v1"

    def embed(self, texts):
        result = []
        for text in texts:
            row = [0.0] * self.dimensions
            for word in text.lower().split():
                row[
                    int.from_bytes(hashlib.sha256(word.encode()).digest()[:2], "big")
                    % self.dimensions
                ] += 1
            if not any(row):
                row[0] = 1.0
            result.append(row)
        return result


def create_app():
    assert os.environ["AGENT_LLM_MODE"] == "mock"
    store = VectorStore(os.environ["AGENT_DATABASE_URL"])
    store.initialize()
    return real_app(retriever=Retriever(store, OfflineEmbedding()))
