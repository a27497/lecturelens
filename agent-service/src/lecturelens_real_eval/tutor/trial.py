"""Operator-authorized Light Tutor trial for one normal user's current course."""

import os
import stat
from pathlib import Path
from typing import Annotated, Literal

from pydantic import Field, model_validator

from lecturelens_agent.study.contracts import StudyScope
from lecturelens_agent.study.store import StudyError

from .flash_app import FlashTutorRuntime
from .flash_ledger import FlashAuthorization, FlashLedgerStore
from .flash_phase import mark_dispatch, verify_dispatch_markers
from .flash_provider import TEXT_SYSTEM, FlashProvider, digest


class TrialAuthorization(FlashAuthorization):
    version: Literal["lecturelens-light-tutor-trial-v1"]
    request_limit: Annotated[int, Field(ge=1, le=3)]
    budget_nano_usd: Annotated[int, Field(ge=1, le=1_000_000_000)]
    scope: StudyScope

    @model_validator(mode="after")
    def bound_scope(self):
        # Reuse the existing ledger's corpus binding for this single course revision.
        if self.dataset_sha256 != digest(self.scope.model_dump_json().encode()):
            raise ValueError("Invalid Tutor trial scope digest")
        return self


class TrialStore(FlashLedgerStore):
    def __init__(self, dsn, grant, dispatch_dir):
        super().__init__(dsn, grant, experiment="user-trial:" + grant.grant_id)
        self.dispatch_dir = dispatch_dir

    def initialize(self):
        with self.connect() as conn:
            if conn.execute(
                """SELECT EXISTS (SELECT 1 FROM pg_namespace WHERE nspname IN
                    ('tutor_e3','tutor_e3_initial','tutor_e3_retest')) AS historical"""
            ).fetchone()["historical"]:
                raise StudyError("TUTOR_TRIAL_REQUIRES_ISOLATED_DATABASE", 403)
        super().initialize()

    def authorize_command(self, command):
        if not self.in_scope(command.model_dump()):
            raise StudyError("TUTOR_FLASH_SCOPE_DENIED", 404)

    def in_scope(self, row):
        return all(row[key] == value for key, value in self.grant.scope.model_dump().items())

    def reserve(self, conn, session, turn, state, request_sha256):
        if not self.in_scope(session):
            raise StudyError("TUTOR_FLASH_SCOPE_DENIED", 404)
        self.lock_trial(conn)
        calls = conn.execute(
            "SELECT slot, request_sha256, 'trial' AS run_kind FROM tutor_flash_call"
        ).fetchall()
        verify_dispatch_markers(self.dispatch_dir, calls)
        self.reserve_slot(conn, turn, state, request_sha256)

    def observe_dispatch(self, request, response=None, status=None, complete=False):
        if response is not None:
            return
        request_hash = digest(request)
        with self.connect() as conn:
            self.lock_trial(conn)
            rows = conn.execute(
                """SELECT slot FROM tutor_flash_call
                   WHERE request_sha256=%s AND charged_nano_usd IS NULL AND observed_at IS NULL""",
                (request_hash,),
            ).fetchall()
            if len(rows) != 1:
                raise StudyError("TUTOR_FLASH_WIRE_JOURNAL_MISMATCH")
            mark_dispatch(self.dispatch_dir, "trial", rows[0]["slot"], request_hash)


class TrialTutorRuntime(FlashTutorRuntime):
    def command(self, command):
        mode = "mock-http" if self.provider.offline else "deepseek-flash"
        return super().command(command) | {"provider_mode": mode}

    def prepare(self, session, turn, history):
        state = super().prepare(session, turn, history)
        state["messages"][0]["content"] = TEXT_SYSTEM
        return state

    def audit_completion(self, state, result):
        # Private to the Tutor checkpoint and subject to the same course deletion purge.
        state["provider_content"] = result.raw_content


def create_trial(dsn, authority, *, transport=None):
    try:
        path = Path(os.environ["TUTOR_TRIAL_RECEIPT_FILE"])
        parent = path.parent.stat()
        if not path.is_absolute() or parent.st_uid != os.geteuid() or parent.st_mode & 0o077:
            raise ValueError
        flags = os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK
        with os.fdopen(os.open(path, flags), "rb") as stream:
            info = os.fstat(stream.fileno())
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid != os.geteuid()
                or info.st_mode & 0o077
                or not 0 < info.st_size <= 8192
            ):
                raise ValueError
            raw = stream.read(8193)
        if len(raw) > 8192:
            raise ValueError
        grant = TrialAuthorization.model_validate_json(raw)
    except (KeyError, OSError, ValueError):
        raise RuntimeError("TUTOR_TRIAL_RECEIPT_REQUIRED") from None
    if grant.mode != ("offline-fake" if transport is not None else "real"):
        raise RuntimeError("TUTOR_FLASH_GRANT_MODE_MISMATCH")
    store = TrialStore(dsn, grant, path.parent / f"{grant.grant_id}.dispatch")
    provider = FlashProvider(
        "synthetic-tutor-trial-fixture"
        if transport is not None
        else os.environ.get("TUTOR_FLASH_API_KEY", ""),
        transport=transport,
        observer=store.observe_dispatch,
        text_reply=True,
    )
    return TrialTutorRuntime(store, authority, provider)
