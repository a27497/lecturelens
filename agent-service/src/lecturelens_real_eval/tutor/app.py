"""Opt-in ASGI entry point; the original frozen app remains byte-identical."""

import os
import re
import time
from contextlib import asynccontextmanager

from fastapi import HTTPException, Request
from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool

from lecturelens_agent.app import create_app as base_app
from lecturelens_agent.study.authority import course_authority, signature
from lecturelens_agent.study.store import StudyError

from .contracts import Command
from .runtime import TutorRuntime
from .store import TutorStore

PATH = "/internal/v1/tutor/command"


def require_mock(mode):
    if mode != "mock":
        raise RuntimeError("TUTOR_MOCK_ONLY")


def create_app(*, tutor=None, **kwargs):
    app = base_app(**kwargs)
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        configured = tutor is None and os.environ.get("TUTOR_ENABLED", "false").lower() == "true"
        # Reject before the base lifespan can initialize or start any provider worker.
        if configured:
            require_mock(os.environ.get("AGENT_LLM_MODE", "real"))
        async with original(app):
            app.state.tutor = tutor
            if configured:
                # No real product adapter is installed; eval has its own guarded factory.
                app.state.tutor = TutorRuntime(
                    TutorStore(os.environ["AGENT_DATABASE_URL"]),
                    course_authority(
                        os.environ.get("AGENT_JAVA_BASE_URL", "http://127.0.0.1:8080"), app.state.secret
                    ),
                )
            if app.state.tutor:
                await run_in_threadpool(app.state.tutor.initialize)
                app.state.tutor.start()
            try:
                yield
            finally:
                if app.state.tutor:
                    await run_in_threadpool(app.state.tutor.close)

    app.router.lifespan_context = lifespan

    @app.post(PATH)
    async def command(request: Request):
        import hmac

        body = bytearray()
        async for part in request.stream():
            body.extend(part)
            if len(body) > 16384:
                raise HTTPException(413, "TUTOR_BODY_LIMIT")
        timestamp = request.headers.get("X-LectureLens-Timestamp", "")
        supplied = request.headers.get("X-LectureLens-Signature", "")
        try:
            valid = (
                abs(time.time() - int(timestamp)) <= 60
                and re.fullmatch(r"[0-9a-f]{64}", supplied) is not None
                and hmac.compare_digest(supplied, signature(app.state.secret, timestamp, bytes(body), PATH))
            )
        except ValueError:
            valid = False
        if not valid:
            raise HTTPException(401, "Invalid execution context")
        if app.state.tutor is None:
            raise HTTPException(503, "TUTOR_DISABLED")
        try:
            payload = Command.model_validate_json(body)
            result = await run_in_threadpool(app.state.tutor.command, payload)
            return {k: getattr(payload, k) for k in ("owner_id", "course_id", "revision")} | result
        except ValidationError:
            raise HTTPException(422, "TUTOR_CONTRACT_INVALID") from None
        except StudyError as error:
            raise HTTPException(error.status, error.code) from None
        except Exception:  # noqa: BLE001 -- no payload/provider/DB details escape
            raise HTTPException(503, "TUTOR_UNAVAILABLE") from None

    return app


app = create_app()
