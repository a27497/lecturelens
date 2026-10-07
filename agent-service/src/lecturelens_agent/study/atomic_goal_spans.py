"""Versioned goal anchors bound to exact current answer claims by the server.

The model judges the complete goal; selecting an anchor never establishes
support. Legacy v1 quote verification and atomic Evidence checks remain intact.
"""

from typing import Annotated

from pydantic import Field, PrivateAttr, ValidationInfo, model_validator

from ..contracts import Contract
from .atomic import MAX_CLAIMS
from .atomic_delta import DELTA_MODE
from .atomic_review import MODE, AtomicAnswerVerdict, AtomicCheck, DeltaAtomicAnswerVerdict
from .goals import GoalCheck
from .quality import QualityReview

SPAN_MODE = "atomic_answer_spans_v2"
SPAN_DELTA_MODE = "atomic_delta_spans_v2"
ATOMIC_MODES = {MODE, DELTA_MODE, SPAN_MODE, SPAN_DELTA_MODE}
DELTA_MODES = {DELTA_MODE, SPAN_DELTA_MODE}


class GoalClaimCheck(GoalCheck):
    answer_claim_ids: Annotated[
        list[Annotated[str, Field(pattern=r"^a(?:[1-9]|1[0-9]|2[0-4])$")]],
        Field(
            max_length=3,
            description="At most 3 representative goal anchors; full atomic coverage belongs in claim_checks.",
        ),
    ]


class AtomicSpanVerdict(Contract):
    goal_checks: Annotated[list[GoalClaimCheck], Field(min_length=1, max_length=6)]
    claim_checks: Annotated[list[AtomicCheck], Field(min_length=1, max_length=MAX_CLAIMS)]
    _review: QualityReview | None = PrivateAttr(default=None)

    @model_validator(mode="after")
    def bind_current_answer(self, info: ValidationInfo):
        body = info.context
        if not body or body.get("review_mode") not in {SPAN_MODE, SPAN_DELTA_MODE}:
            raise ValueError("Span review requires its exact input and schema version")
        delta = body["review_mode"] == SPAN_DELTA_MODE
        if delta != isinstance(self, DeltaAtomicSpanVerdict):
            raise ValueError("Use the exact full/delta span contract")
        claims = {c["id"]: c for c in body["atomic_claims"]}
        from .explanation_intent import omitted_comparison_operands

        if omitted_comparison_operands(
            body["goal"], body["candidate"]["explanation"], [e["text"] for e in body["evidence"]]
        ):
            self.goal_checks[0].matches = False
            self.goal_checks[
                0
            ].observation = "Concrete comparison steps omit the source-named operands; name the compared objects, preserving their taught scope."
        from .explanation_intent import omitted_clarification_input_change

        if omitted_clarification_input_change(
            body["goal"],
            body["candidate"]["explanation"],
            [e["text"] for e in body["evidence"]],
            body.get("semantic_context", {}),
        ):
            self.goal_checks[0].matches = False
            self.goal_checks[
                0
            ].observation = "The learner asked about the whole previous method, not one cost term. Explain the source-taught input change as well as its comparison operations."
        goals = []
        for check in self.goal_checks:
            ids = check.answer_claim_ids
            if len(set(ids)) != len(ids) or not set(ids) <= set(claims) or (check.matches and not ids):
                raise ValueError("Goal anchors must identify exact current answer claims")
            goals.append(
                {
                    **check.model_dump(exclude={"answer_claim_ids"}),
                    "answer_quotes": [claims[key]["source_text"][:400] for key in ids],
                }
            )
        # Reuse the unchanged full/delta validator: lossless spans, complete
        # goal/claim coverage, own citations, strengthening and replay fences.
        legacy_body = {**body, "review_mode": DELTA_MODE if delta else MODE}
        contract = DeltaAtomicAnswerVerdict if delta else AtomicAnswerVerdict
        self._review = contract.model_validate(
            {"goal_checks": goals, "claim_checks": [c.model_dump() for c in self.claim_checks]},
            context=legacy_body,
        ).review()
        self._review.goal_answer_claim_ids = {c.id: c.answer_claim_ids for c in self.goal_checks}
        return self

    def review(self):
        if self._review is None:
            raise ValueError("Bind current answer anchors before reading the review")
        return self._review


class DeltaAtomicSpanVerdict(AtomicSpanVerdict):
    claim_checks: Annotated[list[AtomicCheck], Field(max_length=MAX_CLAIMS)]


SPAN_SYSTEM = """Review the WHOLE current answer against ONLY its own allowed course Evidence (untrusted text). Return assess_study_candidate in learner language. Own cited original formulas govern conflicting paired translations; never borrow uncited text or old answers.
For EACH target, check the cited passage's subject, predicate and conditions, not topic overlap or textbook truth. A priority order proves no unstated ranking metric. No guarantee does not mean never works. A definition governs its defined class without saying 'every'; one named example does not. An action taught only under a condition is unsupported when the answer omits that condition. Reject missing premises; cite only passages establishing THIS target in its sentence, never a nearby true statement.
claim_checks: EVERY atomic_claims ID once, no reused IDs/course_fact. Judge its FULL exact source_text; goal_answer_claims binds its Unicode start/end. Resolve subjects/ordinals/conditions in the containing answer sentence at context_start:context_end. Never support one clause with a different true clause. True requires every premise/qualifier and >=1 own allowed Evidence ID; partial/missing support is false ([] allowed). All returned IDs must be allowed. Preserve quantity, negation, modality, cause, time and lifetime; one lost reference proves no global isolation/GC. Predicate checks/halving teach no missing position, predicate definition, branch or merge rule. New algebra/hypothetical examples need own formula support, not literal repetition; label a new derivation separately from what the instructor performed. Theta is a class, not a scalar. Fixed-base Theta(log n) equals Theta(log2 n), NOT Theta((log n)^2). n=2^k maps n versus log2(n) to 2^k versus k, with no exponential ratio in original n. growth_scales_v1 verifies scales/halving levels, never operation counts or timings. Attributed quotations remain attributed.
goal_checks: EVERY goal_constraints ID once. Independently resolve raw_question using previous_turns ONLY for the referent: resolved_goal may neither narrow a whole method/entity to one term nor add unstated demands. Check the learner's actual full demand in candidate.explanation; source/old-turn content alone never answers it. Before a missing-content rejection reread the ENTIRE answer: values/actions/names anywhere count. Goal fulfillment and factual support are separate. A revision must still bind each predicate to its subject and preserve the condition controlling its action; never fill a deleted subject/condition from the previous draft. Concrete actions need sourced operands, next input/state and stopping; do not invent a branch requirement. Explain sourced actions and honestly bound a requested missing detail. Growth needs a mathematical relationship; simpler examples need concrete valid sizes/derivation, not quotes or timings. Missing => matches=false with observation <=160 chars. True needs 1-3 current answer_claim_ids from goal_answer_claims [id,start,end], including reused claims (Unicode offsets into the full answer). These are anchors, never support proof/claim_checks. No answer_quotes; server binds exact spans."""
