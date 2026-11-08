"""Phase 1-B outer admission. No human reviewer or implicit billing-risk consent."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

import risk_once

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "eval/phase1a-tutor-readiness-20261108"))
from prepare import inspect  # noqa: E402

POLICY = Path(__file__).with_name("review-plan.json")


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load(path):
    try:
        return json.loads(Path(path).read_bytes())
    except (OSError, ValueError, TypeError):
        raise ValueError("NONSECRET_RECEIPT_MISSING_OR_INVALID") from None


def fresh(stamp, seconds):
    try:
        return (
            0
            <= (
                datetime.now(timezone.utc) - datetime.fromisoformat(stamp)
            ).total_seconds()
            <= seconds
        )
    except (TypeError, ValueError):
        return False


def review_plan(path):
    plan = load(path)
    expected = {
        "version": "PHASE1B_LAYERED_DEVELOPMENT_ONLY",
        "deterministic_checks": True,
        "ai_review": "EXTERNAL_AI_PACKET_NO_AUTOMATIC_PAID_REVIEW",
        "human_review": "HUMAN_NOT_RUN",
        "unresolved_blocks_quality_pass": True,
        "all_original_required_points": True,
        "same_implementation_session_cannot_cross_review": True,
        "automatic_expansion": False,
    }
    if plan != expected:
        raise ValueError("LAYERED_REVIEW_PLAN_REQUIRED")
    return digest(path)


def cost_assurance(receipt, grant):
    # An exact, recorded user authorization is a separate path from account
    # enforcement. Neither path treats a lone risk-acceptance boolean as consent.
    if not receipt:
        raise ValueError("SUPPLIER_HARD_CAP_UNVERIFIED_NO_EXCESS_RISK_AUTHORIZATION")
    data = load(receipt)
    if data.get("kind") == risk_once.KIND:
        if grant.get("cost_assurance_sha256") != digest(receipt):
            raise ValueError("FIXED_RUN_RISK_RECEIPT_HASH_MISMATCH")
        return risk_once.validate(data, grant, preparation_head())
    try:
        valid = (
            grant["cost_assurance_sha256"] == digest(receipt)
            and data["kind"] == "VERIFIED_SUPPLIER_ACCOUNT_HARD_CAP"
            and data["verified"] is True
            and data["run_id"] == grant["run_id"]
            and data["execution_root"] == grant["execution_root"]
            and data["model"] == "deepseek-flash"
            and data["currency"] == "USD"
            and type(data["maximum_additional_liability_nano_usd"]) is int
            and 0 < data["maximum_additional_liability_nano_usd"] <= 300000000
            and data["inflight_and_delayed_billing_covered"] is True
            and data["shared_account_activity_covered"] is True
            and data["automatic_topups_and_credit_disabled"] is True
            and data["verified_by"]
            and fresh(data["verified_utc"], 3600)
        )
        evidence = Path(receipt).parent / data["redacted_evidence_file"]
        valid = valid and evidence.resolve().is_relative_to(
            Path(receipt).parent.resolve()
        )
        valid = valid and data["redacted_evidence_sha256"] == digest(evidence)
        valid = valid and evidence.stat().st_size > 0
    except (KeyError, OSError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("SUPPLIER_HARD_CAP_RECEIPT_INVALID")
    return data


def preparation_head():
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise ValueError("CLEAN_PREPARATION_CHECKOUT_REQUIRED")
    return (
        subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT).decode().strip()
    )


def database_ready():
    import psycopg
    from lecturelens_real_eval.tutor.selection_smoke import TEST_DSN
    from lecturelens_real_eval.tutor_channel import isolated_dsn

    try:
        with psycopg.connect(isolated_dsn(TEST_DSN), connect_timeout=3) as conn:
            row = conn.execute("SELECT current_database(),current_user").fetchone()
            durable = conn.execute("SHOW fsync").fetchone()[0] == "on"
        if row != ("lecturelens_agent_acceptance", "tutor_scale") or not durable:
            raise ValueError()
    except Exception:  # noqa: BLE001 -- never expose connection details
        raise ValueError("ISOLATED_DURABLE_DATABASE_REQUIRED") from None


def preflight(root, plan=POLICY):
    state = inspect(root)
    review_plan(plan)
    consent = risk_once.status(root)
    return {
        "frozen": state["frozen"],
        "execution_head": state["execution_head"],
        "execution_root": str(Path(root).resolve()),
        "review_plan_sha256": digest(plan),
        "human_review": "HUMAN_NOT_RUN",
        "human_review_required_for_generation": False,
        "runtime_key_present": "AGENT_LLM_API_KEY" in os.environ,
        "credential_value_read": False,
        "supplier_hard_cap": "UNVERIFIED",
        "excess_supplier_risk_authorized": consent["risk_accepted_for_fixed_run_only"],
        "fixed_run_authorization": consent,
        "phase0_remote_ci": "PENDING",
        "execution": "BLOCKED",
        "quality": "NOT_RUN",
        "real_requests": 0,
        "blockers": [
            "FRESH_SINGLE_USE_RECEIPTS_REQUIRED",
        ]
        + ([] if consent["valid_now"] else ["FIXED_USER_AUTHORIZATION_EXPIRED"])
        + ([] if "AGENT_LLM_API_KEY" in os.environ else ["RUNTIME_KEY_NOT_INJECTED"]),
    }


def handoff(
    root, output, authorization, pricing, assurance, plan=POLICY, *, execute=os.execv
):
    state = inspect(root)
    plan_hash = review_plan(plan)
    grant = load(authorization)
    # Billing protection is deliberately evaluated before credentials, database,
    # one-use claim and native CLI execution. No blanket 'accepted=true' bypass.
    cost = cost_assurance(assurance, grant)
    if "AGENT_LLM_API_KEY" not in os.environ:
        raise ValueError("RUNTIME_KEY_NOT_INJECTED_NO_CLAIM_OR_RESERVATION")
    root, output = Path(root).resolve(), Path(output).resolve()
    if not output.is_relative_to(root / ".data") or output.exists():
        raise ValueError("FRESH_PRIVATE_EXECUTION_OUTPUT_REQUIRED")
    try:
        expiry = datetime.fromisoformat(grant["expires_utc"])
        lifetime = (expiry - datetime.now(timezone.utc)).total_seconds()
        valid = (
            grant["preparation_git_head"] == preparation_head()
            and grant["execution_root"] == str(root)
            and grant["review_plan_sha256"] == plan_hash
            and 0 < lifetime <= 900
        )
    except (KeyError, TypeError, ValueError):
        valid = False
    if not valid:
        raise ValueError("BOUND_SHORT_LIVED_DIAGNOSTIC_APPROVAL_REQUIRED")
    from lecturelens_real_eval.tutor.selection_smoke import live_admission

    live_admission(state["frozen"], authorization, pricing)
    database_ready()
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
    if cost["kind"] == risk_once.KIND:
        # No grant renewal is performed. Leave an exclusive, durable record even
        # if exec fails; the native CLI still creates its original own claim.
        risk_once.validate(cost, grant, preparation_head())
        risk_once.begin_handoff(root, grant, authorization, pricing, assurance)
        execute(
            "/usr/bin/timeout",
            [
                "/usr/bin/timeout",
                "--signal=TERM",
                "--kill-after=2s",
                str(risk_once.WALL_SECONDS) + "s",
                *argv,
            ],
        )
    else:
        execute(str(python), argv)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--candidate-root", type=Path, required=True)
    parser.add_argument(
        "--mode", choices=["preflight", "handoff-live"], default="preflight"
    )
    parser.add_argument("--review-plan", type=Path, default=POLICY)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--authorization", type=Path)
    parser.add_argument("--pricing", type=Path)
    parser.add_argument("--cost-assurance", type=Path)
    args = parser.parse_args()
    try:
        if args.mode == "preflight":
            print(
                json.dumps(preflight(args.candidate_root, args.review_plan), indent=2)
            )
            return 2
        if not all([args.output, args.authorization, args.pricing]):
            raise ValueError("FRESH_APPROVAL_PRICING_OUTPUT_REQUIRED")
        handoff(
            args.candidate_root,
            args.output,
            args.authorization,
            args.pricing,
            args.cost_assurance,
            args.review_plan,
        )
    except Exception:  # noqa: BLE001 -- constant admission boundary, no credential/body/connection details
        print(
            json.dumps(
                {
                    "execution": "BLOCKED",
                    "real_requests": 0,
                    "reason": "OUTER_ADMISSION_DENIED_SEE_TESTED_PREREQUISITES",
                }
            )
        )
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
