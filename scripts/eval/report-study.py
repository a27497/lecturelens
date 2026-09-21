#!/usr/bin/env python3
"""Summarize every frozen evaluation trial, including failures; require explicit semantic reviews."""

import argparse
import hashlib
import json
import math
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def validate_cohort(rows, dataset_digest):
    assert all(row.get("dataset_sha256") == dataset_digest for row in rows), "Dataset changed"
    assert all(row.get("runtime") for row in rows), "Missing runtime identity"
    assert len({json.dumps(row["runtime"], sort_keys=True) for row in rows}) <= 1, (
        "Mixed implementations/models/budgets cannot form one evaluation cohort"
    )


def summarize(cases, rows, reviews):
    expected = {case["id"]: case for case in cases}
    assert len({row["case_id"] for row in rows}) == len(rows), "Duplicate trials in one label"
    assert all(row["case_id"] in expected for row in rows)
    times = sorted(row["elapsed_seconds"] for row in rows)
    valid, on_time, semantic, insufficient, provenance = 0, 0, 0, 0, True
    no_serious_unsupported = True
    components = {key: 0 for key in ["grounded", "answers_correct", "questions_distinct"]}
    serious = 0
    details = []
    for row in rows:
        case = expected[row["case_id"]]
        artifact = row.get("artifact") or {}
        success = row["run"]["status"] == "succeeded"
        is_insufficient = case["expected_outcome"] == "insufficient_evidence"
        structure = success and (
            artifact.get("kind") == "insufficient_evidence"
            and not artifact.get("questions")
            and not artifact.get("citations")
            if is_insufficient
            else len(artifact.get("questions", [])) == 2 and bool(artifact.get("citations"))
        )
        review = reviews.get(row["case_id"], {})
        reviewed = bool(review.get("reviewer")) and bool(review.get("reason"))
        no_serious_unsupported &= not success or review.get("serious_unsupported") is False
        serious += bool(success and review.get("serious_unsupported") is True)
        quality = reviewed and all(
            review.get(key) is True for key in ["grounded", "answers_correct", "questions_distinct"]
        )
        valid += bool(structure)
        on_time += bool(structure and row["elapsed_seconds"] <= 90)
        semantic += bool(not is_insufficient and structure and quality)
        if not is_insufficient and structure and reviewed:
            for key in components:
                components[key] += review.get(key) is True
        insufficient += bool(is_insufficient and structure and reviewed and review.get("grounded") is True)
        provenance &= not success or row["provenance_valid"]
        details.append(
            {
                "case_id": row["case_id"],
                "status": row["run"]["status"],
                "error_code": row["run"].get("error_code"),
                "elapsed_seconds": row["elapsed_seconds"],
                "structure_valid": structure,
                "semantic_review_pass": bool(
                    quality if not is_insufficient else reviewed and review.get("grounded") is True
                ),
                "reviewer": review.get("reviewer"),
                "reason": review.get("reason"),
                "serious_unsupported": review.get("serious_unsupported"),
            }
        )
    total = len(cases)
    supported = sum(case["expected_outcome"] == "practice" for case in cases)
    absent = total - supported
    gates = {
        "complete": len(rows) == total,
        "structure": valid >= math.ceil(total * 0.9),
        "provenance": provenance,
        "insufficient": insufficient == absent,
        "semantic": semantic >= math.ceil(supported * 0.9),
        "no_serious_unsupported": no_serious_unsupported,
        "latency": on_time >= math.ceil(total * 0.9),
    }
    measured_calls = [
        event["payload"]
        for row in rows
        for event in row.get("events", [])
        if event["event_type"] in {"model_finished", "model_failed"}
    ]
    total_model_calls = sum(row["run"].get("model_calls", 0) for row in rows)
    return {
        "expected_cases": total,
        "observed_cases": len(rows),
        "structure_pass": valid,
        "semantic_supported_pass": semantic,
        "supported_review_components": components,
        "serious_unsupported_cases": serious,
        "insufficient_pass": insufficient,
        "successful_within_90s": on_time,
        "p50_all_seconds": times[math.ceil(len(times) * 0.5) - 1] if times else None,
        "p95_all_seconds": times[math.ceil(len(times) * 0.95) - 1] if times else None,
        "quantile_method": "nearest rank, all outcomes",
        "status_counts": dict(Counter(row["run"]["status"] for row in rows)),
        "model_calls": total_model_calls,
        "tool_calls": sum(row["run"].get("tool_calls", 0) for row in rows),
        "measured_model_calls": len(measured_calls),
        "model_calls_without_complete_usage": total_model_calls
        - sum("prompt_tokens" in call and "completion_tokens" in call for call in measured_calls),
        "reported_prompt_tokens": sum(
            call["prompt_tokens"] for call in measured_calls if "prompt_tokens" in call
        )
        if any("prompt_tokens" in call for call in measured_calls)
        else None,
        "reported_completion_tokens": sum(
            call["completion_tokens"] for call in measured_calls if "completion_tokens" in call
        )
        if any("completion_tokens" in call for call in measured_calls)
        else None,
        "gates": gates,
        "passed": all(gates.values()),
        "cases": details,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=ROOT / "eval/study-v1/cases.json")
    args = parser.parse_args()
    dataset = args.cases.read_bytes()
    cases = json.loads(dataset)["cases"]
    rows = [json.loads(line) for line in args.results.read_text().splitlines()]
    digest = hashlib.sha256(dataset).hexdigest()
    validate_cohort(rows, digest)
    reviews = json.loads(args.reviews.read_text())
    result = summarize(cases, rows, reviews)
    result["dataset_sha256"] = digest
    result["runtime"] = rows[0]["runtime"] if rows else None
    result["splits"] = {
        split: summarize(
            [case for case in cases if case["split"] == split],
            [row for row in rows if row["split"] == split],
            reviews,
        )
        for split in ["dev", "holdout"]
    }
    result["outcomes"] = {
        kind: summarize(
            [case for case in cases if case["expected_outcome"] == kind],
            [row for row in rows if row["expected_outcome"] == kind],
            reviews,
        )
        for kind in ["practice", "insufficient_evidence"]
    }
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {key: value for key, value in result.items() if key not in ["cases", "splits"]},
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
