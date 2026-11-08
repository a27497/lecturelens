"""Verify by default; explicit future handoff reuses the unchanged frozen CLI."""

import argparse
import json
import os
import subprocess
from pathlib import Path

from prepare import inspect

ROOT = Path(__file__).resolve().parents[2]


def preparation_head():
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("CLEAN_PREPARATION_CHECKOUT_REQUIRED")
    return (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    )


def handoff(root, output, authorization, pricing, *, execute=os.execv):
    # Membership does not read, validate or copy a credential value. The native
    # exec inherits the user's environment only after all nonsecret admission.
    if "AGENT_LLM_API_KEY" not in os.environ:
        raise ValueError("RUNTIME_KEY_NOT_INJECTED_NO_CLAIM_OR_RESERVATION")
    state = inspect(root)
    root, output = Path(root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / ".data") or output.exists():
        raise ValueError("FRESH_PRIVATE_EXECUTION_OUTPUT_REQUIRED")
    grant = json.loads(Path(authorization).read_bytes())
    if (
        grant.get("preparation_git_head") != preparation_head()
        or grant.get("execution_root") != str(root)
        or grant.get("supplier_cost_risk_accepted") is not True
        or not grant.get("independent_reviewer")
    ):
        raise ValueError("PREPARATION_PATH_COST_AND_REVIEW_APPROVAL_REQUIRED")
    from lecturelens_real_eval.tutor.selection_smoke import live_admission

    live_admission(state["frozen"], authorization, pricing)
    python = root / "agent-service/.venv/bin/python"
    argv = [
        str(python),
        str(root / "scripts/dev/run_tutor_smoke_v19.py"),
        "--mode",
        "live",
        "--output",
        str(output),
        "--authorization",
        str(Path(authorization).resolve()),
        "--pricing",
        str(Path(pricing).resolve()),
    ]
    execute(str(python), argv)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument("--mode", choices=["verify", "handoff-live"], default="verify")
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--pricing", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "verify":
            print(json.dumps(inspect(args.candidate_root), indent=2))
            return 0
        if not all([args.output, args.authorization, args.pricing]):
            raise ValueError("FUTURE_EXPLICIT_GRANT_PRICING_OUTPUT_REQUIRED")
        handoff(args.candidate_root, args.output, args.authorization, args.pricing)
    except ValueError as error:
        # Own ValueErrors have constant codes; malformed JSON uses a fixed code.
        code = (
            "INVALID_NONSECRET_RECEIPT"
            if isinstance(error, json.JSONDecodeError)
            else str(error)
        )
        print(json.dumps({"admission": "DENIED", "code": code, "real_requests": 0}))
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
