"""Offline evidence checks; no HTTP, DB access, model calls or modifications."""

import hashlib
import json
import re

from score import aggregate
from support import PUBLIC, ROOT


def load(name):
    return json.loads((PUBLIC / name).read_text())


def main():
    actual = aggregate()
    assert actual == load("summary.json")
    assert actual["finished_trials"] == actual["submitted_trials"] == 10
    trials = actual["trials"]
    assert len({t["task_id"] for t in trials}) == 10
    assert {(t["source_id"], t["repeat"]) for t in trials} == {
        (s, n)
        for s in ["algorithms", "calculus", "economics", "linear", "probability"]
        for n in [1, 2]
    }
    assert all(t["config_version"] == 10 for t in trials)
    assert all(t["task_terminal_seconds"] <= 1800 for t in trials)
    disks = [
        json.loads(x)
        for x in (PUBLIC / "disk-observations.jsonl").read_text().splitlines()
    ]
    assert disks and all(d["percent"] <= 85 for d in disks)
    for t in trials:
        snapshots = load("snapshots/" + t["trial_id"] + ".json")
        assert snapshots and all(
            s["configVersion"] == 10
            and s["routes"]["TRANSLATION_FULL_TEXT"]["source"] == "DATABASE"
            and s["routes"]["TRANSLATION_FULL_TEXT"]["model"] == "deepseek-flash"
            for s in snapshots
        )
        if t["deepseek_total_tokens"] is None:
            assert t["deepseek_list_price_usd"] is None
    rows = [json.loads(x) for x in (PUBLIC / "trials.jsonl").read_text().splitlines()]
    manifest = json.loads(
        (ROOT / "eval/baseline-asr-20261015/assets.lock.json").read_text()
    )
    media = {s["id"]: s["evaluation_video_sha256"] for s in manifest["sources"]}
    assert all(r["source_sha256"] == media[r["source_id"]] for r in rows)
    assert load("original-baseline-db-before.json") == load(
        "original-baseline-db-after.json"
    )
    dead = load("dead-handling.json")
    assert (
        dead["failed_task_count"] == 30
        and dead["formal_baseline_count"] == 10
        and dead["non_baseline_failed_count"] == 20
    )
    assert (
        dead["retry_backlog_total"]
        == dead["database_writes"]
        == dead["messages_consumed_by_cleanup"]
        == 0
    )
    assert not dead["dead_letter_topics"]
    for period in ["before", "final"]:
        offsets = load("mq-consumer-offsets-" + period + ".json")["offsetTable"]
        topics = load("mq-retry-dead-offsets-" + period + ".json")
        for item in topics:
            topic = item["topic"]
            assert not topic.startswith("%DLQ%")
            group = topic.split("%RETRY%", 1)[1].rsplit("_", 1)[0]
            consumed = offsets[topic + "@" + group]
            for line in item["stdout"].splitlines():
                p = line.split()
                if len(p) > 3 and p[0] == "broker-a" and p[1].isdigit():
                    assert int(p[3]) == consumed[p[1]], (period, topic, p)
    final = load("final-check.json")
    assert final["binding_retained"] and final["version"] == 10
    assert (
        final["original_baseline_db_unchanged"]
        and final["jar_unchanged"]
        and all(final["services_unchanged"].values())
    )
    assert final["disk"]["percent"] <= 85 and not final["active_tasks"]
    assert load("catalog-final.json") == load("catalog-bound.json")
    freeze = load("measurement-freeze.json")
    for path, digest in freeze["files"].items():
        assert hashlib.sha256((ROOT / path).read_bytes()).hexdigest() == digest, path
    # Search evidence for credential-shaped values; never print any matched value.
    for p in PUBLIC.rglob("*"):
        if p.is_file() and p.suffix in [".json", ".jsonl", ".md", ".txt"]:
            text = p.read_text()
            assert not re.search(r"\bsk-[A-Za-z0-9_-]{12,}", text), str(p)
            assert not re.search(r"Bearer\s+eyJ[A-Za-z0-9._-]+", text), str(p)
    print(
        json.dumps(
            {
                "checks": "PASS",
                "trials": 10,
                "baseline_rows_preserved": 10,
                "config_version": 10,
                "retry_dead_backlog": 0,
                "business_files_changed": 0,
                "usage_complete_trials": actual["usage_complete_trials"],
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
