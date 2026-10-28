"""Local smoke ASGI factory; never installed in the product package.

An armed mock decision writes ``entered`` and waits up to 10 seconds for
``release`` (polling every 50ms). Timeout resumes the ordinary mock decision.
"""

import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

HOLD_SECONDS = 10.0
POLL_SECONDS = 0.05


def create_app(**kwargs):
    if os.environ.get("AGENT_LLM_MODE") != "mock":
        raise RuntimeError("TUTOR_MOCK_TEST_HOLD_REQUIRES_MOCK")

    from lecturelens_real_eval.tutor import runtime
    from lecturelens_real_eval.tutor.app import create_app as real_create_app

    hold_dir = os.environ.get("TUTOR_MOCK_TEST_HOLD_DIR")

    class HeldMockTutor(runtime.MockTutor):
        def decide(self, messages, schemas, timeout):
            if hold_dir:
                hold = Path(hold_dir)
                if (hold / "arm").is_file():
                    (hold / "entered").write_text(str(time.time_ns()) + "\n")
                    deadline = time.monotonic() + HOLD_SECONDS
                    while not (hold / "release").is_file():
                        remaining = deadline - time.monotonic()
                        if remaining <= 0:
                            break
                        time.sleep(min(POLL_SECONDS, remaining))
            return super().decide(messages, schemas, timeout)

    app = real_create_app(**kwargs)
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        # The real lifespan constructs and starts TutorRuntime. Patch its default
        # provider before entry so even its first worker decision is wrapped.
        # Scope the replacement to this local test app and restore on shutdown.
        if os.environ.get("AGENT_LLM_MODE") != "mock":
            raise RuntimeError("TUTOR_MOCK_TEST_HOLD_REQUIRES_MOCK")
        with patch.object(runtime, "MockTutor", HeldMockTutor):
            async with original(app):
                yield

    app.router.lifespan_context = lifespan
    return app
