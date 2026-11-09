"""Dedicated, disabled-by-default E3 entry point. Trusted local operator only."""

import os
from datetime import datetime, timezone
from pathlib import Path

from pydantic import ValidationError

from lecturelens_agent.study.authority import EvidenceAuthority
from lecturelens_agent.study.store import StudyError

from .app import create_app as tutor_app
from .flash_ledger import FlashStore, Grant
from .flash_provider import OUTPUT_TOKENS, FlashProvider, digest, payload
from .light import LightTutorRuntime


class FlashTutorRuntime(LightTutorRuntime):
    output_reserve = OUTPUT_TOKENS

    def __init__(self, store, authority, provider):
        if not isinstance(provider, FlashProvider) or provider.offline != (
            store.grant.mode == "offline-fake"
        ):
            raise TypeError("TUTOR_FLASH_PROVIDER_REQUIRED")
        super().__init__(store, authority, provider)

    def command(self, command):
        self.store.authorize_command(command)
        return super().command(command)

    def loop(self, turn_id):
        try:
            super().loop(turn_id)
        except StudyError:
            raise
        except Exception:  # noqa: BLE001 -- no provider or infrastructure details leave the journal
            raise StudyError("TUTOR_FLASH_EXECUTION_FAILURE") from None

    def reserve_generation(self, conn, session, turn, state):
        body = payload(state["messages"])
        # Runtime context bound and supplier billing bound are independent.
        state["reservation"] = max(state["reservation"], len(body) + OUTPUT_TOKENS)
        super().reserve_generation(conn, session, turn, state)
        self.store.reserve(conn, session, turn, state, digest(body))

    def generate(self, turn, state, timeout):
        body = payload(state["messages"])
        remaining_grant = (self.store.grant.expires_at - datetime.now(timezone.utc)).total_seconds()
        if remaining_grant <= 0:
            raise StudyError("TUTOR_FLASH_GRANT_EXPIRED")
        result = self.provider.complete(body, min(timeout, remaining_grant))
        # Billing can settle even when a cancelled turn can no longer publish.
        error = self.store.settle(turn["turn_id"], digest(body), result)
        if error:
            return {"flash_error": error, "usage": result.usage or {}, "raw_content": result.raw_content}
        return {**result.reply, "usage": result.usage}

    def publish(self, turn_id, state):
        if error := state["response"].get("flash_error"):
            raise StudyError(error)
        super().publish(turn_id, state)

    def publication_committed(self, conn, turn_id):
        self.store.published(conn, turn_id)


def create_app():
    return experiment_app()


def experiment_app(*, offline_transport=None):
    if (
        os.environ.get("TUTOR_FLASH_EXPERIMENT") != "enabled"
        or os.environ.get("AGENT_LLM_MODE") != "real"
        or os.environ.get("STUDY_AGENT_ENABLED", "false").lower() == "true"
    ):
        raise RuntimeError("TUTOR_FLASH_EXPERIMENT_DISABLED")
    # The receipt is installed by a trusted operator, never accepted from the gateway.
    try:
        with Path(os.environ["TUTOR_FLASH_GRANT_FILE"]).open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise RuntimeError("TUTOR_FLASH_GRANT_REQUIRED")
        grant = Grant.model_validate_json(data)
    except (KeyError, OSError, ValidationError):
        raise RuntimeError("TUTOR_FLASH_GRANT_REQUIRED") from None
    if grant.mode != ("offline-fake" if offline_transport is not None else "real"):
        raise RuntimeError("TUTOR_FLASH_GRANT_MODE_MISMATCH")
    if offline_transport is None:
        raise RuntimeError("TUTOR_FLASH_E3_FACTORY_REQUIRED")
    secret = os.environ.get("AGENT_SERVICE_SECRET", "")
    if len(secret.encode()) < 32:
        raise RuntimeError("AGENT_SERVICE_SECRET must contain at least 32 bytes")
    store = FlashStore(os.environ["AGENT_DATABASE_URL"], grant)
    authority = EvidenceAuthority(os.environ["AGENT_JAVA_BASE_URL"], secret)
    # Dedicated injection only. The ordinary Study and provider variables are unused.
    provider = FlashProvider(os.environ.get("TUTOR_FLASH_API_KEY", ""), transport=offline_transport)
    return tutor_app(tutor=FlashTutorRuntime(store, authority, provider), secret=secret)
