"""Additive v13 identity and new development-only input lock; no old asset edits."""

import hashlib
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-v12-rerun-v1"))
import rerun as parent  # noqa: E402 -- frozen parent installs the development-only source fence

CANDIDATE = "p8-tutor-claim-grounding-v13-development"
ENTRYPOINT = "lecturelens_real_eval.tutor.claim_grounding_runtime:ClaimGroundingTutorRuntime"
PARENT_SHA = "4540369887eb2d84f79ee5351a8e1c0c82af859be8ff8d364ce7faf262a3afb2"
bridge, data = parent.bridge, parent.data


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_candidate():
    parent.contract.verify()
    manifest = data.read(HERE / "candidate.json")
    files = {
        "agent-service/src/lecturelens_real_eval/tutor/claim_grounding_runtime.py",
        "eval/tutor-v13-grounding-v1/v13_contract.py",
    }
    if (
        manifest["candidate"] != CANDIDATE
        or manifest["runtime_entrypoint"] != ENTRYPOINT
        or manifest["parent_manifest_sha256"] != PARENT_SHA
        or set(manifest["files"]) != files
        or any(digest(ROOT / p) != h for p, h in manifest["files"].items())
    ):
        raise ValueError("V13_IDENTITY_CHANGED")
    return digest(HERE / "candidate.json")


def verify():
    identity = verify_candidate()
    lock = data.read(HERE / "freeze-lock.json")
    if any(digest(HERE / p) != h for p, h in lock["files"].items()):
        raise ValueError("V13_FROZEN_INPUT_CHANGED")
    plan = data.read(HERE / "run-plan.json")
    if plan["candidate"] != CANDIDATE or plan["candidate_sha256"] != identity:
        raise ValueError("V13_PLAN_IDENTITY_CHANGED")
    snapshot = data.read(HERE / "snapshot.json")
    scripts = data.read(HERE / "development.json")["dialogues"]
    if set(snapshot["lectures"]) != {"carpentries-python", "carpentries-spreadsheets"}:
        raise ValueError("V13_DEVELOPMENT_ONLY")
    for source in data.read(HERE / "sources.json")["sources"]:
        if source["split"] != "development":
            raise ValueError("V13_NO_HOLDOUT")
        for p, h in (("local_path", "sha256"), ("license_local_path", "license_sha256")):
            if digest(HERE / source[p]) != source[h]:
                raise ValueError("V13_SOURCE_CHANGED")
    expected = bridge.module.expected_rows(snapshot, scripts)
    if len(scripts) != 4 or len(expected) != 16 or [e["turn_key"] for e in expected] != plan["turn_keys"]:
        raise ValueError("V13_SCOPE_CHANGED")
    return plan, scripts, snapshot, expected, data.read(ROOT / "eval/tutor-v12-rerun-v1/protocol.json")
