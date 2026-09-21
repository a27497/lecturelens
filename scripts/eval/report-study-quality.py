#!/usr/bin/env python3
"""Apply existing quality criteria to fixed-Evidence replay; never certify the full L2 gate."""

import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("study_report", Path(__file__).with_name("report-study.py"))
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--cases", type=Path, default=ROOT / "eval/study-v2/cases.json")
    args = parser.parse_args()
    dataset = args.cases.read_bytes()
    rows = [json.loads(line) for line in args.results.read_text().splitlines()]
    assert rows, "Empty cohort"
    digest = hashlib.sha256(dataset).hexdigest()
    for row in rows:
        assert row["identity"]["protocol"] in {
            "real-model-pg-runtime-fixed-evidence-replay",
            "managed-real-provider-development-fixed-evidence",
        }
        if row["identity"]["protocol"] == "managed-real-provider-development-fixed-evidence":
            assert all(case.get("split") == "development" for case in json.loads(dataset)["cases"])
        row["dataset_sha256"] = row["identity"]["dataset_sha256"]
        row["runtime"] = row["identity"]
        evidence = {e["evidence_id"]: e for e in row["evidence"]}
        artifact = row.get("artifact") or {}
        citations = artifact.get("citations", [])
        refs = set(artifact.get("evidence_ids", []))
        for question in artifact.get("questions", []):
            refs.update(question["evidence_ids"])
        row["provenance_valid"] = refs <= {e["evidence_id"] for e in citations} and all(
            e == evidence.get(e["evidence_id"]) for e in citations
        )
    report.validate_cohort(rows, digest)
    reviews = json.loads(args.reviews.read_text())
    result = report.summarize(json.loads(dataset)["cases"], rows, reviews)
    result.update(
        {
            "dataset_sha256": digest,
            "runtime": rows[0]["identity"],
            "results_sha256": hashlib.sha256(args.results.read_bytes()).hexdigest(),
            "reviews_sha256": hashlib.sha256(args.reviews.read_bytes()).hexdigest(),
            "full_l2_gate_assessed": False,
            "scope": "Fixed-Evidence replay pilot; real provider, production Python runtime and isolated PG. No ingestion, dense retrieval, Java auth or browser acceptance.",
            "assessment": "Source-based Codex AI review, not blind and not a human gold standard. Runtime model review is not used as semantic scoring.",
            "quality_checks": sum(e["event_type"] == "quality_checked" for r in rows for e in r["events"]),
            "rejected_candidates": sum(
                e["event_type"] == "quality_checked" and e["payload"]["accepted"] is False
                for r in rows
                for e in r["events"]
            ),
            "runs_completed_after_rejection": sum(
                r["run"]["status"] == "succeeded"
                and any(
                    e["event_type"] == "quality_checked" and e["payload"]["accepted"] is False
                    for e in r["events"]
                )
                for r in rows
            ),
            "review_model_calls_started": sum(
                e["event_type"] == "model_started" and e["payload"].get("purpose") == "review"
                for r in rows
                for e in r["events"]
            ),
        }
    )
    result["usage_by_purpose"] = {}
    for purpose in ["decision", "review"]:
        started = [
            e["payload"]
            for r in rows
            for e in r["events"]
            if e["event_type"] == "model_started" and e["payload"].get("purpose") == purpose
        ]
        finished = [
            e["payload"]
            for r in rows
            for e in r["events"]
            if e["event_type"] == "model_finished" and e["payload"].get("purpose") == purpose
        ]
        failed = [
            e["payload"]
            for r in rows
            for e in r["events"]
            if e["event_type"] == "model_failed" and e["payload"].get("purpose") == purpose
        ]
        measured = finished + failed
        result["usage_by_purpose"][purpose] = {
            "calls_started": len(started),
            "calls_finished": len(finished),
            "calls_failed": len(failed),
            "known_prompt_tokens": sum(e.get("prompt_tokens", 0) for e in measured),
            "known_completion_tokens": sum(e.get("completion_tokens", 0) for e in measured),
            "calls_without_complete_usage": len(started)
            - sum("prompt_tokens" in e and "completion_tokens" in e for e in measured),
        }
    with args.output.open("x") as output:
        output.write(json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    print(
        json.dumps(
            {
                k: result[k]
                for k in ["status_counts", "semantic_supported_pass", "insufficient_pass", "passed"]
            }
        )
    )


if __name__ == "__main__":
    main()
