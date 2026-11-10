"""Model-blind per-turn review package. This module never calls an AI."""

import hashlib
import json

REFERENCE = {"loop": "python_trace", "sql": "sqlite", "shell": "shell", "git": "git"}


def packet_hash(packet):
    return hashlib.sha256(
        json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()


def make_packet(case, turn, references):
    context = json.loads(turn["checkpoint"]["messages"][-1]["content"])
    family = case["id"].rsplit("-", 1)[0]
    packet = {
        "case_id": case["id"],
        "question": case["question"],
        "socratic": case["socratic"],
        "expected_outcome": case["expected_outcome"],
        "prior_dialogue": context["dialogue"],
        "current_evidence": context["current_evidence"],
        "answer": turn["answer"],
        "outcome": turn["outcome"],
        "criteria": {str(i): rule for i, rule in enumerate(case["required_checks"], 1)},
        "reference": references[REFERENCE[family]],
    }
    packet["packet_sha256"] = packet_hash(packet)
    return packet


def reviewed_pass(packet, reviews):
    if not isinstance(reviews, list) or len(reviews) != 2:
        return False
    if any(not isinstance(review, dict) for review in reviews):
        return False
    allowed_ids = {item["evidence_id"] for item in packet["current_evidence"]}
    models, contexts = set(), set()
    for review in reviews:
        model, context = review.get("model"), review.get("independent_context")
        if (
            not isinstance(model, str)
            or not model.strip()
            or model in models
            or not isinstance(context, str)
            or not context.strip()
            or context in contexts
            or review.get("packet_sha256") != packet["packet_sha256"]
            or review.get("severe_error") is not False
            or review.get("confidence") != "HIGH"
        ):
            return False
        models.add(model)
        contexts.add(context)
        checks = review.get("checks")
        if not isinstance(checks, dict) or set(checks) != set(packet["criteria"]):
            return False
        if any(not supported(item) for item in checks.values()):
            return False
        claims = review.get("claim_checks")
        if not isinstance(claims, list):
            return False
        if not claims and not (
            packet["socratic"] or packet["expected_outcome"] == "insufficient_evidence"
        ):
            return False
        if any(
            not supported(claim)
            or not isinstance(claim.get("claim"), str)
            or not claim["claim"].strip()
            or claim.get("evidence_id") not in allowed_ids
            or f"[{claim['evidence_id']}]" not in packet["answer"]
            for claim in claims
        ):
            return False
        if not supported(review.get("citation_and_teaching_check")):
            return False
    return packet["outcome"] == packet["expected_outcome"]


def supported(item):
    return (
        isinstance(item, dict)
        and item.get("verdict") == "PASS"
        and isinstance(item.get("basis"), str)
        and bool(item["basis"].strip())
    )
