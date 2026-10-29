"""Eval-only adapters. Original locks, stores, workers and providers are unchanged."""

import hashlib
import logging
import os
import time

from lecturelens_agent.retrieval import Retriever
from lecturelens_agent.store import VectorStore
from lecturelens_agent.study.authority import course_authority
from lecturelens_real_eval.tutor.app import create_app as product_app
from lecturelens_real_eval.tutor.runtime import MockTutor, TutorRuntime
from lecturelens_real_eval.tutor.store import TutorStore

log = logging.getLogger("perf-p0")


class HashEmbedding:
    """No download/inference; not a semantic embedding performance measurement."""

    dimensions = 384
    index_version = "perf-p0-hash384-v1"

    def embed(self, texts):
        rows = []
        for text in texts:
            row = [0.0] * self.dimensions
            for word in text.lower().split():
                index = int.from_bytes(
                    hashlib.sha256(word.encode()).digest()[:2], "big"
                )
                row[index % self.dimensions] += 1
            if not any(row):
                row[0] = 1.0
            rows.append(row)
        return rows


class DelayedMockTutor(MockTutor):
    def __init__(self, delay_ms):
        if not 0 <= delay_ms <= 5000:
            raise ValueError("Mock delay must be between 0 and 5000 ms")
        self.delay = delay_ms / 1000

    def decide(self, messages, schemas, timeout):
        # Delay belongs to each model decision, not the load client's timer.
        time.sleep(self.delay)
        log.warning("PERF_MOCK_TUTOR_DECIDE delay_ms=%d", round(self.delay * 1000))
        return super().decide(messages, schemas, timeout)


def create_app():
    if os.environ.get("AGENT_LLM_MODE") != "mock":
        raise RuntimeError("Perf harness requires AGENT_LLM_MODE=mock")
    delay = int(os.environ["PERF_MOCK_MODEL_DELAY_MS"])
    store = VectorStore(os.environ["AGENT_DATABASE_URL"])
    store.initialize()
    tutor = TutorRuntime(
        TutorStore(os.environ["AGENT_DATABASE_URL"]),
        course_authority(
            os.environ["AGENT_JAVA_BASE_URL"], os.environ["AGENT_SERVICE_SECRET"]
        ),
        provider=DelayedMockTutor(delay),
    )
    log.warning(
        "PERF_FACTORY hash384; original Retriever; one original Tutor worker; mock only"
    )
    return product_app(retriever=Retriever(store, HashEmbedding()), tutor=tutor)
