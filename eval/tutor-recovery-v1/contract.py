"""Additive development identity. Parent manifests and sample assets stay frozen."""

# ruff: noqa: E402 -- development-only bridge must install its source fence first

import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path.insert(1, str(ROOT / "eval/tutor-fresh-dev-v1"))
import bridge
import data

CANDIDATE = "p8-tutor-repair-context-v12-development"
ENTRYPOINT = "lecturelens_real_eval.tutor.repair_context_runtime:RepairContextTutorRuntime"
PARENT = "b7fe50df1854703cc05d4ad039dad3245cc62adc5d68c3af7b394f2407f0ec58"
FILES = {
    "agent-service/src/lecturelens_real_eval/tutor/repair_context_runtime.py",
    "eval/tutor-recovery-v1/contract.py",
    "eval/tutor-recovery-v1/session_driver.py",
    "eval/tutor-recovery-v1/replay_support.py",
}


def verify_candidate():
    if bridge.verify_candidate() != PARENT:
        raise ValueError("RECOVERY_PARENT_CHANGED")
    data.load()
    manifest = json.loads((HERE / "candidate.json").read_text())
    if (
        manifest["candidate"] != CANDIDATE
        or manifest["runtime_entrypoint"] != ENTRYPOINT
        or manifest["parent_manifest_sha256"] != PARENT
        or set(manifest["files"]) != FILES
        or any(data.digest(ROOT / p) != h for p, h in manifest["files"].items())
    ):
        raise ValueError("RECOVERY_CANDIDATE_CHANGED")
    return hashlib.sha256((HERE / "candidate.json").read_bytes()).hexdigest()
