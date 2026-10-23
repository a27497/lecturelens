#!/usr/bin/env python3
"""Describe the frozen offline expense experiment; no live/serve command exists."""

import argparse
import json

from lecturelens_agent.study.acceptance_cost import (
    FROZEN_AGENT,
    INPUT_TOKEN_CEILING,
    MAX_BODY,
    MODEL,
    verify_frozen_agent,
)


def plan():
    return {
        "agent_candidate": FROZEN_AGENT,
        "mode": "fake_only",
        "required_models": {"decision": MODEL, "review": MODEL},
        "max_output_tokens": {
            "decision": 900,
            "practice_review": 1200,
            "feedback": 900,
        },
        "max_wire_bytes": MAX_BODY,
        "charged_input_token_ceiling_per_request": INPUT_TOKEN_CEILING,
        "max_calls": 12,
        "max_calls_per_run": 6,
        "budget_micro_cny": 20_000_000,
        "money_limit_implies_max_admitted_calls": 9,
        "refund_policy": "never",
        "unknown_outcome_policy": "stop_without_resending",
        "account_spending_limit": "not_verified_or_configured",
        "provider_billed_micro_cny": None,
        "provider_requests": 0,
        "live_authorization": False,
        "verified_frozen_modules": verify_frozen_agent(),
        "pricing_scope": "historical conservative simulation assumptions, not supplier billing certification",
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["plan"])
    parser.parse_args()
    print(json.dumps(plan(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
