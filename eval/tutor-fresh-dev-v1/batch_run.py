"""Fixed sixteen-turn development batch; prepare-only default, existing runner in two fixed parts."""

import argparse
import json
import os
import re
import subprocess
import types
from pathlib import Path

import bridge
import data

HERE = data.HERE


def part_dir(out, part):
    return out / f"{out.name}-{part}"


def prepare(args):
    batch, scripts, snapshot = data.load()
    identity = bridge.verify_candidate()
    if args.agent != bridge.repair_check.CANDIDATE or args.model != "deepseek-flash":
        raise ValueError("EXPLICIT_CANDIDATE_AND_MODEL_REQUIRED")
    return batch, scripts, snapshot, identity


def run(args, *, dsn=None, fault=None):
    batch, scripts, snapshot, identity = prepare(args)
    if not args.mock and not args.live:
        return {
            "mode": "PREPARE_ONLY_NO_EGRESS",
            "candidate": args.agent,
            "candidate_sha256": identity,
            "frozen_base_code_sha": data.read(HERE / "candidate-freeze.json")[
                "frozen_base_code_sha"
            ],
            "counts": batch["counts"],
            "plan_sha256": data.digest(HERE / "batch-plan.json"),
            "dataset_lock_sha256": data.digest(HERE / "dataset-lock.json"),
            "freeze_sha256": data.digest(HERE / "freeze-lock.json"),
            "normal_requests": 32,
            "second_search_path_requests": 48,
            "maximum_requests": 80,
            "reviewer": "DISABLED_NOT_RUN",
            "concurrency": 1,
            "transport_retries": 0,
            "total_usd": "UNCONFIRMED",
            "real_quality": "NOT_RUN",
        }
    if args.mock and os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
        raise ValueError("MOCK_SOCKET_FENCE_REQUIRED")
    if not args.output or args.max_calls is None or args.max_usd is None:
        raise ValueError("EXPLICIT_TOTAL_CAPS_AND_NEW_OUTPUT_REQUIRED")
    if not 2 <= args.max_calls <= 80:
        raise ValueError("TOTAL_REQUEST_CAP_OUT_OF_RANGE")
    money = bridge.legacy.usd_to_nano(args.max_usd)
    if not 2 <= money <= 700_000_000:
        raise ValueError("TOTAL_USD_CAP_OUT_OF_RANGE")
    calls = [args.max_calls // 2, args.max_calls - args.max_calls // 2]
    budgets = [money // 2, money - money // 2]
    # Validate both fixed allocations before directory creation/DB/transport/credential lookup.
    for c, b in zip(calls, budgets, strict=True):
        bridge.legacy.TutorPolicy(
            live=args.live, max_calls=c, max_nano_usd=b, candidate_sha256=identity
        ).validate()
    if args.live:
        if not args.ack_ledger_not_billing_cap or not args.pricing:
            raise ValueError("LIVE_REQUIRES_FRESH_PRICING_AND_BILLING_ACK")
        bridge.repair_run.check_pricing(args.pricing)
    out = Path(args.output)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,38}", out.name):
        raise ValueError("BATCH_NAME_INVALID")
    out.mkdir(parents=True, exist_ok=False)
    planned = bridge.module.expected_rows(snapshot, scripts)
    # Keep the predeclared batch execution order, not incidental course iteration order.
    by_key = {r["turn_key"]: r for r in planned}
    planned = [by_key[k] for k in batch["turn_keys"]]
    config = {
        "data_kind": "REAL" if args.live else "MOCK",
        "live": args.live,
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=data.ROOT, text=True
        ).strip(),
        "agent": args.agent,
        "candidate_sha256": identity,
        "dataset_version": data.VERSION,
        "dataset_lock_sha256": data.digest(HERE / "dataset-lock.json"),
        "plan_sha256": data.digest(HERE / "batch-plan.json"),
        "freeze_sha256": data.digest(HERE / "freeze-lock.json"),
        "reviewer": "DISABLED_NOT_RUN",
        "concurrency": 1,
        "transport_retries": 0,
        "sdk_retries": 0,
        "application_transport_retries": 0,
        "max_total_calls": args.max_calls,
        "max_total_local_nano_usd": money,
        "allocation": {
            "A": {"calls": calls[0], "nano_usd": budgets[0]},
            "B": {"calls": calls[1], "nano_usd": budgets[1]},
        },
        "budget_transfer": False,
        "supplier_bill_hard_cap": "UNVERIFIED",
        "quality_status": "NOT_RUN",
        "selected_dialogue_ids": [d["dialogue_id"] for d in scripts],
    }
    data.write(out / "config.json", config)
    data.write(
        out / "expected-turns.json",
        {"turns": planned, "plan_sha256": config["plan_sha256"]},
    )
    results = []
    parts = []
    failures = []
    original = bridge.repair_run.contract
    try:
        for i, ref in enumerate(batch["parts"]):
            plan = data.read(HERE / ref["path"])
            subset = [
                next(d for d in scripts if d["dialogue_id"] == s["dialogue_id"])
                for s in plan["sessions"]
            ]

            def load_part(path, ref=ref, plan=plan, subset=subset):
                if Path(path).resolve() != HERE / ref["path"]:
                    raise ValueError("PART_PATH_MISMATCH")
                data.load()
                return plan, subset, snapshot

            bridge.repair_run.contract = types.SimpleNamespace(
                CANDIDATE=original.CANDIDATE,
                ENTRYPOINT=original.ENTRYPOINT,
                CONTEXT_VERSION=original.CONTEXT_VERSION,
                verify_candidate=bridge.verify_candidate,
                load_plan=load_part,
            )
            options = argparse.Namespace(**vars(args))
            options.plan = str(HERE / ref["path"])
            options.max_calls = calls[i]
            options.max_usd = (
                f"{budgets[i] // 1_000_000_000}.{budgets[i] % 1_000_000_000:09d}"
            )
            options.output = str(part_dir(out, plan["part"]))
            transport = (
                bridge.legacy.mock_transport(subset, fault=fault if i == 0 else None)
                if args.mock
                else None
            )
            summary = bridge.repair_run.run(options, dsn=dsn, transport=transport)
            rows_path = part_dir(out, plan["part"]) / "turns.jsonl"
            results.extend(
                json.loads(line) for line in rows_path.read_text().splitlines()
            )
            parts.append({"part": plan["part"], "summary": summary})
            if summary["mechanics_status"] != "COMPLETE":
                failures.append(
                    {"code": "BATCH_STOPPED_ON_PART_FAILURE", "part": plan["part"]}
                )
                break
    except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- retain scheduled missing with safe fixed codes
        failures.append({"code": "BATCH_ABORTED", "type": type(error).__name__})
    finally:
        bridge.repair_run.contract = original
    rows = bridge.reconcile(planned, results)
    for row in rows:
        bridge.legacy.append(out / "turns.jsonl", row)
    counts = bridge.execution_counts(rows)
    run_data = {
        "rows": rows,
        "planned": planned,
        "config": config,
        "scripts": scripts,
        "directory": str(out.resolve()),
        "queue_sha256": config["plan_sha256"],
        "result_origin": "fixed_parts",
        "input_hashes": {},
    }
    diagnostics = bridge.failure_items(run_data)
    part_for = {
        sid: spec["part"]
        for spec in data.read(HERE / "candidate-freeze.json")["parts"]
        for sid in spec["sessions"]
    }
    for item in diagnostics["items"]:
        part = part_for[item["dialogue_id"]]
        item["trace"].update(
            calls_path=str(part_dir(out, part) / "calls.jsonl"),
            ledger_path=str(part_dir(out, part) / "ledger.jsonl"),
        )
    data.write(out / "failure-review.json", diagnostics)
    data.write(out / "unannotated-scores.json", bridge.summarize(run_data, {}))
    summary = dict(
        data_kind=config["data_kind"],
        **counts,
        parts=parts,
        failures=failures,
        mechanics_status="COMPLETE"
        if counts["completed_turns"] == 16 and not failures
        else "INCOMPLETE",
        reviewer="DISABLED_NOT_RUN",
        reviewer_calls=0,
        real_quality="NOT_RUN",
        real_tokens="NOT_RUN",
        real_cost="NOT_RUN" if args.mock else "REQUIRES_USAGE_RECONCILIATION",
        independent_human_agreement="NOT_RUN",
    )
    data.write(out / "summary.json", summary)
    return summary


def parser():
    p = argparse.ArgumentParser(description=__doc__)
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--mock", action="store_true")
    mode.add_argument("--live", action="store_true")
    p.add_argument("--agent", required=True, choices=[bridge.repair_check.CANDIDATE])
    p.add_argument("--model", required=True, choices=["deepseek-flash"])
    p.add_argument("--reviewer", choices=["off"], default="off")
    p.add_argument("--concurrency", type=int, choices=[1], default=1)
    p.add_argument("--max-calls", type=int)
    p.add_argument("--max-usd")
    p.add_argument("--pricing")
    p.add_argument("--ack-ledger-not-billing-cap", action="store_true")
    p.add_argument("--output")
    return p


if __name__ == "__main__":
    try:
        result = run(parser().parse_args())
        print(json.dumps(result))
        raise SystemExit(1 if result.get("mechanics_status") == "INCOMPLETE" else 0)
    except Exception:  # noqa: BLE001 -- no provider/DB/config body reaches CLI output
        print(
            json.dumps(
                {
                    "error": "FROZEN_BATCH_PREFLIGHT_OR_STARTUP_REJECTED",
                    "real_calls": "NOT_RUN_OR_UNKNOWN",
                }
            )
        )
        raise SystemExit(2) from None
