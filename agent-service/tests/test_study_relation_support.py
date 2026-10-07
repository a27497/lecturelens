"""Authorized quote binding, checkpoint reuse and legacy policy boundaries."""

import copy
import json

import pytest
from pydantic import ValidationError
from test_study_atomic import judgment

from lecturelens_agent.study.atomic_delta import delta_plan
from lecturelens_agent.study.atomic_goal_spans import AtomicSpanVerdict
from lecturelens_agent.study.ledger import facts_from_review
from lecturelens_agent.study.quality import review_messages, review_schema
from lecturelens_agent.study.support_review import output_tokens


def body(*, relation_review=True, prior=None):
    return json.loads(
        review_messages(
            "Explain the gate.",
            dict(
                kind="explanation",
                title="Gate",
                explanation="The gate opens when a ticket is scanned.",
                evidence_ids=["own"],
            ),
            [
                dict(evidence_id="own", text="The gate opens when a ticket is scanned."),
                dict(evidence_id="uncited", text="The gate always opens."),
            ],
            relation_review=relation_review,
            prior_atomic_review=prior,
        )[-1]["content"]
    )


def test_relation_contract_requires_proof_and_excludes_uncited_passages():
    b = body()
    assert [e["evidence_id"] for e in b["evidence"]] == ["e1"]
    schema = review_schema("explanation", review_mode=b["review_mode"], context=b)["function"]["parameters"]
    assert "relation" in schema["$defs"]["AtomicCheck"]["required"]
    assert output_tokens(b["review_mode"], b["relation_review"]) == 1600
    raw = judgment(b)
    raw["claim_checks"][0].pop("relation")
    with pytest.raises(ValidationError, match="exact target"):
        AtomicSpanVerdict.model_validate(raw, context=b)


@pytest.mark.parametrize(
    "mutation", ["other_claim", "other_source", "invented_quote", "uncited_quote", "missing_citation_quote"]
)
def test_relation_proof_cannot_borrow_or_fabricate_anchors(mutation):
    b = body()
    raw = judgment(b)
    proof = raw["claim_checks"][0]["relation"]
    if mutation == "other_claim":
        proof["claim_quote"] = "The gate always opens."
    elif mutation == "other_source":
        proof["grounds"][0]["evidence_id"] = "e2"
    elif mutation == "invented_quote":
        proof["grounds"][0]["quote"] = "The gate is open."
    elif mutation == "uncited_quote":
        proof["grounds"][0]["quote"] = "The gate always opens."
    else:
        proof["grounds"] = []
    with pytest.raises(ValidationError):
        AtomicSpanVerdict.model_validate(raw, context=b)


def test_absent_relation_policy_keeps_legacy_readback_but_cannot_publish_new_facts():
    b = body(relation_review=False)
    raw = judgment(b)
    q = AtomicSpanVerdict.model_validate(raw, context=b).review().model_dump()
    assert q["atomic_basis"]["support_policy"] == "course_entailment_v1"
    assert facts_from_review({}, b["candidate"], q, b["evidence"]) == []
    assert (
        "relation"
        not in review_schema("explanation", review_mode=b["review_mode"], context=b)["function"][
            "parameters"
        ]["$defs"]["AtomicCheck"]["properties"]
    )


def test_old_policy_and_tampered_quote_cannot_seed_delta_reuse():
    for legacy, tamper in [(True, False), (False, True)]:
        old = body(relation_review=not legacy)
        q = AtomicSpanVerdict.model_validate(judgment(old), context=old).review().model_dump()
        if tamper:
            q["atomic_assessments"][0]["relation"]["grounds"][0]["quote"] = "Invented source"
        prior = {"candidate": old["candidate"], "quality": q}
        saved = copy.deepcopy(prior)
        reused, plan = delta_plan(body(prior=prior))
        assert not reused and plan.rechecked_ids
        assert prior == saved


def test_rejection_observation_can_quote_an_own_source_without_claiming_support():
    b = body()
    raw = judgment(b)
    raw["claim_checks"][0].update(supported=False, evidence_ids=[])
    raw["claim_checks"][0]["relation"]["gap"] = "omitted_condition"
    q = AtomicSpanVerdict.model_validate(raw, context=b).review()
    assert "unsupported_explanation" in q.issues
    assert q.atomic_assessments[0].relation.grounds
    assert "omitted_condition" not in q.feedback


def test_reported_gap_cannot_be_published_as_supported():
    b = body()
    raw = judgment(b)
    raw["claim_checks"][0]["relation"]["gap"] = "untaught_property"
    with pytest.raises(ValidationError, match="support gap"):
        AtomicSpanVerdict.model_validate(raw, context=b)
