import copy
import json

import pytest
from pydantic import ValidationError

from lecturelens_agent.study.contracts import PracticeDraftArgs, materialize_practice, tool_schemas
from lecturelens_agent.study.grounded import CourseReviewVerdict
from lecturelens_agent.study.quality import review_messages


def draft():
    return {
        "title": "Return and output",
        "explanation": "Without return, a function returns None.",
        "evidence_ids": ["caption-a"],
        "questions": [
            {
                "question": "What is returned without return?",
                "answer_points": ["None"],
                "evidence_ids": ["caption-a"],
            },
            {
                "question": "What appears when an inner print is followed by printing its None result?",
                "answer_points": ["inner", "None"],
                "evidence_ids": ["caption-b"],
            },
        ],
    }


def context():
    candidate = {**materialize_practice(draft()), "kind": "practice"}
    evidence = [
        {"evidence_id": "caption-a", "text": "Without explicit return, the call returns None."},
        {
            "evidence_id": "caption-b",
            "text": "The internal print displays inner, then the outer print displays None.",
        },
    ]
    return json.loads(review_messages("Distinguish returning and output", candidate, evidence)[-1]["content"])


def verdict():
    return {
        "explanation": {"issue": "none", "correction": "", "anchors": []},
        "questions": [
            {"issue": "none", "answer": "None", "evidence": ["e1"]},
            {"issue": "none", "answer": "inner then None", "evidence": ["e2"]},
        ],
    }


def test_single_source_compilation_preserves_all_ordered_points_and_hides_legacy_fields():
    data = draft()
    data["questions"][1]["answer_points"] = ["inner", "inner", "None"]
    saved = materialize_practice(data)
    assert saved["questions"][1]["answer"] == saved["questions"][1]["rubric"] == "inner\ninner\nNone"
    assert "answer" not in data["questions"][1]
    schema = next(s for s in tool_schemas() if s["function"]["name"] == "create_practice_set")
    props = schema["function"]["parameters"]["$defs"]["AnswerPointsQuestion"]["properties"]
    assert "answer_points" in props and "answer" not in props and "rubric" not in props
    data["questions"][1]["rubric"] = "Any answer containing None gets zero"
    with pytest.raises(ValidationError):
        PracticeDraftArgs.model_validate(data)


@pytest.mark.parametrize("points", [[], [" "], ["x"] * 5, ["x" * 301]])
def test_answer_points_are_bounded_and_nonempty(points):
    data = draft()
    data["questions"][0]["answer_points"] = points
    with pytest.raises(ValidationError):
        materialize_practice(data)


def test_review_omits_separate_scoring_text_but_rejects_forged_derivation():
    body = context()
    assert "rubric_tasks" not in body
    assert all("rubric" not in q for q in body["candidate"]["questions"])
    assert not any("rubric" in source for source in body["source_catalog"])
    candidate = {**materialize_practice(draft()), "kind": "practice"}
    candidate["questions"][1]["rubric"] = "An incompatible old scoring rule"
    with pytest.raises(ValueError, match="relabel"):
        review_messages("goal", candidate, [])


def test_course_review_corrects_wrong_points_without_a_second_conflicting_finding():
    body = context()
    body["candidate"]["questions"][1].update(answer="None", answer_points=["None"])
    data = verdict()
    data["questions"][1]["issue"] = "incorrect_answer"
    review = CourseReviewVerdict.model_validate(data, context=body).review()
    assert review.issues == ["incorrect_answer"]
    assert review.feedback == "question_2: inner then None"
    assert review.grounds["question_2"][0].quote == "None"
    assert review.grounds["question_2"][1].source == "e2"
    assert review.rubric_observations == []
    data["findings"] = [{"field": "question_2", "issue": "unsupported_question"}]
    with pytest.raises(ValidationError):
        CourseReviewVerdict.model_validate(data, context=body)


def test_accepted_questions_need_not_regenerate_answers_but_rejections_need_corrections():
    body = context()
    data = verdict()
    for question in data["questions"]:
        question["answer"] = ""
    review = CourseReviewVerdict.model_validate(data, context=body).review()
    assert review.issues == [] and review.answer_observations == []
    data["questions"][1]["issue"] = "incorrect_answer"
    with pytest.raises(ValidationError):
        CourseReviewVerdict.model_validate(data, context=body)
    data["questions"][1]["answer"] = "Both lines must be included: inner, then None."
    review = CourseReviewVerdict.model_validate(data, context=body).review()
    assert review.issues == ["incorrect_answer"]
    assert review.answer_observations[0].matches_reference is False


@pytest.mark.parametrize("anchors", [["e2"], ["unknown"], ["question_1.answer:1"], ["e1", "e1"]])
def test_course_solution_still_requires_its_own_unique_course_anchors(anchors):
    data = verdict()
    data["questions"][0]["evidence"] = anchors
    with pytest.raises(ValidationError):
        CourseReviewVerdict.model_validate(data, context=context())


def test_explanation_criticism_requires_own_claim_and_evidence_not_unrelated_course():
    data = verdict()
    data["explanation"] = {
        "issue": "unsupported_explanation",
        "correction": "Remove the unsupported statement.",
        "anchors": ["explanation:1", "e2"],
    }
    with pytest.raises(ValidationError):
        CourseReviewVerdict.model_validate(data, context=context())
    data["explanation"]["anchors"][1] = "e1"
    assert CourseReviewVerdict.model_validate(data, context=context()).review().issues == [
        "unsupported_explanation"
    ]
    data["explanation"]["issue"] = "none"
    with pytest.raises(ValidationError):
        CourseReviewVerdict.model_validate(data, context=context())


def test_maximum_three_field_feedback_fits_and_observations_are_not_quotations():
    data = verdict()
    data["explanation"] = {
        "issue": "unsupported_explanation",
        "correction": "c" * 100,
        "anchors": ["explanation:1", "e1"],
    }
    for i, question in enumerate(data["questions"]):
        question.update(issue="incorrect_answer", answer=str(i) * 100)
    review = CourseReviewVerdict.model_validate(data, context=context()).review()
    assert len(review.feedback) <= 400
    assert "0" * 100 in review.feedback and "1" * 100 in review.feedback
    assert review.answer_observations[0].expected_answer == "0" * 100
    assert review.answer_observations[0].grounds[0].quote != "0" * 100
    altered = copy.deepcopy(context())
    altered["candidate"]["questions"][0]["answer"] = "Different than stored points"
    with pytest.raises(ValidationError):
        CourseReviewVerdict.model_validate(data, context=altered)


def test_derived_review_course_quotes_keep_full_sentences_and_reject_old_span_ids():
    candidate = {**materialize_practice(draft()), "kind": "practice"}
    passage = "A long passage prefix. " * 14 + "The condition applies only if a return is absent."
    body = json.loads(
        review_messages(
            "goal",
            candidate,
            [
                {"evidence_id": "caption-a", "text": passage},
                {"evidence_id": "caption-b", "text": "Inner and outer print both display."},
            ],
        )[-1]["content"]
    )
    assert body["evidence"][0]["text"] == passage
    assert "e1" not in body["source_catalog"]
    data = verdict()
    checked = CourseReviewVerdict.model_validate(data, context=body).review()
    assert checked.answer_observations[0].grounds[0].quote == passage
    data["questions"][0]["evidence"] = ["e1:1"]
    with pytest.raises(ValidationError):
        CourseReviewVerdict.model_validate(data, context=body)


def test_long_accepted_restatement_cannot_replace_reference_or_fail_optional_output():
    body = context()
    data = verdict()
    data["questions"][0]["answer"] = "Redundant accepted restatement. " * 12
    original = json.dumps(body, sort_keys=True)
    review = CourseReviewVerdict.model_validate(data, context=body).review()
    assert review.issues == []
    assert not any(o.field == "question_1" for o in review.answer_observations)
    assert json.dumps(body, sort_keys=True) == original
    data["questions"][0]["issue"] = "incorrect_answer"
    with pytest.raises(ValidationError, match="at most 200"):
        CourseReviewVerdict.model_validate(data, context=body)


def test_generic_tool_names_concept_and_new_application_while_preserving_old_replays():
    from lecturelens_agent.study.contracts import GenericPracticeArgs

    legacy = draft()
    named = {k: legacy[k] for k in ("title", "explanation", "evidence_ids")}
    named.update(concept=legacy["questions"][0], application=legacy["questions"][1])
    assert GenericPracticeArgs.model_validate(named).to_draft() == legacy
    assert GenericPracticeArgs.model_validate(legacy).to_draft() == legacy
    schema = next(
        s["function"]["parameters"] for s in tool_schemas() if s["function"]["name"] == "create_practice_set"
    )
    assert {"concept", "application"} <= set(schema["required"])
    assert "questions" not in schema["properties"]
    with pytest.raises(ValidationError):
        GenericPracticeArgs.model_validate({**named, "questions": legacy["questions"]})
    bad = copy.deepcopy(named)
    bad["application"]["rubric"] = "Invented scoring condition"
    with pytest.raises(ValidationError):
        GenericPracticeArgs.model_validate(bad)
