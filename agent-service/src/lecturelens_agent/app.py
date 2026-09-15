import hashlib
import hmac
import logging
import os
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .contracts import RetrieveRequest, RetrieveResponse
from .embedding import LocalEmbedding
from .retrieval import BusyError, Retriever
from .store import VectorStore

PATH = "/internal/v1/retrieve"
AUDIENCE = "lecturelens-retrieval-v1"
MAX_BODY_BYTES = 4 * 1024 * 1024
log = logging.getLogger(__name__)


def signature(secret: str, timestamp: str, body: bytes) -> str:
    message = f"{AUDIENCE}\nPOST\n{PATH}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def create_app(retriever=None, secret=None):
    @asynccontextmanager
    async def lifespan(app):
        key = secret if secret is not None else os.environ.get("AGENT_SERVICE_SECRET", "")
        if len(key.encode()) < 32:
            raise RuntimeError("AGENT_SERVICE_SECRET must contain at least 32 bytes")
        app.state.secret = key
        if retriever is None:
            store = VectorStore(os.environ["AGENT_DATABASE_URL"])
            store.initialize()
            embedder = LocalEmbedding(os.environ.get("AGENT_CACHE_DIR", ".cache"))
            app.state.retriever = Retriever(store, embedder)
        else:
            app.state.retriever = retriever
        yield

    app = FastAPI(
        title="LectureLens Evidence Retrieval",
        version="0.1.0",
        lifespan=lifespan,
        docs_url=None,
        redoc_url=None,
        openapi_url=None,
    )

    @app.get("/healthz")
    def health():
        return {"status": "ready", "index_version": app.state.retriever.embedder.index_version}

    @app.post(PATH, response_model=RetrieveResponse)
    async def retrieve(request: Request):
        timestamp = request.headers.get("X-LectureLens-Timestamp", "")
        try:
            valid_time = abs(time.time() - int(timestamp)) <= 60
        except ValueError:
            valid_time = False
        if not valid_time:
            raise HTTPException(401, "Invalid execution context")
        body = bytearray()
        async for piece in request.stream():
            body.extend(piece)
            if len(body) > MAX_BODY_BYTES:
                raise HTTPException(413, "Snapshot too large")
        expected = signature(app.state.secret, timestamp, bytes(body))
        supplied = request.headers.get("X-LectureLens-Signature", "")
        if not re.fullmatch(r"[0-9a-f]{64}", supplied) or not hmac.compare_digest(expected, supplied):
            raise HTTPException(401, "Invalid execution context")
        try:
            payload = RetrieveRequest.model_validate_json(body)
        except ValidationError:
            # Do not reflect source text or raw validation inputs in error responses/logs.
            raise HTTPException(422, "Invalid retrieval contract") from None
        started = time.monotonic()
        try:
            result = await run_in_threadpool(app.state.retriever.search, payload)
        except BusyError:
            raise HTTPException(503, "Retrieval busy", headers={"Retry-After": "1"}) from None
        except Exception as error:  # noqa: BLE001 -- redact all provider/DB details at this HTTP boundary
            log.warning("retrieval_failed request_id=%s type=%s", payload.request_id, type(error).__name__)
            raise HTTPException(503, "Retrieval unavailable") from None
        log.info(
            "retrieval request_id=%s cache_hit=%s hits=%s elapsed_ms=%s",
            payload.request_id,
            result.cache_hit,
            len(result.hits),
            round((time.monotonic() - started) * 1000),
        )
        return result

    return app


app = create_app()
