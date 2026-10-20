#!/usr/bin/env python3
"""Inspect a no-cost plan, or explicitly start the isolated acceptance proxy.

Neither command creates Runs. Live serving requires a separately authorized,
immutable policy and a credential read from an already-open private descriptor.
"""

import argparse
import json
import os
import secrets
import signal
import threading
from pathlib import Path

from lecturelens_agent.study.acceptance_cost import (
    FROZEN_AGENT,
    INPUT_TOKEN_CEILING,
    MAX_BODY,
    MODEL,
    PRICE_SOURCE,
    UPSTREAM,
    CostDenied,
    CostLedger,
    CostPolicy,
    routes,
    verify_frozen_agent,
)
from lecturelens_agent.study.acceptance_egress import (
    CostGateway,
    OfficialSender,
    serve_gateway,
)


def plan(route_file=None):
    frozen_modules = verify_frozen_agent()
    result = {
        "agent_candidate": FROZEN_AGENT,
        "upstream": UPSTREAM,
        "required_models": {"decision": MODEL, "review": MODEL},
        "thinking": "disabled",
        "max_output_tokens": {
            "decision": 900,
            "practice_review": 1200,
            "feedback": 900,
        },
        "max_wire_bytes": MAX_BODY,
        "charged_input_token_ceiling_per_request": INPUT_TOKEN_CEILING,
        "input_peak_cny_per_million": 2,
        "output_peak_cny_per_million": 8,
        "price_source": PRICE_SOURCE,
        "max_calls": 12,
        "max_calls_per_run": 6,
        "budget_micro_cny": 20_000_000,
        "max_900_token_request_micro_cny": 2_104_352,
        "max_1200_token_request_micro_cny": 2_106_752,
        "twelve_call_unchecked_upper_micro_cny": 25_266_624,
        "money_limit_implies_max_admitted_calls": 9,
        "refund_policy": "never",
        "unknown_outcome_policy": "stop_without_resending",
        "live_authorization": "not_given_by_this_plan",
        "account_spending_limit": "not_verified_or_configured",
        "provider_requests": 0,
        "verified_frozen_modules": frozen_modules,
    }
    if route_file:
        result["checked_routes"] = routes(json.loads(route_file.read_text()))
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    inspect = sub.add_parser("plan")
    inspect.add_argument("--routes", type=Path)
    serve = sub.add_parser("serve")
    serve.add_argument("--policy-file", type=Path, required=True)
    serve.add_argument("--credential-fd", type=int, required=True)
    serve.add_argument("--endpoint-file", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "plan":
        print(json.dumps(plan(args.routes), ensure_ascii=False, indent=2))
        return
    policy = CostPolicy(**json.loads(args.policy_file.read_text()))
    policy.validate()
    if policy.mode != "live" or not policy.authorization_id or args.credential_fd < 3:
        raise CostDenied("COST_LIVE_AUTHORIZATION_REQUIRED")
    # The gateway owns the only provider key. Do not use the production loader,
    # environment credential, /models probe or /user/balance discovery.
    ledger = CostLedger(os.environ["AGENT_ACCEPTANCE_DATABASE_URL"])
    ledger.install(policy)
    with os.fdopen(args.credential_fd, "r") as stream:
        credential = stream.read(8193).strip()
    if (
        not credential
        or len(credential) > 8192
        or any(ord(c) <= 32 for c in credential)
    ):
        raise CostDenied("COST_PRIVATE_CREDENTIAL_REQUIRED")
    sender = OfficialSender(ledger, credential)
    local_key = secrets.token_urlsafe(32)
    stop = threading.Event()
    prior = {
        sig: signal.signal(sig, lambda *_: stop.set())
        for sig in (signal.SIGINT, signal.SIGTERM)
    }
    try:
        with serve_gateway(CostGateway(ledger, sender), local_key) as url:
            # Never emit this independent local capability to stdout or Git.
            fd = os.open(
                args.endpoint_file, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
            )
            with os.fdopen(fd, "w") as output:
                json.dump({"proxy_url": url, "local_token": local_key}, output)
            print(
                json.dumps(
                    {"status": "LISTENING", "endpoint_file": str(args.endpoint_file)}
                ),
                flush=True,
            )
            stop.wait()
    finally:
        for sig, handler in prior.items():
            signal.signal(sig, handler)


if __name__ == "__main__":
    try:
        main()
    except Exception:  # noqa: BLE001 -- never print provider credentials, DB URLs or payloads
        raise SystemExit(
            "Acceptance egress refused; review the private policy and persistent ledger"
        ) from None
