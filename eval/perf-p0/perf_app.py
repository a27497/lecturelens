"""Eval-only adapters. Product locks, slots, stores, workers and providers are unchanged."""

import hashlib
import hmac
import logging
import os
import re
import threading
import time
from collections import Counter

from fastapi import HTTPException, Request
from lecturelens_agent.app import bounded_setting, course_authority, signature
from lecturelens_agent.retrieval import (
    DEFAULT_QUERY_CONCURRENCY,
    MAX_QUERY_CONCURRENCY,
    BusyError,
    IndexNotReady,
    Retriever,
)
from lecturelens_agent.store import StaleSync, VectorStore
from lecturelens_agent.study.models import ModelRegistry
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import (
    DEFAULT_RUN_CONCURRENCY,
    MAX_RUN_CONCURRENCY,
    StudyRuntime,
)
from lecturelens_agent.study.store import StudyStore
from lecturelens_real_eval.tutor.app import create_app as product_app
from lecturelens_real_eval.tutor.runtime import MockTutor, TutorRuntime
from lecturelens_real_eval.tutor.store import TutorStore
from load import OUTCOME_KEYS, OUTCOMES_PATH

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


def check_delay(delay_ms):
    if not 0 <= delay_ms <= 5000:
        raise ValueError("Mock delay must be between 0 and 5000 ms")
    return delay_ms / 1000


class DelayedMockTutor(MockTutor):
    def __init__(self, delay_ms):
        self.delay = check_delay(delay_ms)

    def decide(self, messages, schemas, timeout):
        # Delay belongs to each model decision, not the load client's timer.
        time.sleep(self.delay)
        log.warning("PERF_MOCK_TUTOR_DECIDE delay_ms=%d", round(self.delay * 1000))
        return super().decide(messages, schemas, timeout)


class DelayedStudyMock(MockProvider):
    """Holds a Run lane for each flashcard decision, like model I/O would."""

    def __init__(self, delay_ms):
        self.delay = check_delay(delay_ms)

    def flashcards(self, messages, schemas, timeout):
        time.sleep(self.delay)
        log.warning("PERF_MOCK_STUDY_DECIDE delay_ms=%d", round(self.delay * 1000))
        return super().flashcards(messages, schemas, timeout)


class CountingRetriever(Retriever):
    """Original search admission plus server-side outcome counters.

    Java turns every non-200 retrieval into RETRIEVAL_UNAVAILABLE, so Java QA, Tutor and
    Study clients cannot tell a busy 503 from a 409 snapshot change. These counters
    attribute them at the Python boundary without changing admission or responses.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._outcomes = Counter()
        self._outcome_lock = threading.Lock()

    def _count(self, name):
        with self._outcome_lock:
            self._outcomes[name] += 1

    def outcomes(self):
        with self._outcome_lock:
            return {name: self._outcomes[name] for name in OUTCOME_KEYS}

    def search(self, request):
        try:
            result = super().search(request)
        except BusyError:
            self._count("busy_503")
            raise
        except IndexNotReady:
            self._count("index_not_ready_409")
            raise
        except StaleSync:
            self._count("index_changed_409")
            raise
        except Exception:
            self._count("error")
            raise
        self._count("ok")
        return result


def add_outcome_route(app, retriever):
    @app.post(OUTCOMES_PATH)
    async def retrieval_outcomes(request: Request):
        # Same HMAC contract as the retrieval route; the counters carry no course data.
        timestamp = request.headers.get("X-LectureLens-Timestamp", "")
        supplied = request.headers.get("X-LectureLens-Signature", "")
        body = await request.body()
        try:
            fresh = abs(time.time() - int(timestamp)) <= 60
        except ValueError:
            fresh = False
        if (
            not fresh
            or not re.fullmatch(r"[0-9a-f]{64}", supplied)
            or not hmac.compare_digest(
                signature(app.state.secret, timestamp, body, OUTCOMES_PATH), supplied
            )
        ):
            raise HTTPException(401, "Invalid execution context")
        return retriever.outcomes()


def run_deadline_seconds():
    # Same parsing and range as the product lifespan in lecturelens_agent.app.
    seconds = int(os.environ.get("AGENT_RUN_DEADLINE_SECONDS", "90"))
    if not 30 <= seconds <= 300:
        raise RuntimeError("AGENT_RUN_DEADLINE_SECONDS must be between 30 and 300")
    return seconds


def create_app():
    if os.environ.get("AGENT_LLM_MODE") != "mock":
        raise RuntimeError("Perf harness requires AGENT_LLM_MODE=mock")
    delay = int(os.environ["PERF_MOCK_MODEL_DELAY_MS"])
    dsn = os.environ["AGENT_DATABASE_URL"]
    secret = os.environ["AGENT_SERVICE_SECRET"]
    java = os.environ["AGENT_JAVA_BASE_URL"]
    # The product reads these two settings only when it builds the Retriever and
    # StudyRuntime itself; passing adapters bypasses that, so parse them identically.
    retrieval_lanes = bounded_setting(
        "AGENT_RETRIEVAL_CONCURRENCY",
        DEFAULT_QUERY_CONCURRENCY,
        1,
        MAX_QUERY_CONCURRENCY,
    )
    run_lanes = bounded_setting(
        "AGENT_RUN_CONCURRENCY", DEFAULT_RUN_CONCURRENCY, 1, MAX_RUN_CONCURRENCY
    )
    store = VectorStore(dsn)
    store.initialize()
    retriever = CountingRetriever(
        store, HashEmbedding(), query_concurrency=retrieval_lanes
    )
    tutor = TutorRuntime(
        TutorStore(dsn),
        course_authority(java, secret),
        provider=DelayedMockTutor(delay),
    )
    registry = ModelRegistry(dsn, secret)
    registry.initialize()
    study = StudyRuntime(
        StudyStore(dsn, model_resolver=registry.freeze),
        course_authority(java, secret),
        DelayedStudyMock(delay),
        seconds=run_deadline_seconds(),
        concurrency=run_lanes,
    )
    log.warning(
        "PERF_FACTORY hash384; retrieval_concurrency=%d; run_concurrency=%d; "
        "tutor_workers=1; mock only",
        retriever.query_concurrency,
        study.concurrency,
    )
    app = product_app(
        retriever=retriever, tutor=tutor, study_runtime=study, model_registry=registry
    )
    add_outcome_route(app, retriever)
    return app
