"""Aggregate independently supplied judgements; never grade generated text itself."""

import argparse
import hashlib
import json
from pathlib import Path

TURN_KEYS = [f"v18-loop-teaching-smoke:{n}" for n in range(1, 4)]
CANDIDATE = "16a094317ba06b3c1932280c7dbb15a07d47200dc74ed8e08e25465e10549ae9"
PACKET = "ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e"
POINTS = {
    key: [f"{i}.{n}" for n in range(1, count + 1)]
    for i, (key, count) in enumerate(zip(TURN_KEYS, [5, 3, 4], strict=True), 1)
}


def adjudicate(review, outcomes_raw):
    if review["candidate_sha256"] != CANDIDATE or review["packet_sha256"] != PACKET:
        raise ValueError("FROZEN_CANDIDATE_AND_PACKET_REQUIRED")
    outcomes = json.loads(outcomes_raw)
    if len(outcomes) != 3 or [r["turn_key"] for r in outcomes] != TURN_KEYS:
        raise ValueError("ALL_THREE_ORDERED_POSITIONS_REQUIRED")
    if review["outcomes_sha256"] != hashlib.sha256(outcomes_raw).hexdigest():
        raise ValueError("REVIEW_OUTPUT_BINDING_REQUIRED")
    if [t["turn_key"] for t in review["turns"]] != TURN_KEYS:
        raise ValueError("ALL_THREE_REVIEW_POSITIONS_REQUIRED")
    judgements = []
    for turn in review["turns"]:
        if [p["id"] for p in turn["points"]] != POINTS[turn["turn_key"]]:
            raise ValueError("ALL_ORIGINAL_REQUIRED_POINTS_REQUIRED")
        if not turn["claims"]:
            judgements.append("UNRESOLVED")
        for item in turn["points"] + turn["claims"]:
            status = item["status"]
            if status not in {"PASS", "FAIL", "UNRESOLVED", "NOT_RUN"}:
                raise ValueError("INVALID_JUDGEMENT")
            if status in {"PASS", "FAIL"} and (
                not item["reason"] or not item["evidence"]
            ):
                raise ValueError("REASON_AND_EVIDENCE_REQUIRED")
            judgements.append(status)
    reviewer = review["reviewer"]
    independent = (
        bool(reviewer["name"])
        and reviewer["implementation_contributor"] is False
        and bool(reviewer["independence_attested_by"])
    )
    mechanical = all(t["status"] == "completed" for t in outcomes)
    if not mechanical:
        verdict = "NOT_RUN_ENGINEERING_STOP"
    elif "FAIL" in judgements:
        verdict = "FAIL"
    elif not independent or any(s != "PASS" for s in judgements):
        verdict = "UNRESOLVED"
    else:
        verdict = "PASS"
    return {
        "quality": verdict,
        "scheduled": 3,
        "independence_attested": independent,
        "semantic_scoring": "EXTERNAL_JUDGEMENTS_NOT_AUTOMATIC_MODEL_GRADING",
        "release_or_expansion_authorized": False,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--outcomes", type=Path, required=True)
    args = parser.parse_args()
    result = adjudicate(
        json.loads(args.review.read_bytes()), args.outcomes.read_bytes()
    )
    print(json.dumps(result, indent=2))
    return 0 if result["quality"] == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
