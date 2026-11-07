"""Read-only independent queue/result/call/PG-event reconciliation."""

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path

from records import execution_counts, read_run
from shared import jsonl, legacy, read, write


def check(queue_path, directory, database=False):
    run = read_run(queue_path, directory)
    directory = Path(directory)
    expected = {f"{d['dialogue_id']}:{n}" for d in run["scripts"] for n in range(1, 6)}
    assert len(expected) == 20 and {r["turn_key"] for r in run["rows"]} == expected
    assert {r["course_id"] for r in run["rows"]} == {"queue", "ecology"}
    assert all(r["split"] == "development" for r in run["rows"])
    states = Counter()
    calls = 0
    mirrored = 0
    reserved = 0
    for course in ("queue", "ecology"):
        source = directory / course
        attempts = jsonl(source / "calls.jsonl")
        events = jsonl(source / "ledger.jsonl")
        calls += len(attempts)
        states.update(e["state"] for e in events)
        assert [e["sequence"] for e in events] == list(range(1, len(events) + 1))
        groups = defaultdict(list)
        for e in events:
            groups[e["call_id"]].append(e)
        for history in groups.values():
            assert (
                len(history) == 2
                and history[0]["state"] == "reserved"
                and history[1]["state"] in ("settled", "failed")
            )
            assert history[0]["wire_sha256"] == history[1]["wire_sha256"]
        reserved += len(groups)
        if database:
            import psycopg
            from psycopg.rows import dict_row

            with psycopg.connect(
                legacy.DSN, row_factory=dict_row, options="-cdefault_transaction_read_only=on"
            ) as conn:
                assert conn.execute("SHOW transaction_read_only").fetchone()["transaction_read_only"] == "on"
                persisted = [
                    r["record"]
                    for r in conn.execute(
                        "SELECT record FROM p8_tutor_real_event WHERE run_id=%s ORDER BY sequence",
                        (f"{directory.name}-{course}",),
                    )
                ]
                assert persisted == events
                for r in run["rows"]:
                    if r["course_id"] != course or r["status"] == "MISSING":
                        continue
                    row = conn.execute(
                        "SELECT * FROM tutor_turn WHERE turn_id=%s", (r["turn_id"],)
                    ).fetchone()
                    for f in (
                        "ordinal",
                        "learner_text",
                        "status",
                        "outcome",
                        "answer",
                        "evaluation",
                        "error_code",
                        "usage",
                    ):
                        assert row[f] == r[f]
                    owner = conn.execute(
                        "SELECT owner_id,course_id FROM tutor_session WHERE session_id=%s", (r["session_id"],)
                    ).fetchone()
                    assert owner["owner_id"] == 811008 and owner["course_id"].endswith(r["dialogue_id"])
            mirrored += len(events)
    summary = read(directory / "summary.json")
    assert summary["recorded_calls"] == calls
    assert summary["reserved_calls"] == reserved
    assert summary["settled_calls"] == states["settled"] + states["failed"]
    assert summary["statuses"] == dict(Counter(r["status"] for r in run["rows"]))
    return dict(
        queue_sha256=run["queue_sha256"],
        counts=execution_counts(run["rows"]),
        attempted_requests=calls,
        ledger_states=dict(states),
        pg_content_equal_events=mirrored,
        quality_status="NOT_RUN",
        no_holdout_execution=True,
        cost_status="NOT_RUN",
    )


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--queue", required=True)
    p.add_argument("--run", required=True)
    p.add_argument("--database", action="store_true")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = check(a.queue, a.run, a.database)
    write(a.output, result)
    print(json.dumps(result))
