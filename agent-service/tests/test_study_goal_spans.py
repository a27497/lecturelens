"""Goal transport anchors do not establish semantic or Evidence support."""

import json

import httpx
import pytest
from pydantic import ValidationError
from test_study_atomic import judgment
from test_study_delta import INITIAL, NARROWED, SOURCE, initial_review

from lecturelens_agent.study.atomic_goal_spans import AtomicSpanVerdict, DeltaAtomicSpanVerdict
from lecturelens_agent.study.quality import review_contract, review_messages, review_wire_messages


def inputs(answer=NARROWED, prior=None):
    messages = review_messages(
        "Explain the state.",
        {"kind": "explanation", "title": "State", "explanation": answer, "evidence_ids": ["canonical"]},
        [{"evidence_id": "canonical", "text": SOURCE}],
        prior_atomic_review=prior,
    )
    return json.loads(messages[-1]["content"]), json.loads(review_wire_messages(messages)[-1]["content"])


def test_current_goal_anchors_bind_exact_answer_units_without_model_copied_quotes():
    body, wire = inputs()
    verdict = AtomicSpanVerdict.model_validate(judgment(wire), context=body).review()
    assert verdict.issues == [] and verdict.goal_answer_claim_ids == {"g1": ["a1"]}
    assert wire["goal_answer_claims"] == [[c["id"], c["start"], c["end"]] for c in body["atomic_claims"]]
    answer = wire["candidate"]["explanation"]
    assert [answer[start:end] for _, start, end in wire["goal_answer_claims"]] == [
        c["source_text"] for c in body["atomic_claims"]
    ]


@pytest.mark.parametrize("ids", [[], ["a24"], ["e1"], ["a1", "a1"]])
def test_missing_foreign_evidence_or_duplicate_goal_anchors_are_rejected(ids):
    body, wire = inputs()
    value = judgment(wire)
    value["goal_checks"][0]["answer_claim_ids"] = ids
    with pytest.raises(ValidationError):
        AtomicSpanVerdict.model_validate(value, context=body)


def test_goal_judgment_still_rejects_missing_demand_despite_valid_anchors():
    body, wire = inputs()
    value = judgment(wire)
    value["goal_checks"][0]["matches"] = False
    assert AtomicSpanVerdict.model_validate(value, context=body).review().issues == ["goal_mismatch"]


@pytest.mark.parametrize(
    "answer,goal,expected",
    [
        (
            "Each step performs constant comparisons and halves the input.",
            "Explain concrete steps.",
            ["goal_mismatch"],
        ),
        ("Each step compares neighbouring values and halves the input.", "Explain concrete steps.", []),
        (
            "Each step halves the input and reaches the base case.",
            "Explain concrete steps.",
            ["goal_mismatch"],
        ),
        ("Each step performs constant comparisons and halves the input.", "Explain the time complexity.", []),
    ],
)
def test_procedural_comparisons_require_source_named_operands_without_inventing_positions(
    answer, goal, expected
):
    source = "Each step compares left and right neighbours; the next input has half the size."
    messages = review_messages(
        goal,
        dict(kind="explanation", title="Steps", explanation=answer, evidence_ids=["owned"]),
        [dict(evidence_id="owned", text=source)],
    )
    body = json.loads(messages[-1]["content"])
    wire = json.loads(review_wire_messages(messages)[-1]["content"])
    assert AtomicSpanVerdict.model_validate(judgment(wire), context=body).review().issues == expected


def test_goal_anchor_never_bypasses_atomic_support_or_owned_citation_checks():
    body, wire = inputs(INITIAL)
    value = judgment(wire)
    value["claim_checks"][1].update(supported=False, evidence_ids=[])
    if value["claim_checks"][1].get("relation"):
        value["claim_checks"][1]["relation"]["grounds"] = []
    assert AtomicSpanVerdict.model_validate(value, context=body).review().issues == [
        "unsupported_explanation"
    ]
    value["claim_checks"][0]["evidence_ids"] = ["e2"]
    with pytest.raises(ValidationError, match="own observed citations"):
        AtomicSpanVerdict.model_validate(value, context=body)


@pytest.mark.parametrize(
    "raw,answer,source,expected",
    [
        (
            "Explain the second method in concrete steps.",
            "Each step compares neighbour values in constant time.",
            "Each step compares neighbour values in constant time and halves the input.",
            ["goal_mismatch"],
        ),
        (
            "Explain the second method in concrete steps.",
            "Each step compares neighbour values and halves the input.",
            "Each step compares neighbour values in constant time and halves the input.",
            [],
        ),
        (
            "Explain the constant term of the previous method in concrete steps.",
            "Each step compares neighbour values in constant time.",
            "Each step compares neighbour values in constant time and halves the input.",
            [],
        ),
        (
            "Explain the second method in concrete steps.",
            "Each step compares neighbour values in constant time.",
            "Each step compares neighbour values in constant time.",
            [],
        ),
    ],
)
def test_narrowed_resolved_goal_cannot_drop_a_whole_method_input_change(raw, answer, source, expected):
    resolved = "Explain the constant term."
    semantic = {
        "raw_question": raw,
        "resolved_goal": resolved,
        "previous_turns": [{"explanation": "The first method scans; the second method halves its input."}],
    }
    messages = review_messages(
        resolved,
        dict(kind="explanation", title="Method", explanation=answer, evidence_ids=["owned"]),
        [dict(evidence_id="owned", text=source)],
        semantic=semantic,
    )
    body = json.loads(messages[-1]["content"])
    wire = json.loads(review_wire_messages(messages)[-1]["content"])
    assert wire["semantic_context"]["raw_question"] == raw
    assert AtomicSpanVerdict.model_validate(judgment(wire), context=body).review().issues == expected


def test_delta_with_zero_targets_still_checks_the_entire_current_answer_goal():
    body, wire = inputs(prior=initial_review())
    assert wire["atomic_claims"] == []
    assert len(wire["goal_answer_claims"]) == 2
    value = judgment(wire)
    quality = DeltaAtomicSpanVerdict.model_validate(value, context=body).review().model_dump()
    assert quality["issues"] == [] and quality["atomic_delta"]["rechecked_ids"] == []
    assert len(quality["atomic_assessments"]) == 2
    recovered = json.loads(json.dumps(body))
    assert quality == DeltaAtomicSpanVerdict.model_validate(value, context=recovered).review().model_dump()


def test_unicode_goal_transport_preserves_every_character_and_reused_anchor():
    body, wire = inputs("🌿 门仍然打开（此时）。旧对象不再由 s 引用。")
    original = [{"id": c["id"], "source_text": c["source_text"]} for c in body["atomic_claims"]]
    reconstructed = [
        {"id": key, "source_text": wire["candidate"]["explanation"][start:end]}
        for key, start, end in wire["goal_answer_claims"]
    ]
    assert reconstructed == original
    spans = {key: (start, end) for key, start, end in wire["goal_answer_claims"]}
    assert all(
        c["source_text"] == body["candidate"]["explanation"][slice(*spans[c["id"]])]
        for c in wire["atomic_claims"]
    )
    assert all(
        c["context_start"] <= spans[c["id"]][0] < spans[c["id"]][1] <= c["context_end"]
        for c in wire["atomic_claims"]
    )
    assert len(json.dumps(wire["goal_answer_claims"]).encode()) < len(json.dumps(original).encode())
    _, reused = inputs(prior=initial_review())
    assert reused["atomic_claims"] == []
    assert len(reused["goal_answer_claims"]) == len(reused["reused_claim_ids"]) == 2


def test_all_reused_wire_schema_forbids_rechecking_without_relaxing_goal_review():
    from jsonschema import Draft202012Validator

    from lecturelens_agent.study.quality import review_schema

    body, wire = inputs(prior=initial_review())
    schema = review_schema("explanation", review_mode=body["review_mode"], context=body)["function"][
        "parameters"
    ]
    value = judgment(wire)
    Draft202012Validator(schema).validate(value)
    assert schema["properties"]["claim_checks"]["const"] == []
    value["claim_checks"] = [dict(id="a1", supported=True, evidence_ids=["e1"])]
    assert list(Draft202012Validator(schema).iter_errors(value))
    with pytest.raises(ValidationError):
        DeltaAtomicSpanVerdict.model_validate(value, context=body)
    value["claim_checks"] = []
    value["goal_checks"][0]["matches"] = False
    assert DeltaAtomicSpanVerdict.model_validate(value, context=body).review().issues == ["goal_mismatch"]


def test_supported_derived_claim_requires_own_evidence_in_wire_and_validator():
    from jsonschema import Draft202012Validator

    from lecturelens_agent.study.quality import review_schema

    body, wire = inputs()
    schema = review_schema("explanation", review_mode=body["review_mode"], context=body)["function"][
        "parameters"
    ]
    value = judgment(wire)
    value["claim_checks"][0].update(supported=True, evidence_ids=[])
    assert list(Draft202012Validator(schema).iter_errors(value))
    with pytest.raises(ValidationError, match="require Evidence"):
        AtomicSpanVerdict.model_validate(value, context=body)
    value["claim_checks"][0]["supported"] = False
    value["claim_checks"][0]["relation"]["grounds"] = []
    Draft202012Validator(schema).validate(value)
    assert "unsupported_explanation" in AtomicSpanVerdict.model_validate(value, context=body).review().issues


def test_legacy_quote_contract_remains_available_for_old_trace_replay():
    from lecturelens_agent.study.atomic_review import AtomicAnswerVerdict

    assert review_contract(review_mode="atomic_answer_support_v1") is AtomicAnswerVerdict


def test_overlong_goal_anchors_have_safe_actionable_retry_diagnostics(monkeypatch):
    from lecturelens_agent.study.atomic_review import correction_feedback
    from lecturelens_agent.study.provider import ChatProvider, ModelResponseError

    messages = review_messages(
        "Explain the state.",
        {"kind": "explanation", "title": "State", "explanation": NARROWED, "evidence_ids": ["canonical"]},
        [{"evidence_id": "canonical", "text": SOURCE}],
    )
    client = httpx.Client
    calls = []

    def handle(request):
        wire = json.loads(json.loads(request.content)["messages"][-1]["content"])
        calls.append(wire)
        value = judgment(wire)
        if len(calls) == 1:
            value["goal_checks"][0]["answer_claim_ids"] = ["a1", "a2", "a1", "a2"]
        else:
            assert "AT MOST 3" in wire["protocol_feedback"]["instruction"]
            assert wire["candidate"]["explanation"] == NARROWED
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "assess_study_candidate",
                                        "arguments": json.dumps(value),
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handle), **kw))
    provider = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture-key")
    with pytest.raises(ModelResponseError) as failure:
        provider.review(messages, 10)
    diagnostic = failure.value.diagnostics["validation"][0]
    assert diagnostic["path"] == ["goal_checks", 0, "answer_claim_ids"]
    assert diagnostic["bounds"]["max_length"] == 3
    assert diagnostic["bounds"]["actual_length"] == 4
    body = json.loads(messages[-1]["content"])
    body["protocol_feedback"] = correction_feedback(failure.value)
    messages[-1]["content"] = json.dumps(body)
    assert provider.review(messages, 10)["review"]["issues"] == []


def test_schema_diagnostics_never_expose_arbitrary_fields_values_or_messages():
    from lecturelens_agent.study.review_diagnostics import validation_diagnostics

    result = validation_diagnostics(
        [
            {
                "loc": ("goal_checks", 0, "password-sentinel"),
                "type": "too_long",
                "msg": "private model prose",
                "input": "private-api-key",
                "ctx": {"max_length": 3, "credential": "private-token"},
            },
        ]
    )
    assert result == [{"field": "other", "type": "too_long"}]
