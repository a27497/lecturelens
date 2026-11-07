"""Explicit development identity; no paid entry or product-default registration."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-v13-grounding-v2"))
import v13_v2_contract as historical  # noqa: E402 -- preserve inherited source/data fence

CANDIDATE = "p8-tutor-draft-repair-v14-development"
ENTRYPOINT = "lecturelens_real_eval.tutor.draft_repair_runtime:DraftRepairTutorRuntime"
PARENT_SHA = "70b4f27471a61fb6db64e1a8318b2e4540b2d1428614f5e29f3a6166f4dd43a7"
FILES = {
    "agent-service/src/lecturelens_real_eval/tutor/draft_repair_runtime.py",
    "eval/tutor-v14-offline-v1/v14_contract.py",
}


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_candidate():
    historical.verify()
    manifest = json.loads((HERE / "candidate.json").read_text())
    if (
        historical.verify_candidate() != PARENT_SHA
        or manifest["candidate"] != CANDIDATE
        or manifest["runtime_entrypoint"] != ENTRYPOINT
        or manifest["parent_manifest_sha256"] != PARENT_SHA
        or manifest["default_registration"] is not False
        or set(manifest["files"]) != FILES
        or any(digest(ROOT / p) != h for p, h in manifest["files"].items())
    ):
        raise ValueError("V14_IDENTITY_CHANGED")
    return digest(HERE / "candidate.json")


def verify_offline():
    identity = verify_candidate()
    lock = json.loads((HERE / "offline-lock.json").read_text())
    files = FILES | {
        "eval/tutor-v14-offline-v1/candidate.json",
        "eval/tutor-v14-offline-v1/test_v14.py",
        "eval/tutor-v14-offline-v1/v14_audit.py",
    }
    if set(lock["files"]) != files or any(digest(ROOT / p) != h for p, h in lock["files"].items()):
        raise ValueError("V14_OFFLINE_CHECK_CHANGED")
    return identity
