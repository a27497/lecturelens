import asyncio
import hashlib
import hmac
import json
import logging
import os
import re
import time
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import StreamingResponse
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from .contracts import RetrieveRequest, RetrieveResponse, SyncRequest
from .embedding import LocalEmbedding
from .retrieval import DEFAULT_QUERY_CONCURRENCY, MAX_QUERY_CONCURRENCY, BusyError, IndexNotReady, Retriever
from .store import StaleSync, VectorStore

PATH = "/internal/v1/retrieve"
SYNC_PATH = "/internal/v1/evidence/sync"
EVENT_STREAM_PATH = "/internal/v1/study/events/stream"
# Public Run states after which the journal receives no further events for this Run.
STREAM_END = {"succeeded", "failed", "cancelled", "budget_exceeded", "awaiting_approval"}
EVENT_PAGE = 100  # StudyStore EVENTS page size
AUDIENCE = "lecturelens-retrieval-v1"
MAX_BODY_BYTES = 4 * 1024 * 1024
log = logging.getLogger(__name__)


def signature(secret: str, timestamp: str, body: bytes, path: str = PATH) -> str:
    message = f"{AUDIENCE}\nPOST\n{path}\n{timestamp}\n{hashlib.sha256(body).hexdigest()}"
    return hmac.new(secret.encode(), message.encode(), hashlib.sha256).hexdigest()


def bounded_setting(name, default, low, high):
    raw = os.environ.get(name, "").strip()
    try:
        value = int(raw) if raw else default
    except ValueError:
        raise RuntimeError(f"{name} must be an integer between {low} and {high}") from None
    if not low <= value <= high:
        raise RuntimeError(f"{name} must be an integer between {low} and {high}")
    return value


def flag(name):
    value = os.environ.get(name, "false").strip().lower()
    if value not in {"true", "false"}:
        raise RuntimeError(f"{name} must be true or false")
    return value == "true"


def sse(name, data, event_id=None):
    head = f"id: {event_id}\n" if event_id is not None else ""
    return f"{head}event: {name}\ndata: {json.dumps(data, ensure_ascii=False, default=str)}\n\n"


def create_app(
    retriever=None,
    secret=None,
    study_runtime=None,
    model_registry=None,
    *,
    event_stream=None,
    stream_seconds=25.0,
    stream_poll_seconds=0.25,
):
    @asynccontextmanager
    async def lifespan(app):
        key = secret if secret is not None else os.environ.get("AGENT_SERVICE_SECRET", "")
        if len(key.encode()) < 32:
            raise RuntimeError("AGENT_SERVICE_SECRET must contain at least 32 bytes")
        app.state.secret = key
        # Off by default: Java's SSE gateway keeps polling EVENTS until it adopts this route.
        app.state.event_stream = flag("AGENT_EVENT_STREAM_ENABLED") if event_stream is None else event_stream
        if retriever is None:
            concurrency = bounded_setting(
                "AGENT_RETRIEVAL_CONCURRENCY", DEFAULT_QUERY_CONCURRENCY, 1, MAX_QUERY_CONCURRENCY
            )
            store = VectorStore(os.environ["AGENT_DATABASE_URL"])
            store.initialize()
            embedder = LocalEmbedding(os.environ.get("AGENT_CACHE_DIR", ".cache"))
            app.state.retriever = Retriever(store, embedder, query_concurrency=concurrency)
        else:
            app.state.retriever = retriever
        app.state.study = study_runtime
        app.state.models = model_registry
        if study_runtime is not None or os.environ.get("STUDY_AGENT_ENABLED", "false").lower() == "true":
            from .study.authority import course_authority
            from .study.models import ModelRegistry, RegistryProvider
            from .study.provider import MockProvider
            from .study.runtime import DEFAULT_RUN_CONCURRENCY, MAX_RUN_CONCURRENCY, StudyRuntime
            from .study.store import StudyStore

            if app.state.study is None:
                mode = os.environ.get("AGENT_LLM_MODE", "real")
                if mode not in {"real", "mock"}:
                    raise RuntimeError("AGENT_LLM_MODE must be real or mock")
                seconds = int(os.environ.get("AGENT_RUN_DEADLINE_SECONDS", "90"))
                if not 30 <= seconds <= 300:
                    raise RuntimeError("AGENT_RUN_DEADLINE_SECONDS must be between 30 and 300")
                lanes = bounded_setting(
                    "AGENT_RUN_CONCURRENCY", DEFAULT_RUN_CONCURRENCY, 1, MAX_RUN_CONCURRENCY
                )
                app.state.models = ModelRegistry(os.environ["AGENT_DATABASE_URL"], key)
                await run_in_threadpool(app.state.models.initialize)
                app.state.study = StudyRuntime(
                    StudyStore(os.environ["AGENT_DATABASE_URL"], model_resolver=app.state.models.freeze),
                    course_authority(os.environ.get("AGENT_JAVA_BASE_URL", "http://127.0.0.1:8080"), key),
                    MockProvider() if mode == "mock" else RegistryProvider(app.state.models),
                    seconds=seconds,
                    concurrency=lanes,
                )
            await run_in_threadpool(app.state.study.initialize)
            app.state.study.start()
        try:
            yield
        finally:
            if app.state.study:
                await run_in_threadpool(app.state.study.close)

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

    async def authenticated_body(request: Request, study=False):
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
        if study:
            from .study.authority import signature as study_signature

            expected = study_signature(app.state.secret, timestamp, bytes(body), request.url.path)
        else:
            expected = signature(app.state.secret, timestamp, bytes(body), request.url.path)
        supplied = request.headers.get("X-LectureLens-Signature", "")
        if not re.fullmatch(r"[0-9a-f]{64}", supplied) or not hmac.compare_digest(expected, supplied):
            raise HTTPException(401, "Invalid execution context")
        return bytes(body)

    @app.post(PATH, response_model=RetrieveResponse)
    async def retrieve(request: Request):
        body = await authenticated_body(request)
        try:
            payload = RetrieveRequest.model_validate_json(body)
        except ValidationError:
            # Do not reflect source text or raw validation inputs in error responses/logs.
            raise HTTPException(422, "Invalid retrieval contract") from None
        started = time.monotonic()
        try:
            result = await run_in_threadpool(app.state.retriever.search, payload)
        except IndexNotReady:
            raise HTTPException(409, "Evidence index not ready", headers={"Retry-After": "3"}) from None
        except BusyError:
            raise HTTPException(503, "Retrieval busy", headers={"Retry-After": "1"}) from None
        except StaleSync:
            # The same course was republished or deleted between snapshot lookup and scoring.
            raise HTTPException(409, "Evidence index changed", headers={"Retry-After": "1"}) from None
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

    @app.post(SYNC_PATH)
    async def sync(request: Request):
        body = await authenticated_body(request)
        try:
            payload = SyncRequest.model_validate_json(body)
        except ValidationError:
            raise HTTPException(422, "Invalid sync contract") from None
        try:
            return await run_in_threadpool(app.state.retriever.sync, payload)
        except StaleSync:
            raise HTTPException(409, "Obsolete sync") from None
        except BusyError:
            raise HTTPException(503, "Indexing busy", headers={"Retry-After": "1"}) from None
        except Exception as error:  # noqa: BLE001 -- redact provider/DB/source details
            log.warning("sync_failed request_id=%s type=%s", payload.request_id, type(error).__name__)
            raise HTTPException(503, "Evidence sync unavailable") from None

    @app.post("/internal/v1/study/command")
    async def study_command(request: Request):
        from .study.contracts import StudyCommand
        from .study.store import StudyError

        body = await authenticated_body(request, study=True)
        if app.state.study is None:
            raise HTTPException(503, "Study Agent disabled")
        try:
            command = StudyCommand.model_validate_json(body)
        except ValidationError:
            raise HTTPException(422, "Invalid study contract") from None
        try:
            await run_in_threadpool(app.state.study.authority.read, command.model_dump())
            result = await run_in_threadpool(
                app.state.study.store.command, command, app.state.study.provider.mode
            )
            return {
                "owner_id": command.owner_id,
                "course_id": command.course_id,
                "revision": command.revision,
                **result,
            }
        except StudyError as error:
            raise HTTPException(error.status, error.code) from None
        except Exception as error:  # noqa: BLE001 -- no provider/DB details cross this boundary
            log.warning("study_command_failed type=%s", type(error).__name__)
            raise HTTPException(503, "Study Agent unavailable") from None

    @app.post(EVENT_STREAM_PATH)
    async def study_event_stream(request: Request):
        """Server-sent public Run events from the durable journal (optional, default off).

        The payloads are exactly the EVENTS projection: private trace detail, evidence text,
        unvalidated model output and quiz answers never enter it. Course authority is checked
        before the first byte and again before every later read.
        """
        from .study.contracts import StudyCommand
        from .study.store import StudyError

        body = await authenticated_body(request, study=True)
        if not app.state.event_stream:
            raise HTTPException(404, "STUDY_EVENT_STREAM_DISABLED")
        if app.state.study is None:
            raise HTTPException(503, "Study Agent disabled")
        try:
            command = StudyCommand.model_validate_json(body)
        except ValidationError:
            raise HTTPException(422, "Invalid study contract") from None
        if command.operation != "EVENTS" or not command.session_id or not command.run_id:
            raise HTTPException(422, "Invalid study contract")
        study = app.state.study

        def events(after):
            study.authority.read(command.model_dump())
            return study.store.command(command.model_copy(update={"after": after}), study.provider.mode)

        try:
            first = await run_in_threadpool(events, command.after)
        except StudyError as error:
            raise HTTPException(error.status, error.code) from None
        except Exception as error:  # noqa: BLE001 -- no provider/DB details cross this boundary
            log.warning("study_stream_failed type=%s", type(error).__name__)
            raise HTTPException(503, "Study Agent unavailable") from None

        async def stream():
            cursor, batch = command.after, first
            deadline = time.monotonic() + stream_seconds
            while True:
                for event in batch["events"]:
                    cursor = event["sequence"]
                    yield sse(event["event_type"], event, cursor)
                # EVENTS pages at most EVENT_PAGE rows; a full page may hide later events.
                drained = len(batch["events"]) < EVENT_PAGE
                if batch["status"] in STREAM_END and drained:
                    yield sse("stream_end", {"status": batch["status"], "cursor": cursor})
                    return
                if time.monotonic() >= deadline or await request.is_disconnected():
                    # The client resumes from `cursor`; nothing is lost on reconnect.
                    yield sse("stream_pause", {"status": batch["status"], "cursor": cursor})
                    return
                if drained:
                    yield ": heartbeat\n\n"
                    await asyncio.sleep(stream_poll_seconds)
                try:
                    batch = await run_in_threadpool(events, cursor)
                except StudyError as error:
                    yield sse("stream_error", {"code": error.code, "cursor": cursor})
                    return
                except Exception as error:  # noqa: BLE001 -- no provider/DB details cross this boundary
                    log.warning("study_stream_failed type=%s", type(error).__name__)
                    yield sse("stream_error", {"code": "STUDY_UNAVAILABLE", "cursor": cursor})
                    return

        return StreamingResponse(
            stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"},
        )

    @app.post("/internal/v1/models/command")
    async def model_command(request: Request):
        from .study.models import ModelCommand
        from .study.store import StudyError

        body = await authenticated_body(request, study=True)
        if app.state.models is None:
            raise HTTPException(503, "MODEL_MANAGEMENT_DISABLED")
        if len(body) > 65536:
            raise HTTPException(413, "MODEL_REQUEST_LIMIT")
        try:
            command = ModelCommand.model_validate_json(body)
        except ValidationError:
            raise HTTPException(422, "MODEL_CONFIGURATION_INVALID") from None
        try:
            result = await run_in_threadpool(app.state.models.command, command)
            return {"owner_id": command.owner_id, **result}
        except StudyError as error:
            raise HTTPException(error.status, error.code) from None
        except Exception as error:  # noqa: BLE001 -- credential-bearing payloads never enter logs/responses
            log.warning("model_management_failed type=%s", type(error).__name__)
            raise HTTPException(503, "MODEL_MANAGEMENT_UNAVAILABLE") from None

    return app


app = create_app()
