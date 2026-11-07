"""Fixed v12 rerun contract; reuse the frozen development-only source/identity fence."""

# ruff: noqa: E402 -- install the existing scope fence before evaluation imports

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-recovery-v1"))
import contract as candidate

bridge, data = candidate.bridge, candidate.data
CANDIDATE_SHA = "4540369887eb2d84f79ee5351a8e1c0c82af859be8ff8d364ce7faf262a3afb2"
PLAN_SHA = "6a684a138d9fe2a04ccbb51f9d3bdbab25b44b5465a21a0c1082bbbc33dad825"
FILES = {"rerun_contract.py", "rerun.py", "run-plan.json", "protocol.json", "test_run.py"}


def verify():
    if candidate.verify_candidate() != CANDIDATE_SHA:
        raise ValueError("RERUN_V12_IDENTITY_MISMATCH")
    if data.digest(HERE / "run-plan.json") != PLAN_SHA:
        raise ValueError("RERUN_PLAN_CHANGED")
    lock = data.read(HERE / "adapter-lock.json")
    if (
        lock["version"] != "tutor-v12-rerun-v1-adapter"
        or lock["candidate_manifest_sha256"] != CANDIDATE_SHA
        or lock["execution_authorized"] is not False
        or set(lock["files"]) != FILES
        or any(data.digest(HERE / name) != sha for name, sha in lock["files"].items())
    ):
        raise ValueError("RERUN_ADAPTER_CHANGED")
    plan = data.read(HERE / "run-plan.json")
    batch, scripts, snapshot = data.load()
    if plan["candidate_sha256"] != CANDIDATE_SHA or plan["candidate"] != candidate.CANDIDATE:
        raise ValueError("RERUN_PLAN_IDENTITY_MISMATCH")
    for name, sha in plan["original_inputs"].items():
        if data.digest(data.HERE / name) != sha:
            raise ValueError("RERUN_ORIGINAL_INPUT_CHANGED")
    ordered = [
        next(s for s in scripts if s["dialogue_id"] == spec["dialogue_id"])
        for ref in batch["parts"]
        for spec in data.read(data.HERE / ref["path"])["sessions"]
    ]
    expected = bridge.module.expected_rows(snapshot, ordered)
    if [r["turn_key"] for r in expected] != plan["turn_keys"] or len(expected) != 16:
        raise ValueError("RERUN_SCOPE_MISMATCH")
    return plan, ordered, snapshot, expected, data.read(HERE / "protocol.json")
