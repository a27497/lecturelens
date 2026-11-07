"""Independent file/PG reconciliation; never uses the runner's summary calculation."""

import argparse
import hashlib
import json
from collections import Counter
from pathlib import Path

from dataset import HERE, write


def lines(path):
    return [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]


def check(run, database=False, blind=None):
    snapshot = json.loads((HERE / "snapshot.json").read_text())
    partitions = {
        s: json.loads((HERE / f"{s}.json").read_text())["dialogues"] for s in ("development", "holdout")
    }
    dev_courses = {d["course_id"] for d in partitions["development"]}
    held_courses = {d["course_id"] for d in partitions["holdout"]}
    assert not dev_courses & held_courses
    assert len(dev_courses | held_courses) == 4
    assert sum(len(ds) for ds in partitions.values()) == 64
    assert sum(len(d["turns"]) for ds in partitions.values() for d in ds) == 320
    manifest = json.loads((HERE / "holdout-manifest.json").read_text())
    assert set(manifest["course_ids"]) == held_courses
    assert manifest["dataset_sha256"] == hashlib.sha256((HERE / "holdout.json").read_bytes()).hexdigest()
    for ds in partitions.values():
        for d in ds:
            source = {e["evidence_id"]: e for e in snapshot["lectures"][d["course_id"]]["evidence"]}
            for t in d["turns"]:
                for eid in t["reference"]["evidence_ids"]:
                    assert source[eid]["text"] == t["reference"]["quote"]
    run = Path(run)
    config = json.loads((run / "config.json").read_text())
    scripts = [d for ds in partitions.values() for d in ds]
    if config["smoke"]:
        scripts = [next(d for d in scripts if d["course_id"] == c) for c in snapshot["lectures"]]
    expected = {f"{d['dialogue_id']}:{n}" for d in scripts for n in range(1, len(d["turns"]) + 1)}
    rows = lines(run / "turns.jsonl")
    assert len(rows) == len(expected) and {r["turn_key"] for r in rows} == expected
    totals = Counter(r["status"] for r in rows)
    call_total, settled, reserved, pg_events = 0, 0, 0, 0
    call_by_key = Counter()
    for course in snapshot["lectures"]:
        shard = run / course
        calls = lines(shard / "calls.jsonl") if (shard / "calls.jsonl").exists() else []
        ledger = lines(shard / "ledger.jsonl")
        call_total += len(calls)
        call_by_key.update(c["turn_key"] for c in calls)
        reserved += sum(e["state"] == "reserved" for e in ledger)
        settled += sum(e["state"] == "settled" for e in ledger)
        assert all(c["cost_status"] == "NOT_RUN" for c in calls)
        if config["data_kind"] == "MOCK":
            assert all(c["usage_source"] == "MOCK_NOT_BILLABLE" and not c["live"] for c in calls)
        if database:
            import psycopg
            from run import DSN

            with psycopg.connect(DSN) as conn:
                events = [
                    r[0]
                    for r in conn.execute(
                        "SELECT record FROM p8_tutor_real_event WHERE run_id=%s ORDER BY sequence",
                        (f"{run.name}-{course}",),
                    )
                ]
            assert events == ledger
            pg_events += len(events)
    # A budget refusal has a call record but no reservation; it is still a failed attempted request.
    embedded_calls = sum(len(r["calls"]) for r in rows)
    assert embedded_calls <= call_total
    summary = json.loads((run / "summary.json").read_text())
    assert summary["statuses"] == dict(totals) and summary["scheduled_turns"] == len(expected)
    assert summary["recorded_calls"] == embedded_calls
    if "reserved_calls" in summary:
        assert summary["reserved_calls"] == reserved
        assert summary["settled_calls"] == settled
    assert summary["mechanics_status"] == "INCOMPLETE" or (
        totals == {"completed": len(expected)} and not summary["failures"]
    )
    result = dict(
        data_kind=config["data_kind"],
        courses=4,
        sessions=len(scripts),
        scheduled_turns=len(expected),
        partitions={
            s: dict(
                courses=len({d["course_id"] for d in ds}),
                sessions=len(ds),
                turns=sum(len(d["turns"]) for d in ds),
            )
            for s, ds in partitions.items()
        },
        statuses=dict(totals),
        call_records=call_total,
        embedded_calls=embedded_calls,
        reserved_calls=reserved,
        settled_calls=settled,
        pg_mirror_events=pg_events,
        cost_status="NOT_RUN",
        quality_status="NOT_RUN",
    )
    if blind:
        blind = Path(blind)
        key = json.loads((blind / "private-key.json").read_text())
        packets = {r: json.loads((blind / f"packet-{r}.json").read_text()) for r in "AB"}
        assert len(packets["A"]["items"]) == 100 and len(packets["B"]["items"]) == 20
        a = {i["item_id"] for i in packets["A"]["items"]}
        b = {i["item_id"] for i in packets["B"]["items"]}
        assert b <= a
        strata = Counter((key["mappings"][i]["course_id"], key["mappings"][i]["category"]) for i in a)
        assert len(strata) == 20 and set(strata.values()) == {5}
        result["blind_review"] = dict(primary=100, overlap=20, strata=20, human_scores_status="NOT_RUN")
    return result


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--run", required=True)
    p.add_argument("--database", action="store_true")
    p.add_argument("--blind")
    p.add_argument("--output", required=True)
    a = p.parse_args()
    result = check(a.run, a.database, a.blind)
    write(a.output, result)
    print(json.dumps(result))
