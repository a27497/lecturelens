"""Explicit v19 factory; importing it does not register or change any default."""

import os
from contextlib import asynccontextmanager

from .app import create_app as legacy_app
from .app import require_mock
from .complete_authority import CompleteEvidenceAuthority
from .selection_runtime import SelectedStore, SelectedTutorRuntime
from .store import TutorStore


def create_app(*, tutor=None, **kwargs):
    class Deferred:
        def initialize(self):
            require_mock(os.environ.get("AGENT_LLM_MODE", "real"))
            self.runtime = SelectedTutorRuntime(
                TutorStore(os.environ["TUTOR_V19_DATABASE_URL"]),
                CompleteEvidenceAuthority(
                    os.environ.get("AGENT_JAVA_BASE_URL", "http://127.0.0.1:8080"), app.state.secret
                ),
            )
            self.runtime.initialize()

        def __getattr__(self, name):
            return getattr(self.runtime, name)

    app = legacy_app(tutor=tutor if tutor is not None else Deferred(), **kwargs)
    original = app.router.lifespan_context

    @asynccontextmanager
    async def lifespan(app):
        if tutor is None:
            require_mock(os.environ.get("AGENT_LLM_MODE", "real"))
            SelectedStore(os.environ["TUTOR_V19_DATABASE_URL"]).check_admission()
        async with original(app):
            yield

    app.router.lifespan_context = lifespan
    return app
