"""Bind new behavior to the unchanged first-real scope and all historical identities."""

# ruff: noqa: E402 -- local versioned eval imports require explicit paths

import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-python-contract-v1"))
import contract_check as parent
from lecturelens_real_eval.tutor.grounded_runtime import CONTEXT_VERSION as CONTEXT_VERSION
from public_dataset import digest, read

CANDIDATE = "p8-tutor-grounded-v11-development"
ENTRYPOINT = "lecturelens_real_eval.tutor.grounded_runtime:GroundedTutorRuntime"
PARENT_SHA = "8f430ba637bb13dfd415bf29d4785e116d44141d7d3c49946ede77cee45079cf"
SCOPE_SHA = "27c3361d841412f950b9aac5ab08a0d14e40b4fb0bc60801be0c9d181e5180d7"
FILES = {
    "agent-service/src/lecturelens_real_eval/tutor/grounded_runtime.py",
    "agent-service/src/lecturelens_real_eval/tutor/observed_channel.py",
    "eval/tutor-repair-v1/repair_check.py",
    "eval/tutor-repair-v1/repair_run.py",
    "eval/tutor-repair-v1/test_repair.py",
    "eval/tutor-repair-v1/offline_audit.py",
    "eval/tutor-pilot-v1/adapter-lock.json",
}


def verify_candidate():
    if parent.verify_candidate() != PARENT_SHA:
        raise ValueError("REPAIR_PARENT_CHANGED")
    # The new adapter is derived from the frozen pilot, whose transport/budget bounds remain pinned.
    lock = read(ROOT / "eval/tutor-pilot-v1/adapter-lock.json")
    for name, sha in lock["files"].items():
        if digest(ROOT / "eval/tutor-pilot-v1" / name) != sha:
            raise ValueError("REPAIR_PARENT_ADAPTER_CHANGED")
    value = read(HERE / "candidate.json")
    if (
        value["candidate"] != CANDIDATE
        or value["runtime_entrypoint"] != ENTRYPOINT
        or value["parent_manifest_sha256"] != PARENT_SHA
        or set(value["files"]) != FILES
    ):
        raise ValueError("REPAIR_IDENTITY_INVALID")
    if any(digest(ROOT / name) != sha for name, sha in value["files"].items()):
        raise ValueError("REPAIR_INPUT_CHANGED")
    return digest(HERE / "candidate.json")


def load_plan(path):
    identity = verify_candidate()
    if digest(path) != read(HERE / "scope-lock.json")["plan_sha256"]:
        raise ValueError("REPAIR_PLAN_CHANGED")
    value = read(path)
    original = ROOT / "eval/tutor-python-contract-v1/development-pilot-v1.json"
    if (
        digest(original) != SCOPE_SHA
        or value["original_plan_sha256"] != SCOPE_SHA
        or value["candidate_manifest_sha256"] != identity
        or value["execution_authorized"] is not False
    ):
        raise ValueError("REPAIR_SCOPE_OR_IDENTITY_CHANGED")
    plan, scripts, snapshot = parent.load_plan(original)
    if value["turn_keys"] != plan["turn_keys"] or value["sessions"] != plan["sessions"]:
        raise ValueError("REPAIR_SCOPE_CHANGED")
    return {**plan, "candidate_manifest_sha256": identity}, scripts, snapshot


if __name__ == "__main__":
    plan, _, _ = load_plan(HERE / "retest-plan.json")
    print(
        json.dumps(
            dict(candidate=CANDIDATE, counts=plan["counts"], execution_authorized=False, real_calls="NOT_RUN")
        )
    )
