"""Dedicated E3 worker. The runner provisions the isolated database and receipt."""

import json
import os
from pathlib import Path

from pydantic import ValidationError

from lecturelens_agent.study.authority import EvidenceAuthority

from .app import create_app as tutor_app
from .flash_app import FlashTutorRuntime
from .flash_phase import DATASET, PhaseFlashStore, PhaseReceipt
from .flash_provider import FlashProvider


def create_app():
    return experiment_app()


def experiment_app(*, offline_transport=None, api_key=None):
    mode = "offline-fake" if offline_transport is not None else "real"
    if (
        os.environ.get("TUTOR_FLASH_EXPERIMENT") != "phase1e3"
        or os.environ.get("AGENT_LLM_MODE") != "real"
        or os.environ.get("STUDY_AGENT_ENABLED", "").lower() != "false"
        or (mode == "real" and os.environ.get("LECTURELENS_E3_KEY_INJECTED") != "phase1e3")
    ):
        raise RuntimeError("TUTOR_E3_EXPERIMENT_DISABLED")
    try:
        with Path(os.environ["TUTOR_E3_RECEIPT_FILE"]).open("rb") as stream:
            data = stream.read(1024 * 1024 + 1)
        if len(data) > 1024 * 1024:
            raise RuntimeError("TUTOR_E3_RECEIPT_REQUIRED")
        receipt = PhaseReceipt.model_validate_json(data)
    except (KeyError, OSError, ValidationError):
        raise RuntimeError("TUTOR_E3_RECEIPT_REQUIRED") from None
    if receipt.grant.mode != mode or receipt.commit_sha != os.environ.get("TUTOR_E3_COMMIT_SHA"):
        raise RuntimeError("TUTOR_E3_RECEIPT_IDENTITY_MISMATCH")
    anchor_path = None
    if mode == "real":
        try:
            anchor_path = Path(os.environ["TUTOR_E3_ANCHOR_FILE"])
            anchor = json.loads(anchor_path.read_bytes())
        except (KeyError, OSError, ValueError):
            raise RuntimeError("TUTOR_E3_LIVE_ANCHOR_REQUIRED") from None
        if (
            not isinstance(anchor, dict)
            or anchor.get("phase_id") != receipt.phase_id
            or anchor.get("dataset_sha256") != DATASET
            or (receipt.kind == "initial" and anchor.get("commit_sha") != receipt.commit_sha)
        ):
            raise RuntimeError("TUTOR_E3_LIVE_ANCHOR_MISMATCH")
    store = PhaseFlashStore(os.environ["AGENT_DATABASE_URL"], receipt, live_anchor=anchor_path)
    secret = os.environ.get("AGENT_SERVICE_SECRET", "")
    if len(secret.encode()) < 32:
        raise RuntimeError("AGENT_SERVICE_SECRET must contain at least 32 bytes")
    provider = FlashProvider(
        os.environ.get("TUTOR_FLASH_API_KEY", "") if api_key is None else api_key,
        transport=offline_transport,
        observer=store.observe,
        text_reply=receipt.kind == "retest",
    )
    authority = EvidenceAuthority(os.environ["AGENT_JAVA_BASE_URL"], secret)
    return tutor_app(tutor=FlashTutorRuntime(store, authority, provider), secret=secret)
