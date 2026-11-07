"""Mock-only compatibility driver for public texts; no live-provider entry point."""

import argparse
import json
import os
import re
import subprocess
from collections import Counter
from pathlib import Path

from public_bridge import (
    execution_counts,
    failure_items,
    legacy,
    summarize,
    verify_tooling,
)
from public_dataset import (
    HERE,
    ROOT,
    VERSION,
    digest,
    expected_rows,
    object_hash,
    select,
    write,
)


def reconcile(planned, results):
    by_key = {}
    for r in results:
        if r["turn_key"] in by_key:
            raise ValueError("DUPLICATE_RESULT")
        by_key[r["turn_key"]] = r
    if not by_key.keys() <= {p["turn_key"] for p in planned}:
        raise ValueError("UNEXPECTED_RESULT")
    return [
        by_key.get(
            p["turn_key"],
            dict(
                **p,
                status="MISSING",
                error_code="RESULT_MISSING",
                answer=None,
                evaluation=None,
                outcome=None,
                citations=[],
                review=None,
                calls=[],
            ),
        )
        for p in planned
    ]


def run(args):
    # Required in addition to the inherited channel's MockTransport admission.
    if os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
        raise ValueError("SOCKET_FENCED_LAUNCHER_REQUIRED")
    identity = verify_tooling()
    snapshot, scripts = select(
        args.split, args.course, args.session, args.evaluation_only_holdout
    )
    planned = expected_rows(snapshot, scripts)
    courses = list(snapshot["lectures"])
    out = Path(args.output)
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,55}", out.name):
        raise ValueError("RUN_NAME_INVALID")
    policy = legacy.TutorPolicy(
        live=False,
        max_calls=args.max_calls // len(courses),
        max_nano_usd=legacy.usd_to_nano("0.70"),
        candidate_sha256=identity,
    )
    policy.validate()
    out.mkdir(parents=True, exist_ok=False)
    config = {
        "schema": VERSION,
        "data_kind": "MOCK",
        "material_kind": "PUBLIC_COURSE_TEXT",
        "live": False,
        "code_sha": subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
        ).strip(),
        "adapter_sha256": {p.name: digest(p) for p in sorted(HERE.glob("*.py"))},
        "candidate_sha256": identity,
        "dataset_version": VERSION,
        "dataset_lock_sha256": digest(HERE / "dataset-lock.json"),
        "split_sha256": digest(HERE / "course-split.json"),
        "selected_dialogue_ids": [d["dialogue_id"] for d in scripts],
        "course_ids": courses,
        "scope": args.split,
        "expected_turns_sha256": object_hash(planned),
        "max_calls": args.max_calls,
        "per_shard_calls": policy.max_calls,
        "per_shard_mock_reservation_nano_usd": policy.max_nano_usd,
        "pricing_source": None,
        "quality_status": "NOT_RUN",
        "cost_status": "NOT_RUN",
        "real_tokens_status": "NOT_RUN",
        "owner_id": 811009,
    }
    write(
        out / "expected-turns.json",
        {"dataset_lock_sha256": config["dataset_lock_sha256"], "turns": planned},
    )
    write(out / "config.json", config)
    results, failures, accountings = [], [], []
    for course in courses:
        subset = [d for d in scripts if d["course_id"] == course]
        shard = out / course
        shard.mkdir()
        ledger = legacy.Ledger(
            legacy.DSN, shard / "ledger.jsonl", f"{out.name}-{course}", policy
        )
        runtime = None
        try:
            ledger.install()
            channel = legacy.RecordedChannel(
                ledger,
                records=shard / "calls.jsonl",
                pricing_source=None,
                transport=legacy.MetadataTransport(legacy.mock_transport(subset)),
            )
            # Only selected course texts are registered; references remain outside authority.
            authority = legacy.SnapshotAuthority(snapshot)
            provider = legacy.TutorProvider(channel, authority)
            store = legacy.TutorStore(ledger.dsn)
            runtime = legacy.TutorRuntime(store, authority, provider)
            runtime.initialize()
            for script in subset:
                scope = {
                    "owner_id": 811009,
                    "course_id": f"public-{out.name}-{script['dialogue_id']}",
                    "revision": 1,
                }
                authority.register(scope, script["lecture_id"])
                session = runtime.command(
                    legacy.Command(**scope, operation="CREATE", request_key="session")
                )["session"]
                scope["session_id"] = session["session_id"]
                provider.scope = scope
                history = []
                for ordinal, task in enumerate(script["turns"], 1):
                    channel.turn_key = f"{script['dialogue_id']}:{ordinal}"
                    channel.turn_calls, provider.proposals = [], []
                    runtime.command(
                        legacy.Command(
                            **scope,
                            operation="TURN",
                            client_turn_id=f"turn-{ordinal}",
                            text=task["text"],
                            socratic=task["socratic"],
                        )
                    )
                    runtime.execute(
                        next(
                            c
                            for c in store.candidates()
                            if c["session_id"] == session["session_id"]
                        )
                    )
                    turn = runtime.command(legacy.Command(**scope, operation="GET"))[
                        "turns"
                    ][-1]
                    sources = {e["evidence_id"]: e for e in authority.rows(scope)}
                    turn["citations"] = [
                        sources[c["evidence_id"]] for c in turn["citations"]
                    ]
                    turn.update(
                        next(p for p in planned if p["turn_key"] == channel.turn_key)
                    )
                    turn.update(proposals=provider.proposals, review=None)
                    if turn["status"] == "completed":
                        try:
                            turn["review"] = legacy.review_turn(
                                channel, history, task, turn
                            )
                        except Exception:  # noqa: BLE001 -- fixed failure code, no request/credential dump
                            turn["review"] = {"error": "REVIEW_FAILED"}
                    turn["calls"] = channel.turn_calls.copy()
                    results.append(turn)
                    legacy.append(shard / "turns.jsonl", turn)
                    history = [
                        *history,
                        {
                            "learner": task["text"],
                            "tutor": turn["answer"],
                            "status": turn["status"],
                            "outcome": turn["outcome"],
                        },
                    ][-6:]
                    if ledger.check()["blocked"]:
                        raise legacy.EvalError("MOCK_LEDGER_BLOCKED")
        except Exception as error:  # noqa: BLE001 -- preserve scheduled missing, avoid provider body logging
            failures.append(
                {
                    "course_id": course,
                    "error": error.code
                    if isinstance(error, legacy.EvalError)
                    else "MOCK_SHARD_FAILED",
                    "error_type": type(error).__name__,
                }
            )
        finally:
            if runtime:
                runtime.close()
            try:
                accounting = ledger.check()
            except Exception:  # noqa: BLE001 -- unknown remains null
                accounting = None
                failures.append({"course_id": course, "error": "ACCOUNTING_UNKNOWN"})
            accountings.append(accounting)
            write(
                shard / "accounting.json",
                {
                    "legacy_mock_reservation_accounting": accounting,
                    "cost_status": "NOT_RUN",
                },
            )
    rows = reconcile(planned, results)
    for row in rows:
        legacy.append(out / "turns.jsonl", row)
    run_data = {
        "rows": rows,
        "planned": planned,
        "config": config,
        "scripts": scripts,
        "directory": str(out.resolve()),
        "queue_sha256": object_hash(planned),
        "result_origin": "aggregate",
        "input_hashes": {},
    }
    counts = execution_counts(rows)
    bad_reviews = sum(
        r["status"] == "completed"
        and (not r["review"] or bool(r["review"].get("error")))
        for r in rows
    )
    complete = (
        counts["completed_turns"] == len(planned) and not failures and not bad_reviews
    )
    summary = dict(
        data_kind="MOCK",
        courses=len(courses),
        sessions=len(scripts),
        **counts,
        mechanics_status="COMPLETE" if complete else "INCOMPLETE",
        failures=failures,
        recorded_calls=sum(len(r["calls"]) for r in rows),
        review_failed_or_missing=bad_reviews,
        outcome_counts=dict(Counter(r["outcome"] for r in rows)),
        quality_status="NOT_RUN",
        human_scores_status="NOT_RUN",
        cost_status="NOT_RUN",
        real_tokens_status="NOT_RUN",
        **legacy.accounting_totals(accountings),
    )
    write(out / "summary.json", summary)
    write(out / "unannotated-scores.json", summarize(run_data, {}))
    write(out / "failure-review.json", failure_items(run_data))
    print(json.dumps(summary))
    return 0 if complete else 1


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--split", choices=["development", "holdout", "all"], required=True)
    p.add_argument("--course", action="append", help="Exact course ID, repeatable")
    p.add_argument(
        "--session", action="append", help="Exact complete session ID, repeatable"
    )
    p.add_argument("--evaluation-only-holdout", action="store_true")
    p.add_argument("--output", required=True)
    p.add_argument(
        "--max-calls",
        type=int,
        default=240,
        help="Mock-only total persistent request ceiling",
    )
    a = p.parse_args()
    if not 3 <= a.max_calls <= 240:
        p.error("Mock call ceiling must be 3..240")
    raise SystemExit(run(a))
