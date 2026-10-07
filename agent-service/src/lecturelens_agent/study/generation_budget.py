"""Protect a follow-up's rejection/repair path before proposing its first draft.

The pricing specimens are never evidence or model judgments. Full current
sources and the maximum Atomic slots are priced, with no speculative reuse.
An over-sized actual request fails closed before an external review call.
"""

import json
from copy import deepcopy
from datetime import datetime, timedelta, timezone

from .atomic import MAX_CLAIMS, AtomicAssessment, atomic_claims
from .atomic_delta import basis
from .context import aliases_in, build_messages, compact_json
from .provider import decision_schemas
from .quality import review_messages
from .request_budget import request_cost
from .review_budget import FINISH_SECONDS, FINISH_TOKENS, REVIEW_CALLS, REVIEW_SECONDS, margin, priced
from .semantic import review_goal


def limit_messages(messages, limit, claims, citations, title):
    result = deepcopy(messages)
    body = json.loads(result[-1]["content"])
    body["generation_max_chars"] = limit
    body["generation_max_claims"] = claims
    body["generation_max_citations"] = citations
    body["generation_max_title"] = title
    result[-1]["content"] = compact_json(body)
    return result


def ceiling(
    provider, messages, semantic, evidence, history, limit, claims=MAX_CLAIMS, citations=8, title=120
):
    from .revision import freeze_revision
    from .runtime import bind_revision_review, price_review

    # 24 spans, maximum title, all offered sources and no reused claim. Quote
    # escaping bounds ordinary UTF-8 prose as well as JSON string punctuation.
    width = max(1, (limit - claims) // claims)
    text = ",".join("𐀀" * width for _ in range(claims))
    text += "𐀀" * (limit - len(text))
    # Citation completion can add observed neighbours. Price the full offered
    # source closure rather than assuming the initial list remains unchanged.
    largest = sorted(evidence, key=lambda e: len(e["text"][:1200].encode()), reverse=True)
    candidate = dict(
        kind="explanation",
        title="𐀀" * title,
        explanation=text,
        evidence_ids=[e["evidence_id"] for e in largest],
        questions=[],
    )
    initial = review_messages(
        review_goal(semantic, "explanation"),
        candidate,
        evidence,
        structured_support=True,
        check_goal=True,
        semantic=semantic,
    )
    body = json.loads(initial[-1]["content"])
    canonical = dict(zip(body["candidate"]["evidence_ids"], candidate["evidence_ids"], strict=True))
    proof = aliases_in(basis(body).model_dump(), canonical)
    quality = dict(
        accepted=False,
        source="model_review",
        issues=["unsupported_explanation"],
        feedback="𐀀" * 400,
        atomic_basis=proof,
        atomic_assessments=[
            AtomicAssessment(**c, supported=False, model_supported=False, evidence_ids=[]).model_dump()
            for c in atomic_claims(text)
        ],
    )
    rejected = [
        *history,
        dict(
            tool="create_explanation",
            arguments={k: candidate[k] for k in ("title", "explanation", "evidence_ids")},
            result={"quality": quality},
        ),
    ]
    revision, _ = build_messages(
        messages[0]["content"],
        semantic["resolved_goal"],
        evidence,
        rejected,
        semantic.get("previous_turns", []),
        semantic=semantic,
    )
    transaction = freeze_revision(rejected, semantic, evidence)
    final = review_messages(
        review_goal(semantic, "explanation"),
        candidate,
        evidence,
        structured_support=True,
        check_goal=True,
        semantic=semantic,
    )
    bind_revision_review(final, transaction, evidence)

    # All partitioned text together is bounded by the answer length. Replacing
    # it with escaped quotes gives a larger wire representation without turning
    # this artificial specimen into a valid answer or changing any verifier.
    def escape_bound(value):
        if isinstance(value, dict):
            return {k: escape_bound(v) for k, v in value.items()}
        if isinstance(value, list):
            return [escape_bound(v) for v in value]
        return value.replace("𐀀", '"') if isinstance(value, str) else value

    for bundle in (initial, revision, final):
        for m in bundle:
            if m["role"] != "system" and isinstance(m.get("content"), str):
                m["content"] = compact_json(escape_bound(json.loads(m["content"])))
    initial_cost = price_review(provider, initial)["cost"]
    final_estimate = price_review(provider, final)
    revision_cost = request_cost(provider, "decision", revision, decision_schemas(revision), 900)["cost"]
    # Unknown guard names/goal feedback and source-bound fact substitutions
    # are bounded by these extra slots, not charged as actual model requests.
    revision_cost += 1024
    final_tokens = priced({"model_calls": 2}, final_estimate)["tokens"]
    return dict(
        first_review=initial_cost + margin(initial_cost),
        revision=revision_cost,
        final_review=final_tokens,
        finish=FINISH_TOKENS,
        final_estimate=final_estimate,
        future_tokens=initial_cost + margin(initial_cost) + revision_cost + final_tokens + FINISH_TOKENS,
        future_calls=4,
        max_chars=limit,
        max_claims=claims,
        max_citations=citations,
        max_title=title,
    )


def choose(provider, messages, semantic, evidence, history, row):
    from .store import StudyError

    for limit, claims, citations, title in (
        (1500, 24, 8, 120),
        (600, 12, 8, 120),
        (300, 8, 8, 120),
        (300, 8, 2, 120),
        (160, 8, 2, 120),
        (300, 8, 2, 40),
        (160, 8, 2, 40),
        (300, 8, 1, 120),
        (160, 8, 1, 40),
        (120, 8, 2, 40),
        (110, 8, 2, 40),
    ):
        bounded = limit_messages(messages, limit, claims, citations, title)
        allocation = ceiling(provider, bounded, semantic, evidence, history, limit, claims, citations, title)
        cost = request_cost(provider, "decision", bounded, decision_schemas(bounded), 900)["cost"]
        optional_generation = cost if not history else 0
        if row["reserved_tokens"] + cost + allocation["future_tokens"] + optional_generation <= 64000:
            return bounded, dict(
                allocation,
                generation_cost=cost,
                total=row["reserved_tokens"] + cost + allocation["future_tokens"],
            )
    raise StudyError("FINAL_REVIEW_BUDGET_UNAVAILABLE")


def check_path(row, path, tokens):
    from .store import StudyError

    future = path["future_tokens"]
    calls = path["future_calls"]
    if path["stage"] == "generation":
        next_stage = "first_review"
    elif path["stage"] == "first_review":
        if tokens > path["first_review"]:
            raise StudyError("GENERATION_REVIEW_ENVELOPE_EXCEEDED")
        future -= path["first_review"]
        calls -= 1
        next_stage = "reviewed"
    else:
        raise StudyError("GENERATION_PATH_PROTOCOL_STOP")
    if (
        (datetime.fromisoformat(path["preparation_deadline"]) - datetime.now(timezone.utc)).total_seconds()
        <= 0
        or row["model_calls"] + 1 + calls > 6
        or row["reserved_tokens"] + tokens + future > 64000
    ):
        raise StudyError("FINAL_REVIEW_BUDGET_UNAVAILABLE")
    return {**path, "stage": next_stage, "future_tokens": future, "future_calls": calls}


def time_allocation(row, allocation, now=None):
    from .store import StudyError

    now = now or datetime.now(timezone.utc)
    available = (row["deadline"] - now).total_seconds() - FINISH_SECONDS
    if available <= 0:
        raise StudyError("FINAL_REVIEW_BUDGET_UNAVAILABLE")
    # This path contains generation, first verification, revision, and two
    # final verification requests. A fixed 60-second final reserve starves the
    # first verification. Split the remaining window across all five requests;
    # unused preparation time stays available to final verification, while its
    # correction still has a separate slot and recovery retains both cutoffs.
    final_seconds = min(REVIEW_SECONDS, available * REVIEW_CALLS / (allocation["future_calls"] + 1))
    return {
        "final_review_seconds": final_seconds,
        "preparation_deadline": (
            row["deadline"] - timedelta(seconds=final_seconds + FINISH_SECONDS)
        ).isoformat(),
    }
