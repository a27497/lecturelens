"""Default verify-only entry; explicit live mode still requires three valid receipts."""

import argparse
import json

from lecturelens_real_eval.tutor.verified_diagnostic import (
    execute,
    verify_inputs,
)
from lecturelens_real_eval.tutor_channel import EvalError


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--mode", choices=["verify", "mock", "live"], default="verify")
    parser.add_argument("--output")
    parser.add_argument("--authorization")
    parser.add_argument("--reference-review")
    parser.add_argument("--pricing")
    parser.add_argument(
        "--fault",
        choices=[
            "none",
            "malformed",
            "unknown_usage",
            "model_mismatch",
            "fabricated_id",
            "support_invalid",
            "budget",
        ],
        default="none",
    )
    args = parser.parse_args()
    state = verify_inputs()
    if args.mode == "verify":
        print(json.dumps({"mode": "VERIFY_ONLY_NO_DISPATCH", **state}))
        return
    if not args.output:
        raise EvalError("V16_FRESH_OUTPUT_REQUIRED")
    print(
        json.dumps(
            execute(
                args.output,
                live=args.mode == "live",
                authorization=args.authorization,
                reference_review=args.reference_review,
                pricing=args.pricing,
                fault=args.fault,
            )
        )
    )


if __name__ == "__main__":
    try:
        main()
    except EvalError as error:
        print(
            json.dumps(
                {
                    "status": "BLOCKED",
                    "code": error.code,
                    "real_calls": "UNKNOWN_UNLESS_ARTIFACTS_ESTABLISH_COUNT",
                }
            )
        )
        raise SystemExit(2) from None
