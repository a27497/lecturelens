"""Read-only provenance/matrix audit; independently recompute metrics, including legacy v1."""

import argparse
import hashlib
import json
import math
import re
import subprocess
from collections import Counter
from pathlib import Path, PurePosixPath


class VerificationError(AssertionError):
    pass


def require(condition, message):
    # Evidence checks must remain active under python -O.
    if not condition:
        raise VerificationError(message)


def finite(value, *, positive=False):
    return (
        isinstance(value, (float, int))
        and not isinstance(value, bool)
        and math.isfinite(value)
        and (value > 0 if positive else value >= 0)
    )


def key(item):
    return item["scenario"], item["concurrency"], item["warmup"]


def quantiles(rows, field="latency_ms"):
    ordered = sorted(r[field] for r in rows if field in r)
    return {
        f"p{p}": round(ordered[(len(ordered) * p + 99) // 100 - 1], 3)
        if ordered
        else None
        for p in (50, 95)
    }


def reference_metrics(rows, seconds, schema):
    good = [r for r in rows if r["ok"]]
    bad = [r for r in rows if not r["ok"]]
    expected = {
        "attempted": len(rows),
        "succeeded": len(good),
        "failed": len(bad),
        "error_rate": len(bad) / len(rows),
        "wall_seconds": seconds,
        "attempted_per_second": len(rows) / seconds,
        "successful_per_second": len(good) / seconds,
        "latency_ms": {
            name: quantiles(part)
            for name, part in (("all", rows), ("success", good), ("failure", bad))
        },
        "http_status_counts": dict(Counter(str(r.get("http_status")) for r in rows)),
        "error_counts": dict(Counter(r["error"] for r in bad)),
        "retrieval_busy_503": sum(r.get("error") == "RETRIEVAL_BUSY_503" for r in rows),
        "retry_after_counts": dict(
            Counter(r["retry_after"] for r in rows if r.get("retry_after"))
        ),
    }
    if schema >= 2:
        counts = Counter()
        for row in rows:
            counts.update(row.get("http_response_status_counts", {}))
        expected.update(
            http_response_status_counts=dict(counts),
            http_requests_started=sum(r["http_requests"] for r in rows),
            cleanup_http_requests_started=sum(
                r.get("cleanup_http_requests", 0) for r in rows
            ),
            turn_latency_ms=quantiles(good, "turn_latency_ms"),
        )
    return expected


def verify_inputs(result, sha):
    root = Path(__file__).resolve().parents[2]
    for name, expected in result["file_sha256"].items():
        path = PurePosixPath(name)
        require(
            not path.is_absolute()
            and ".." not in path.parts
            and re.fullmatch(r"[0-9a-f]{64}", expected),
            "Invalid input fingerprint",
        )
        # Read only the recorded commit's tracked public inputs, never arbitrary local paths.
        content = subprocess.check_output(
            ["git", "show", f"{sha}:{name}"], cwd=root, stderr=subprocess.DEVNULL
        )
        require(
            hashlib.sha256(content).hexdigest() == expected,
            f"Input hash differs from recorded SHA: {name}",
        )


def verify(directory, sha, require_busy=False, check_inputs=False):
    result = json.loads((directory / "result.json").read_text())
    require(result["success"] is True, "Run did not complete successfully")
    require(re.fullmatch(r"[0-9a-f]{40}", sha), "Expected a full Git SHA")
    require(
        result["head"] == sha == result["source"]["sha"] == result["end_source"]["sha"],
        "SHA mismatch",
    )
    require(
        result["valid_clean_source_evidence"] is True
        and result["source"]["source_dirty"] is False,
        "Dirty source evidence",
    )
    require(result["source"] == result["end_source"], "Source drift")
    require(result["stages"]["cleanup"]["status"] == "PASS", "Cleanup not proven")
    require(
        result["label"] in {"DEV_SMOKE_NOT_RESUME", "RENTAL_MOCK_BASELINE"},
        "Unknown measurement label",
    )
    schema = result.get("schema_version", 1)
    require(schema in (1, 2), "Unsupported schema")
    config = result["config"]
    require(
        (config["requests_per_group"] is None) != (config["admission_seconds"] is None),
        "Invalid stop configuration",
    )
    require(
        finite(config["operation_timeout_seconds"], positive=True),
        "Invalid operation timeout",
    )
    if config["requests_per_group"] is not None:
        require(
            type(config["requests_per_group"]) is int
            and config["requests_per_group"] > 0,
            "Invalid request cap",
        )
    else:
        require(
            finite(config["admission_seconds"], positive=True),
            "Invalid admission window",
        )
    config_hash = hashlib.sha256(
        json.dumps(config, sort_keys=True).encode()
    ).hexdigest()
    require(config_hash == result["config_sha256"], "Config fingerprint mismatch")
    scenarios, levels = config["scenarios"], config["concurrency"]
    require(
        scenarios
        and len(set(scenarios)) == len(scenarios)
        and set(scenarios) <= {"S1", "S2", "S3"},
        "Invalid configured scenarios",
    )
    require(
        levels
        and len(set(levels)) == len(levels)
        and all(type(c) is int and c > 0 for c in levels),
        "Invalid configured concurrency",
    )
    expected = {(s, 1, True) for s in scenarios} | {
        (s, c, False) for s in scenarios for c in levels
    }
    items = result["warmups"] + result["groups"]
    require(
        all(i["warmup"] is True for i in result["warmups"])
        and all(i["warmup"] is False for i in result["groups"]),
        "Warmup partition mismatch",
    )
    require(
        len(items) == len(expected) and {key(i) for i in items} == expected,
        "Incomplete or duplicate configured matrix",
    )
    rows = [
        json.loads(line)
        for line in (directory / "requests.jsonl").read_text().splitlines()
    ]
    require(
        len({r["request_id"] for r in rows}) == len(rows), "Duplicate logical attempts"
    )
    for row in rows:
        require(
            row.get("source_sha") == sha and row.get("label") == result["label"],
            "Raw row SHA/label mismatch",
        )
        require(
            key(row) in expected
            and type(row["warmup"]) is bool
            and type(row["ok"]) is bool,
            "Unexpected raw group/boolean",
        )
        require(finite(row["latency_ms"]), "Nonfinite/negative latency")
        require(row["ok"] or bool(row.get("error")), "Failed attempt has no error")
        require(
            not row["ok"] or not row.get("error"), "Successful attempt has an error"
        )
        if row.get("error") == "RETRIEVAL_BUSY_503":
            require(
                not row["ok"] and row.get("http_status") == 503,
                "Busy error must be a failed HTTP 503",
            )
        if schema >= 2:
            require(row.get("schema_version") == 2, "Mixed row schemas")
            require(
                all(
                    finite(row.get(k))
                    for k in ("wall_latency_ms", "start_offset_ms", "finish_offset_ms")
                ),
                "Missing wall timing",
            )
            require(
                row["finish_offset_ms"] >= row["start_offset_ms"]
                and math.isclose(
                    row["wall_latency_ms"],
                    row["finish_offset_ms"] - row["start_offset_ms"],
                    abs_tol=0.003,
                ),
                "Wall timing mismatch",
            )
            require(
                math.isclose(
                    row["latency_ms"] + row.get("cleanup_ms", 0),
                    row["wall_latency_ms"],
                    abs_tol=0.003,
                ),
                "Cleanup leaked into operation latency",
            )
            require(row.get("cleanup_ok") is not False, "Undrained raw Tutor work")
            require(
                type(row["http_requests"]) is int and row["http_requests"] >= 0,
                "Invalid HTTP sends",
            )
            counts = row.get("http_response_status_counts", {})
            require(
                all(
                    re.fullmatch(r"[1-5][0-9]{2}", k) and type(v) is int and v > 0
                    for k, v in counts.items()
                )
                and sum(counts.values()) <= row["http_requests"],
                "Invalid response counts",
            )
            if row["scenario"] == "S3" and row["ok"]:
                require(
                    row.get("turn_status") == "completed"
                    and finite(row.get("turn_latency_ms"))
                    and row["turn_latency_ms"] <= row["latency_ms"] + 0.003,
                    "Tutor acceptance is not completion",
                )
    observed = 0
    for item in items:
        selected = [r for r in rows if key(r) == key(item)]
        require(bool(selected), "Empty measured group")
        seconds = item["wall_seconds"]
        require(finite(seconds, positive=True), "Invalid wall seconds")
        if item["warmup"]:
            require(len(selected) == 1 and selected[0]["ok"], "Warmup did not pass")
        elif config["requests_per_group"] is not None:
            require(
                len(selected) == config["requests_per_group"], "Request cap mismatch"
            )
        stop = item["stop"]
        require(
            stop
            == {
                "requests": 1 if item["warmup"] else config["requests_per_group"],
                "admission_seconds": None
                if item["warmup"]
                else config["admission_seconds"],
                "timeout_seconds": config["operation_timeout_seconds"],
            },
            "Stop condition mismatch",
        )
        expected_metrics = reference_metrics(selected, seconds, schema)
        observed += len(selected)
        for name, value in expected_metrics.items():
            actual = item[name]
            if isinstance(value, float):
                require(
                    finite(actual)
                    and math.isclose(value, actual, rel_tol=0.0001, abs_tol=0.0001),
                    name,
                )
            else:
                require(actual == value, name)
        require(not item["undrained_tutor"], "Hidden Tutor backlog")
        if schema >= 2:
            require(
                item.get("schema_version") == 2
                and max(r["finish_offset_ms"] for r in selected)
                <= seconds * 1000 + 0.002,
                "Attempt outside group wall window",
            )
            if stop["admission_seconds"] is not None:
                start = item["admission_start_offset_ms"]
                require(
                    finite(start)
                    and all(
                        start <= r["start_offset_ms"] + 0.001
                        and r["start_offset_ms"]
                        <= start + stop["admission_seconds"] * 1000 + 0.001
                        for r in selected
                    ),
                    "Attempt outside admission window",
                )
    require(observed == len(rows), "Unaccounted raw requests")
    if require_busy:
        require(
            any(
                not r["warmup"]
                and r["scenario"] == "S1"
                and r.get("error") == "RETRIEVAL_BUSY_503"
                and r.get("http_status") == 503
                and r.get("retry_after") == "1"
                for r in rows
            ),
            "No genuine direct-retrieval busy 503 with Retry-After: 1 observed",
        )
    if check_inputs:
        verify_inputs(result, sha)
    return {
        "sha": sha,
        "schema_version": schema,
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
    parser.add_argument(
        "--check-inputs",
        action="store_true",
        help="Compare recorded public file hashes with the recorded Git commit",
    )
    args = parser.parse_args()
    print(
        json.dumps(
            verify(args.directory, args.sha, args.require_busy, args.check_inputs)
        )
    )
