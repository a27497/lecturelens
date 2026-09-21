"""Combine frozen retrieval with source-based semantic reviews; no model calls or label edits."""

import argparse
import json
import statistics
from pathlib import Path

from .core import STRATEGIES, digest, verify_freeze
from .run import write_json


def answer_metrics(rows, cases, reviews):
    expected = {(cid, strategy) for cid in cases for strategy in STRATEGIES}
    keyed = {(r["case_id"], r["strategy"]): r for r in rows}
    checked = {(r["case_id"], r["strategy"]): r for r in reviews}
    if (
        len(rows) != len(keyed)
        or len(reviews) != len(checked)
        or set(keyed) != expected
        or set(checked) != expected
    ):
        raise ValueError("Incomplete or duplicate cohort/reviews")
    scored = []
    for key, row in keyed.items():
        review = checked[key]
        if review["response_sha256"] != row.get("response_sha256"):
            raise ValueError("Review belongs to another response")
        flags = ("answer_correct", "all_claims_supported", "all_required_aspects")
        if any(type(review.get(flag)) is not bool for flag in flags) or not review.get("reason"):
            raise ValueError("Missing semantic review")
        case = cases[key[0]]
        answer = row.get("answer")
        valid = bool(answer) and "error_type" not in row
        refused = answer["refused"] if valid else None
        supported = review["all_claims_supported"]
        gar = valid and not refused and all(review[flag] for flag in flags)
        refusal = valid and (
            (case["answerable"] and not refused) or (not case["answerable"] and refused and supported)
        )
        scored.append(
            {
                "case_id": key[0],
                "strategy": key[1],
                "answerable": case["answerable"],
                "protocol_valid": valid,
                "refused": refused,
                "grounded_answer_pass": bool(gar) if case["answerable"] else None,
                "refusal_classification_pass": bool(refusal),
                "response_sha256": row.get("response_sha256"),
                "review": review,
            }
        )
    summary = {}
    for strategy in STRATEGIES:
        selected = [r for r in scored if r["strategy"] == strategy]
        positive = [r for r in selected if r["answerable"]]
        negative = [r for r in selected if not r["answerable"]]
        summary[strategy] = {
            "grounded_answer_rate": statistics.mean(r["grounded_answer_pass"] for r in positive),
            "grounded_answers": sum(r["grounded_answer_pass"] for r in positive),
            "answerable_count": len(positive),
            "refusal_accuracy": statistics.mean(r["refusal_classification_pass"] for r in selected),
            "refusal_correct": sum(r["refusal_classification_pass"] for r in selected),
            "total_count": len(selected),
            "no_answer_refusal_rate": statistics.mean(r["refusal_classification_pass"] for r in negative),
            "no_answer_refusal_correct": sum(r["refusal_classification_pass"] for r in negative),
            "no_answer_count": len(negative),
            "false_refusals": sum(r["refused"] is True for r in positive),
            "protocol_errors": sum(not r["protocol_valid"] for r in selected),
        }
    return summary, scored


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--retrieval", type=Path, required=True)
    parser.add_argument("--answers", type=Path, required=True)
    parser.add_argument("--reviews", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    verify_freeze(args.dataset)
    completed = json.loads((args.answers / "complete.json").read_text())
    if digest(args.answers / "answers.jsonl") != completed["answers_sha256"]:
        raise ValueError("Modified answers")
    answer_identity = json.loads((args.answers / "identity.json").read_text())
    retrieval_complete = json.loads((args.retrieval / "complete.json").read_text())
    if digest(args.retrieval / "summary.json") != retrieval_complete["summary_sha256"]:
        raise ValueError("Modified retrieval summary")
    if (
        answer_identity["freeze_sha256"] != digest(args.dataset / "freeze.json")
        or answer_identity["retrieval_sha256"] != digest(args.retrieval / "retrieval.jsonl")
        or retrieval_complete["retrieval_sha256"] != answer_identity["retrieval_sha256"]
    ):
        raise ValueError("Mixed candidates or retrieval cohorts")
    rows = [json.loads(line) for line in (args.answers / "answers.jsonl").read_text().splitlines()]
    cases = {c["id"]: c for c in json.loads((args.dataset / "cases.json").read_text())["cases"]}
    reviews = json.loads(args.reviews.read_text())
    summary, scored = answer_metrics(rows, cases, reviews["reviews"])
    retrieval = json.loads((args.retrieval / "summary.json").read_text())
    args.output.mkdir(parents=True, exist_ok=False)
    write_json(args.output / "metrics.json", {s: retrieval[s] | summary[s] for s in STRATEGIES})
    write_json(args.output / "answer-scores.json", scored)
    write_json(
        args.output / "answer-bad-cases.json",
        [r for r in scored if not r["refusal_classification_pass"] or r["grounded_answer_pass"] is False],
    )
    write_json(
        args.output / "identity.json",
        {
            "freeze_sha256": digest(args.dataset / "freeze.json"),
            "answers_sha256": completed["answers_sha256"],
            "reviews_sha256": digest(args.reviews),
            "review_method": reviews["method"],
            "retrieval_sha256": answer_identity["retrieval_sha256"],
        },
    )


if __name__ == "__main__":
    main()
