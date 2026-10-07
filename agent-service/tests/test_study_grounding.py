"""Mechanics for semantic-scope review and revision binding, not model quality."""

import copy
import json

import pytest
from test_study_atomic import judgment
from test_study_delta import NARROWED, delta_plan, initial_review, input_body
from test_study_revision import frozen_history

from lecturelens_agent.study.atomic import AtomicAssessment, atomic_claims
from lecturelens_agent.study.atomic_delta import digest
from lecturelens_agent.study.atomic_goal_spans import AtomicSpanVerdict
from lecturelens_agent.study.freeze_certification import certify_assessments
from lecturelens_agent.study.ledger import facts_from_review
from lecturelens_agent.study.quality import review_messages
from lecturelens_agent.study.revision import UnfulfilledGoal, assemble_revision, freeze_revision


@pytest.mark.parametrize(
    "answer,source",
    [
        ("Each valid ticket contains a code.", "A valid ticket is defined as a ticket containing a code."),
        ("0/1背包对每个物品只能整件取或不取。", "0/1背包意味着物品整件取或不取。"),
    ],
)
def test_implicit_definition_quantifier_requires_model_support_not_a_literal_each(answer, source):
    body = json.loads(
        review_messages(
            "Explain the definition.",
            dict(kind="explanation", title="Rule", explanation=answer, evidence_ids=["own"]),
            [dict(evidence_id="own", text=source)],
        )[-1]["content"]
    )
    checks = judgment(body)
    assert AtomicSpanVerdict.model_validate(checks, context=body).review().issues == []
    checks["claim_checks"][0].update(supported=False, evidence_ids=[])
    if checks["claim_checks"][0].get("relation"):
        checks["claim_checks"][0]["relation"]["grounds"] = []
    assert "unsupported_explanation" in AtomicSpanVerdict.model_validate(checks, context=body).review().issues


@pytest.mark.parametrize("answer", ["Every ticket contains a code.", "每个票据都有代码。"])
def test_explicit_possible_scope_cannot_certify_a_universal_even_with_true_model_check(answer):
    body = json.loads(
        review_messages(
            "Explain the tickets.",
            dict(kind="explanation", title="Tickets", explanation=answer, evidence_ids=["own"]),
            [dict(evidence_id="own", text="Some tickets may contain a code.")],
        )[-1]["content"]
    )
    review = AtomicSpanVerdict.model_validate(judgment(body), context=body).review()
    assert "unsupported_explanation" in review.issues
    assert "freeze_global_scope" in review.atomic_assessments[0].strengthening_guards


def test_previous_review_policy_cannot_seed_delta_or_be_upgraded_to_new_ledger():
    prior = initial_review(NARROWED)
    prior["quality"]["atomic_basis"].pop("support_policy")
    original = copy.deepcopy(prior)
    body = input_body(NARROWED, prior)
    reused, plan = delta_plan(body)
    assert not reused and plan.rechecked_ids == ["a1", "a2"]
    assert facts_from_review({}, prior["candidate"], prior["quality"], []) == []
    assert prior == original


def leading_revision(answer):
    claims = atomic_claims(answer)
    history = frozen_history()
    history[0]["arguments"]["explanation"] = answer
    history[0]["result"]["quality"] = {
        "atomic_basis": {"answer_sha256": digest(answer)},
        "atomic_assessments": [
            dict(
                **c,
                supported=i > 0,
                model_supported=i > 0,
                evidence_ids=["source"] if i else [],
                strengthening_guards=[],
            )
            for i, c in enumerate(claims)
        ],
    }
    return freeze_revision(
        history, {"raw_question": "Explain the rule.", "resolved_goal": "Explain the rule."}
    )


@pytest.mark.parametrize(
    "answer",
    [
        "规则A适用于所有物品，不能取部分。",
        "The gate is permanently open, can admit cars.",
        "假如黄金已经耗尽，则继续放入白银。",
    ],
)
def test_deleting_leading_binding_cannot_publish_a_protected_bare_predicate(answer):
    transaction = leading_revision(answer)
    with pytest.raises(UnfulfilledGoal):
        assemble_revision(transaction, [{"id": "a1", "replacement": ""}])


def test_removing_a_clause_does_not_remove_an_independently_named_subject():
    transaction = leading_revision("The gate is permanently open, the bell rings.")
    result = assemble_revision(transaction, [{"id": "a1", "replacement": ""}])
    assert result["explanation"].strip() == "the bell rings."


def test_a_rejected_head_leaves_dependent_ending_editable_for_the_model():
    answer = "The method sorts by an unspecified metric until the bag is full. Another method stops."
    checks = [
        AtomicAssessment(**c, supported=i > 0, model_supported=i > 0, evidence_ids=["own"] if i else [])
        for i, c in enumerate(atomic_claims(answer))
    ]
    certified = certify_assessments(checks, {"own": "The bag is full. Another method stops."})
    assert not certified[1].supported
    assert "freeze_dependent_scope" in certified[1].strengthening_guards
    assert certified[-1].supported
