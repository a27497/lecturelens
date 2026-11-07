"""Frozen preflight repair overlay; execute the unchanged corrected-reference v13 entry."""

import hashlib
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
sys.path.insert(1, str(ROOT / "eval/tutor-v13-grounding-v2"))
import trial_run_v2 as base  # noqa: E402 -- retain the immutable source/identity fence

parser = base.parser
contract = base.contract
bridge = base.bridge


def verify_fix():
    lock = json.loads((HERE / "fix-lock.json").read_text())
    if set(lock["files"]) != {"entry.py", "test_preflight.py"} or any(
        hashlib.sha256((HERE / p).read_bytes()).hexdigest() != h for p, h in lock["files"].items()
    ):
        raise ValueError("V13_PREFLIGHT_FIX_CHANGED")
    if (
        contract.digest(contract.HERE / "freeze-lock.json") != lock["base_freeze_sha256"]
        or contract.verify_candidate() != lock["candidate_sha256"]
    ):
        raise ValueError("V13_PREFLIGHT_FIX_BASE_CHANGED")
    return hashlib.sha256((HERE / "fix-lock.json").read_bytes()).hexdigest()


def preflight(args):
    verify_fix()
    return base.preflight(args)


def run(args, *, dsn=None, transport=None):
    preflight(args)
    return base.run(args, dsn=dsn, transport=transport)


if __name__ == "__main__":
    try:
        result = run(parser().parse_args())
        print(json.dumps(result))
        raise SystemExit(1 if result.get("mechanics_status") == "INCOMPLETE" else 0)
    except Exception:  # noqa: BLE001 -- fixed safe error only
        print(json.dumps({"error": "V13_PREFLIGHT_FIX_REJECTED"}))
        raise SystemExit(2) from None
