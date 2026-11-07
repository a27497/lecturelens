"""Reconcile scheduled turns even after a crash before the result file exists."""

from collections import Counter, defaultdict
from pathlib import Path

from plan import expected_rows, load_queue
from shared import digest, jsonl, object_hash, read


def read_run(queue_path, directory):
    queue, scripts, snapshot, identity = load_queue(queue_path)
    directory = Path(directory)
    planned = expected_rows(scripts)
    by_plan = {r["turn_key"]: r for r in planned}
    config = read(directory / "config.json") if (directory / "config.json").exists() else None
    if config and (
        config.get("candidate_sha256") != identity
        or config.get("data_kind") not in ("MOCK", "REAL")
        or config.get("queue_sha256") != digest(queue_path)
        or config.get("dataset_lock_sha256") != queue["dataset_lock_sha256"]
        or config.get("dataset_version") != queue["dataset_version"]
        or config.get("expected_turns_sha256") != object_hash(planned)
        or config.get("selected_dialogue_ids") != [d["dialogue_id"] for d in scripts]
        or config.get("scope") != "frozen_development_queue"
    ):
        raise ValueError("RUN_SCOPE_OR_VERSION_MISMATCH")
    plan_file = directory / "expected-turns.json"
    if plan_file.exists() and read(plan_file) != dict(queue_sha256=digest(queue_path), turns=planned):
        raise ValueError("RUN_EXPECTED_PLAN_CHANGED")
    aggregate = directory / "turns.jsonl"
    if aggregate.exists():
        raw = jsonl(aggregate)
        origin = "aggregate"
    else:
        raw = [r for c in snapshot["lectures"] for r in jsonl(directory / c / "turns.jsonl")]
        origin = "shards" if raw else "NO_RESULT_FILE"
    by_key = {}
    for row in raw:
        key = row["turn_key"]
        if key not in by_plan or key in by_key:
            raise ValueError("DUPLICATE_OR_UNEXPECTED_TURN_RESULT")
        if row.get("script") != by_plan[key]["script"]:
            raise ValueError("RESULT_SCRIPT_MISMATCH")
        for field in ("dialogue_id", "ordinal", "course_id", "split"):
            if row.get(field) != by_plan[key][field]:
                raise ValueError("RESULT_SCOPE_MISMATCH")
        if row["status"] not in ("completed", "failed", "cancelled", "MISSING"):
            raise ValueError("RESULT_STATUS_INVALID")
        by_key[key] = row
    if aggregate.exists():
        shard_keys = set()
        for course in snapshot["lectures"]:
            for item in jsonl(directory / course / "turns.jsonl"):
                key = item["turn_key"]
                if key in shard_keys or by_key.get(key) != item:
                    raise ValueError("RESULT_SHARD_MIRROR_MISMATCH")
                shard_keys.add(key)
    calls = defaultdict(list)
    for c in snapshot["lectures"]:
        for call in jsonl(directory / c / "calls.jsonl"):
            if call["turn_key"] not in by_plan:
                raise ValueError("UNEXPECTED_CALL_SCOPE")
            calls[call["turn_key"]].append(call)
    rows = []
    for p in planned:
        key = p["turn_key"]
        r = by_key.get(key)
        if not r:
            r = {
                **p,
                "status": "MISSING",
                "error_code": "RESULT_MISSING",
                "answer": None,
                "evaluation": None,
                "outcome": None,
                "citations": [],
                "review": None,
                "calls": calls[key],
            }
        elif key in calls and r.get("calls", []) != calls[key]:
            raise ValueError("RESULT_CALL_MIRROR_MISMATCH")
        rows.append(r)
    return dict(
        queue=queue,
        scripts=scripts,
        planned=planned,
        rows=rows,
        config=config,
        result_origin=origin,
        candidate_sha256=identity,
        queue_sha256=digest(queue_path),
        directory=str(directory.resolve()),
        input_hashes={
            str(p.relative_to(directory)): digest(p)
            for p in sorted(directory.rglob("*.json*"))
            if p.is_file()
            and p.name
            in (
                "config.json",
                "expected-turns.json",
                "turns.jsonl",
                "calls.jsonl",
                "ledger.jsonl",
                "accounting.json",
                "summary.json",
            )
        },
    )


def execution_counts(rows):
    statuses = Counter(r["status"] for r in rows)
    completed = statuses["completed"]
    failed = statuses["failed"] + statuses["cancelled"]
    missing = statuses["MISSING"]
    return dict(
        expected_turns=len(rows),
        executed_result_turns=completed + failed,
        completed_turns=completed,
        failed_turns=failed,
        missing_result_turns=missing,
        attempted_turns=sum(r["status"] != "MISSING" or bool(r.get("calls")) for r in rows),
        scorable_turns=completed,
        statuses=dict(statuses),
    )


def failure_items(run):
    result = []
    for r in run["rows"]:
        reasons = []
        code = r.get("error_code")
        if r["status"] == "MISSING":
            reasons.append("MISSING_RESULT")
        elif r["status"] != "completed":
            reasons.append("EXECUTION_" + r["status"].upper())
        if code:
            reasons.append(code)
        bad_calls = [
            dict(index=i, purpose=c.get("purpose"), error=c.get("error"), status=c["status"])
            for i, c in enumerate(r.get("calls", []), 1)
            if c["status"] != "SUCCEEDED"
        ]
        if bad_calls:
            reasons.append("CALL_FAILED")
        if (r.get("review") or {}).get("error"):
            reasons.append("REVIEW_FAILED")
        if code and any(w in code for w in ("FORMAT", "PROTOCOL", "MALFORMED", "INVALID")):
            reasons.append("PROTOCOL_OR_MALFORMED_RESPONSE")
        if code and any(w in code for w in ("TIMEOUT", "DEADLINE")):
            reasons.append("TIMEOUT_OR_DEADLINE")
        config = run["config"] or {}
        if bad_calls and config.get("data_kind") == "MOCK" and config.get("fault"):
            reasons.append("MOCK_INJECTED_" + config["fault"].upper())
        if not reasons:
            continue
        result.append(
            dict(
                turn_key=r["turn_key"],
                dialogue_id=r["dialogue_id"],
                ordinal=r["ordinal"],
                course_id=r["course_id"],
                status=r["status"],
                reasons=list(dict.fromkeys(reasons)),
                failed_calls=bad_calls,
                learner_text=r["script"]["text"],
                expected_behavior=r["script"]["reference"]["expected_behavior"],
                reference=r["script"]["reference"],
                answer=r["answer"],
                evaluation=r["evaluation"],
                history=[
                    dict(
                        turn_key=h["turn_key"],
                        learner_text=h["script"]["text"],
                        answer=h["answer"],
                        status=h["status"],
                    )
                    for h in run["rows"]
                    if h["dialogue_id"] == r["dialogue_id"] and h["ordinal"] < r["ordinal"]
                ],
                trace=dict(
                    run_directory=run["directory"],
                    queue_sha256=run["queue_sha256"],
                    result_origin=run["result_origin"],
                    calls_path=f"{run['directory']}/{r['course_id']}/calls.jsonl",
                    ledger_path=f"{run['directory']}/{r['course_id']}/ledger.jsonl",
                    session_id=r.get("session_id"),
                    turn_id=r.get("turn_id"),
                ),
            )
        )
    return dict(
        schema="tutor-scale-diagnostic-v2",
        population="EXPECTED_EXECUTION_QUEUE_CENSUS",
        purpose="DIAGNOSTIC_ONLY_NEVER_POOL_WITH_RANDOM_SAMPLE",
        data_kind=(run["config"] or {}).get("data_kind", "UNKNOWN"),
        quality_status="NOT_RUN",
        counts=execution_counts(run["rows"]),
        items=result,
        input_hashes=run["input_hashes"],
        metadata_complete=bool(run["config"]),
    )
