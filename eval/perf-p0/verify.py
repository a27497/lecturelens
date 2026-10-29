"""Check final evidence provenance and recalculate reported metrics from raw attempts."""

import argparse
import hashlib
import json
import math
from pathlib import Path

from load import summary


def verify(directory, sha, require_busy=False):
    result = json.loads((directory / "result.json").read_text())
    assert result["success"], "Run did not complete successfully"
    assert (
        result["head"] == sha == result["source"]["sha"] == result["end_source"]["sha"]
    ), "SHA mismatch"
    assert (
        result["valid_clean_source_evidence"] and not result["source"]["source_dirty"]
    ), "Dirty source evidence"
    assert result["source"] == result["end_source"], "Source drift"
    assert result["stages"]["cleanup"]["status"] == "PASS", "Cleanup not proven"
    config_hash = hashlib.sha256(
        json.dumps(result["config"], sort_keys=True).encode()
    ).hexdigest()
    assert config_hash == result["config_sha256"], "Config fingerprint mismatch"
    rows = [
        json.loads(line)
        for line in (directory / "requests.jsonl").read_text().splitlines()
    ]
    assert len({row["request_id"] for row in rows}) == len(rows), (
        "Duplicate logical attempts"
    )
    observed = 0
    for item in result["warmups"] + result["groups"]:
        selected = [
            r
            for r in rows
            if (r["scenario"], r["concurrency"], r["warmup"])
            == (item["scenario"], item["concurrency"], item["warmup"])
        ]
        recalculated = summary(selected, item["wall_seconds"])
        observed += len(selected)
        for key, expected in recalculated.items():
            if isinstance(expected, float):
                assert math.isclose(
                    expected, item[key], rel_tol=0.0001, abs_tol=0.0001
                ), key
            else:
                assert item[key] == expected, key
        assert not item["undrained_tutor"], "Hidden Tutor backlog"
    assert observed == len(rows), "Unaccounted raw requests"
    if require_busy:
        assert any(
            g["scenario"] == "S1"
            and g["retrieval_busy_503"] > 0
            and g["retry_after_counts"].get("1", 0) > 0
            for g in result["groups"]
        ), "No genuine direct-retrieval busy 503 observed"
    return {
        "sha": sha,
        "label": result["label"],
        "groups": len(result["groups"]),
        "raw_attempts_including_warmup": len(rows),
        "status": "PASS",
    }


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--require-busy", action="store_true")
    args = parser.parse_args()
    print(json.dumps(verify(args.directory, args.sha, args.require_busy)))
