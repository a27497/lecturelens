"""Default is frozen-input verification, never a provider request."""

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent-service/src"))

from lecturelens_real_eval.tutor.usable_smoke import (
    execute,
    verify_inputs,
)
from lecturelens_real_eval.tutor_channel import EvalError


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--mode", choices=["verify", "mock", "live"], default="verify")
    p.add_argument("--output", type=Path)
    p.add_argument("--authorization", type=Path)
    p.add_argument("--pricing", type=Path)
    p.add_argument(
        "--fault",
        choices=[
            "none",
            "format_once",
            "format_twice",
            "support_invalid",
            "fabricated_id",
            "model_mismatch",
            "unknown_usage",
            "malformed",
            "budget",
        ],
        default="none",
    )
    a = p.parse_args()
    try:
        if a.mode == "verify":
            result = verify_inputs()
        else:
            if a.output is None:
                p.error("--output required for execution")
            result = execute(
                a.output,
                live=a.mode == "live",
                authorization=a.authorization,
                pricing=a.pricing,
                fault=a.fault,
            )
        print(json.dumps(result, indent=2))
        return 0
    except EvalError as e:
        print(
            json.dumps(
                {"error": e.code, "real_requests_authorized_by_this_command": False}
            )
        )
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
