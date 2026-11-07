"""Read-only v15 identity gate. No network, database or live dispatch mode."""

import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = ROOT / "eval/tutor-repair-phase-v1"


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def verify():
    manifest = json.loads((BASE / "candidate.json").read_text())
    if (
        manifest["candidate"] != "p8-tutor-bounded-v15-development"
        or manifest["default_registration"] is not False
    ):
        raise ValueError("TUTOR_PHASE_IDENTITY_INVALID")
    if digest(ROOT / "eval/tutor-v14-offline-v1/candidate.json") != manifest["parent_manifest_sha256"]:
        raise ValueError("TUTOR_PHASE_PARENT_CHANGED")
    for path, expected in manifest["files"].items():
        if digest(ROOT / path) != expected:
            raise ValueError("TUTOR_PHASE_SOURCE_CHANGED")
    return digest(BASE / "candidate.json")


if __name__ == "__main__":
    print(json.dumps({"candidate_sha256": verify(), "mode": "VERIFY_ONLY_NO_DISPATCH", "real_calls": 0}))
