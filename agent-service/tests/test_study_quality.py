import copy
import json

import pytest
from pydantic import ValidationError

from lecturelens_agent.study.quality import (
    ReviewVerdict,
    citation_mismatches,
    review_material,
    review_messages,
    review_schema,
    rubric_clauses,
)


def accepted_verdict():
    return {
        "answer_checks": [
            {"answer": "None", "matches": True, "evidence": ["e1:1"]},
            {"answer": "Inner print then False", "matches": True, "evidence": ["e2:1"]},
        ],
        "rule_results": [["met", "met"], ["met"]],
        "findings": [],
    }


def review_input():
    return {
        "goal": "Explain return values",
        "candidate": {
            "kind": "practice",
            "explanation": "Nothing is returned",
            "evidence_ids": ["e1"],
            "questions": [
                {
                    "question": "What is returned?",
                    "answer": "None",
                    "rubric": "None earns credit; without the type no credit",
                    "evidence_ids": ["e1"],
                },
                {
                    "question": "What is printed?",
                    "answer": "Inner print then False",
                    "rubric": "Include both lines",
                    "evidence_ids": ["e2"],
                },
            ],
        },
        "evidence": [
            {"evidence_id": "e1", "text": "Implicitly returns None"},
            {"evidence_id": "e2", "text": "Print inside first, then False"},
            {"evidence_id": "e3", "text": "Related but uncited text"},
        ],
    }


def conflicting_verdict():
    data = accepted_verdict()
    data["rule_results"][0] = ["awards_credit", "denies_credit"]
    return data


def factual_verdict():
    data = accepted_verdict()
    data["findings"] = [
        {
            "field": "explanation",
            "issue": "unsupported_explanation",
            "fix": "The return value is None.",
            "anchors": ["explanation:1", "e1:1"],
        }
    ]
    return data


def test_rule_outcomes_preserve_unverified_labels_and_original_material():
    review = ReviewVerdict.model_validate(conflicting_verdict(), context=review_input()).review()
    assert review.issues == ["incorrect_answer"]
    assert "rule labels may be wrong" in review.feedback
    assert review.grounds == {}
    observation = review.rubric_observations[0]
    assert observation.status == "needs_verification"
    assert observation.question.quote == "What is returned?"
    assert observation.answer.quote == "None"
    assert [(rule.quote, rule.result) for rule in observation.rules] == [
        ("None earns credit;", "awards_credit"),
        ("without the type no credit", "denies_credit"),
    ]
    assert len(review.feedback) <= 400
    # A rubric-only disagreement must not manufacture a factual answer correction.
    assert review.answer_observations[0].expected_answer == "None"
    assert review.answer_observations[0].matches_reference is True
    assert "question_1:" not in review.feedback


@pytest.mark.parametrize("anchors", [["e3:1"], ["e999:1"], ["question_1.rubric:1"], ["e1:1", "e1:1"], []])
def test_computed_answers_require_own_course_evidence_even_when_accepted(anchors):
    data = accepted_verdict()
    data["answer_checks"][0]["evidence"] = anchors
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data, context=review_input())


def test_answer_checks_cannot_be_omitted_or_overridden_by_an_editing_instruction():
    data = accepted_verdict()
    data["answer_checks"].pop()
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data, context=review_input())
    data = accepted_verdict()
    data["findings"] = [
        {
            "field": "question_2",
            "issue": "incorrect_answer",
            "fix": "Remove the correct printed line.",
            "anchors": ["question_2.answer:1", "e2:1"],
        }
    ]
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data, context=review_input())


def test_total_factual_defects_and_feedback_remain_bounded():
    data = factual_verdict()
    for answer in data["answer_checks"]:
        answer["matches"] = False
    with pytest.raises(ValidationError, match="at most two"):
        ReviewVerdict.model_validate(data, context=review_input())


@pytest.mark.parametrize(
    "results", [[["met"], ["met"]], [["met", "met", "met"], ["met"]], [["met", "met"]], [["met", "met"], []]]
)
def test_no_rule_can_be_skipped_or_added(results):
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(accepted_verdict() | {"rule_results": results}, context=review_input())


def test_mandatory_missing_and_optional_detail_have_distinct_outcomes():
    data = accepted_verdict()
    data["rule_results"][0] = ["met", "unmet"]
    result = ReviewVerdict.model_validate(data, context=review_input()).review()
    assert result.issues == ["incorrect_answer"]
    assert result.rubric_observations[0].rules[1].result == "unmet"
    data["rule_results"][0] = ["awards_credit", "not_applicable"]
    assert not ReviewVerdict.model_validate(data, context=review_input()).review().issues
    data["rule_results"][0] = ["met", "conflicting"]
    assert (
        ReviewVerdict.model_validate(data, context=review_input())
        .review()
        .rubric_observations[0]
        .rules[1]
        .result
        == "conflicting"
    )


def test_wrong_rubric_labels_cannot_replace_factual_fix_or_evidence():
    body = review_input()
    body["candidate"]["questions"][0].update(
        question="Give the value and its type.",
        answer="None",
        rubric="Value earns one point; type earns another point",
    )
    data = accepted_verdict()
    data["rule_results"][0] = ["awards_credit", "unmet"]  # Model mistakes partial credit for full credit.
    data["answer_checks"][0] = {
        "answer": "None of type NoneType.",
        "matches": False,
        "evidence": ["e1:1"],
    }
    result = ReviewVerdict.model_validate(data, context=body).review()
    assert result.feedback.startswith("question_1: None of type NoneType.")
    assert "Rewrite the conflicting" not in result.feedback
    assert result.grounds["question_1"][1].source == "e1"
    assert result.grounds["question_1"][1].quote == "Implicitly returns None"
    assert result.rubric_observations[0].rules[0].result == "awards_credit"
    assert result.rubric_observations[0].rules[1].result == "unmet"


def test_maximum_fixes_and_full_reference_answers_survive_round_trip():
    from lecturelens_agent.study.quality import QualityReview

    body = review_input()
    body["candidate"]["questions"][0]["answer"] = "a" * 1490 + "FINAL_TYPE"
    data = conflicting_verdict()
    data["rule_results"][1] = ["unmet"]
    data["answer_checks"] = [
        {"answer": str(i) * 100, "matches": False, "evidence": [f"e{i}:1"]} for i in (1, 2)
    ]
    result = ReviewVerdict.model_validate(data, context=body).review()
    restored = QualityReview.model_validate_json(result.model_dump_json())
    assert "1" * 100 in restored.feedback and "2" * 100 in restored.feedback
    assert len(restored.feedback) <= 400
    assert restored.rubric_observations[0].answer.quote.endswith("FINAL_TYPE")
    assert len(restored.rubric_observations[0].answer.quote) == 1500
    assert len(restored.rubric_observations) == 2
    assert restored.grounds["question_2"][1].source == "e2"


def test_incorrect_course_answer_can_meet_its_own_wrong_rubric():
    body = review_input()
    body["candidate"]["questions"][1].update(answer="Only False", rubric="Only False earns full credit")
    data = accepted_verdict()
    data["answer_checks"][1] = {
        "answer": "Inner print then False",
        "matches": False,
        "evidence": ["e2:1"],
    }
    result = ReviewVerdict.model_validate(data, context=body).review()
    assert result.issues == ["incorrect_answer"]
    assert result.feedback == "question_2: Inner print then False"
    assert result.grounds["question_2"][1].quote == "Print inside first, then False"


@pytest.mark.parametrize(
    "anchors",
    [
        ["explanation:1", "e3:1"],
        ["explanation:1", "e999:1"],
        ["explanation:1", "question_2.answer:1"],
        ["e1:1", "e1:1"],
        ["e1:1", "e2:1"],
        ["explanation:1"],
    ],
)
def test_findings_reject_unknown_uncited_wrong_field_or_duplicate_anchors(anchors):
    data = factual_verdict()
    data["findings"][0]["anchors"] = anchors
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data, context=review_input())


def test_only_local_source_text_is_returned_never_model_quotation():
    data = factual_verdict()
    result = ReviewVerdict.model_validate(data, context=review_input()).review()
    assert result.grounds["explanation"][1].quote == "Implicitly returns None"
    data["findings"][0]["quote"] = "Forged prose"
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data, context=review_input())
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(accepted_verdict())


def test_rubric_split_preserves_late_and_repeated_clauses_without_semantic_decisions():
    text = ";".join(["same"] * 10 + ["opposite rule"])
    parts = rubric_clauses(text)
    assert len(parts) == 8 and "".join(parts) == text
    assert parts[-1].endswith("opposite rule")
    assert rubric_clauses("可选补充；必须写类型。") == ["可选补充；", "必须写类型。"]


def test_catalog_covers_visible_text_and_excludes_truncated_evidence():
    body = review_input()
    body["evidence"][0]["text"] = "x" * 1200 + "PRIVATE invisible tail"
    sent = json.loads(review_messages(body["goal"], body["candidate"], body["evidence"])[-1]["content"])
    assert "PRIVATE" not in json.dumps(sent)
    catalog, tasks = review_material(sent)
    assert catalog == sent["source_catalog"] and tasks == sent["rubric_tasks"]
    assert "".join(q["quote"] for q in catalog.values() if q["source"] == "e1") == "x" * 1200
    data = factual_verdict()
    data["findings"][0]["anchors"][1] = "e1:6"
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data, context=sent)


def test_duplicate_findings_and_missing_fix_fail_closed():
    data = factual_verdict()
    data["findings"].append(copy.deepcopy(data["findings"][0]))
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data, context=review_input())
    data = factual_verdict()
    data["findings"][0]["fix"] = " "
    with pytest.raises(ValidationError):
        ReviewVerdict.model_validate(data, context=review_input())


def test_inline_citations_checked_per_field_with_original_alias_mapping():
    candidate = {
        "explanation": "正确说明（e1, e3）。",
        "evidence_ids": ["id-a"],
        "questions": [
            {
                "question": "What happens?",
                "answer": "Answer (Cited: e2).",
                "rubric": "Use evidence e1.",
                "evidence_ids": ["id-b"],
            }
        ],
    }
    assert citation_mismatches(candidate, {"e1": "id-a", "e2": "id-b", "e3": "id-c"}) == [
        "explanation",
        "question_1_rubric",
    ]
    candidate["explanation"] = "正确说明 [e1]。 Variable e2 = 3; consider (e2 + 1)."
    candidate["questions"][0]["rubric"] = "Use the cited passage."
    assert citation_mismatches(candidate, {"e1": "id-a", "e2": "id-b"}) == []


def test_abstention_wire_contract_has_no_practice_defects_or_prose_fields():
    schema = review_schema("insufficient_evidence")["function"]["parameters"]
    assert set(schema["properties"]) == {"issues"}
    assert schema["properties"]["issues"]["items"]["const"] == "unjustified_abstention"
    assert schema["additionalProperties"] is False
    messages = review_messages(
        "学函数", {"kind": "insufficient_evidence", "reason": "No supporting passage"}, []
    )
    assert "missing practice/questions/citations are expected" in messages[0]["content"].lower()
    assert "review_order" not in messages[-1]["content"]
    assert "THREE explicit verdicts" not in messages[0]["content"]


def test_python_observations_preserve_literal_scope_and_never_execute(tmp_path):
    from lecturelens_agent.study.quality import code_observations

    target = tmp_path / "must-not-exist"
    candidate = {
        "explanation": f"```python\nopen({str(target)!r}, 'w').write('bad')\n```",
        "questions": [
            {
                "question": "What prints? def g(): print('hello'); g()",
                "answer": "hello",
                "rubric": "Exact output",
            },
            {
                "question": "```python\ndef g(): print('hello'); g()\n```",
                "answer": "Nothing",
                "rubric": "No top-level caller",
            },
        ],
    }
    observed = code_observations(candidate)
    assert not target.exists()
    assert {"field": "question_1_question", "kind": "inline_definition"} in observed
    assert {
        "field": "question_2_question",
        "kind": "syntax_valid",
        "module_statements": ["FunctionDef"],
    } in observed
    candidate["explanation"] = "```python\ndef f(:\n```"
    assert code_observations(candidate)[0]["kind"] == "syntax_error"
    # Intentionally broken examples are observations for the reviewer, not automatic rejection.
    candidate["explanation"] = "```javascript\nconst f = () => 1;\n```"
    assert all(item["field"] != "explanation" for item in code_observations(candidate))


def test_review_preserves_question_own_citations_and_syntax_observations():
    import json

    candidate = {
        "kind": "practice",
        "explanation": "Description",
        "evidence_ids": ["a"],
        "questions": [
            {
                "question": "```python\ndef f():\n    print('inside')\nf()\n```",
                "answer": "inside",
                "rubric": "Exact output",
                "evidence_ids": ["b"],
            }
        ],
    }
    body = json.loads(
        review_messages(
            "Explain",
            candidate,
            [{"evidence_id": "a", "text": "First fact"}, {"evidence_id": "b", "text": "Second fact"}],
        )[-1]["content"]
    )
    assert body["candidate"]["evidence_ids"] == ["e1"]
    assert body["candidate"]["questions"][0]["evidence_ids"] == ["e2"]
    assert body["code_observations"][0]["module_statements"] == ["FunctionDef", "Expr"]


def test_multiline_unfenced_code_is_allowed_but_literal_newlines_are_not():
    from lecturelens_agent.study.quality import code_observations

    text = "Example:\ndef f():\n    print('hello')\nf()\nWhat prints?"
    assert code_observations({"explanation": text}) == []
    assert any(
        item["kind"] == "literal_newlines"
        for item in code_observations({"explanation": text.replace("\n", "\\n")})
    )
