"""Verify a distinct development identity and a development-only scope; never send."""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-public-v1"))
from public_bridge import verify_tooling  # noqa: E402
from public_dataset import VERSION, digest, object_hash, read, select  # noqa: E402

CANDIDATE = "p8-tutor-python-notation-v10-development-r2"
ENTRYPOINT = "lecturelens_real_eval.tutor.python_runtime:PythonTutorRuntime"
PARENT_SHA = "370d61d64abf1921927ae7e5ba6e5cc6c1e887aeaa9f4ef792aef723e1117426"
EXTRA_FILES = {
    "agent-service/src/lecturelens_real_eval/tutor/python_runtime.py",
    "agent-service/tests/test_tutor_python_contract.py",
    "agent-service/tests/fixtures/tutor_python_contract.json",
    "eval/tutor-python-contract-v1/contract_check.py",
    "eval/tutor-python-contract-v1/README.md",
    "eval/tutor-public-v1/dataset-lock.json",
    "eval/tutor-public-v1/public_bridge.py",
    "eval/tutor-public-v1/public_dataset.py",
    "eval/tutor-scale/candidate.json",
    "eval/tutor-scale-v2/candidate.json",
}


def verify_candidate():
    verify_tooling()  # Historical P8/P10 and synthetic v1/v2 identities still validate unchanged.
    parent = ROOT / "eval/p8-tutor/frozen.json"
    if digest(parent) != PARENT_SHA:
        raise ValueError("PYTHON_CONTRACT_PARENT_CHANGED")
    manifest = read(HERE / "candidate.json")
    if (
        manifest["candidate"] != CANDIDATE
        or manifest["runtime_entrypoint"] != ENTRYPOINT
        or manifest["parent_manifest_sha256"] != PARENT_SHA
        or set(manifest["files"]) != set(read(parent)["files"]) | EXTRA_FILES
    ):
        raise ValueError("PYTHON_CONTRACT_IDENTITY_INVALID")
    for name, expected in manifest["files"].items():
        if digest(ROOT / name) != expected:
            raise ValueError("PYTHON_CONTRACT_INPUT_CHANGED")
    return digest(HERE / "candidate.json")


def validate_plan(plan, snapshot, scripts, identity):
    by_id = {d["dialogue_id"]: d for d in scripts}
    if (
        plan["dataset_version"] != VERSION
        or plan["dataset_lock_sha256"] != digest(ROOT / "eval/tutor-public-v1/dataset-lock.json")
        or plan["candidate_manifest_sha256"] != identity
        or plan["execution_authorized"] is not False
    ):
        raise ValueError("PYTHON_PILOT_VERSION_OR_AUTHORIZATION_INVALID")
    chosen, seen = [], set()
    for item in plan["sessions"]:
        did = item["dialogue_id"]
        if did in seen or did not in by_id:
            raise ValueError("PYTHON_PILOT_NOT_UNIQUE_DEVELOPMENT_SESSIONS")
        seen.add(did)
        d = by_id[did]
        if (
            item["course_id"] != d["course_id"]
            or item["split"] != "development"
            or snapshot["lectures"][d["lecture_id"]]["split"] != "development"
            or item["turns"] != len(d["turns"])
            or item["turns_sha256"] != object_hash(d["turns"])
        ):
            raise ValueError("PYTHON_PILOT_SESSION_CHANGED_OR_TRUNCATED")
        chosen.append(d)
    expected_keys = [f"{d['dialogue_id']}:{n}" for d in chosen for n in range(1, len(d["turns"]) + 1)]
    if (
        len(chosen) != 2
        or len({d["course_id"] for d in chosen}) != 2
        or sum(len(d["turns"]) for d in chosen) != 8
        or plan["counts"] != {"courses": 2, "sessions": 2, "turns": 8}
        or plan["turn_keys"] != expected_keys
    ):
        raise ValueError("PYTHON_PILOT_SCOPE_INVALID")
    return chosen


def load_plan(path):
    identity = verify_candidate()
    lock = read(HERE / "scope-lock.json")
    if lock["candidate_sha256"] != identity or digest(path) != lock["plan_sha256"]:
        raise ValueError("PYTHON_PILOT_MANIFEST_HASH_MISMATCH")
    snapshot, development = select("development")
    plan = read(path)
    chosen = validate_plan(plan, snapshot, development, identity)
    courses = {d["lecture_id"] for d in chosen}
    return (
        plan,
        chosen,
        {**snapshot, "lectures": {k: v for k, v in snapshot["lectures"].items() if k in courses}},
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plan", required=True)
    args = parser.parse_args()
    plan, scripts, snapshot = load_plan(args.plan)
    print(
        json.dumps(
            dict(
                candidate=CANDIDATE,
                candidate_sha256=verify_candidate(),
                counts=plan["counts"],
                sessions=[d["dialogue_id"] for d in scripts],
                course_ids=list(snapshot["lectures"]),
                execution_authorized=False,
                real_quality_status="NOT_RUN",
                real_cost_status="NOT_RUN",
            )
        )
    )
