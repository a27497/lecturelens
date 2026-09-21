import copy
import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_answer_points import draft
from test_study_intervals import arguments

from lecturelens_agent.study.contracts import StudyCommand, materialize_practice
from lecturelens_agent.study.intervals import interval_practice
from lecturelens_agent.study.quality import review_messages, review_schema, review_wire_messages
from lecturelens_agent.study.support_review import (
    CoverageVerdict,
    FieldSupportVerdict,
    MethodCoverageVerdict,
    field_view,
    output_tokens,
)

setup = test_study.setup


def messages():
    return review_messages(
        "Explain return and make a new output example",
        {**materialize_practice(draft()), "kind": "practice"},
        [
            {"evidence_id": "caption-a", "text": "Without return, the result is None."},
            {"evidence_id": "caption-b", "text": "The two print statements print inner and None."},
        ],
        structured_support=True,
    )


def accepted(body):
    return {
        "checks": [
            dict(
                field=field["field"],
                course_fact="Observed course fact",
                evidence_ids=[field["own_evidence"][0]["evidence_id"]],
                issue="none",
                correction="",
                **(
                    {"answer_check": {"answer": "An independently worked answer", "matches": True}}
                    if "answer_points" in field
                    else {"answer_check": None}
                    if "goals_v1" in body["review_mode"]
                    else {}
                ),
                **(
                    {
                        "method_alignment": {
                            "operation": "Observed method",
                            "output": "Observed output",
                            "matches": True,
                        }
                    }
                    if "selected_method" in field
                    else {}
                ),
            )
            for field in field_view(body)["fields"]
        ]
    }


def test_wire_fields_have_only_own_sources_and_preserve_exact_original_input():
    original = messages()
    snapshot = copy.deepcopy(original)
    wire = json.loads(review_wire_messages(original)[-1]["content"])
    assert set(wire) == {"goal", "fields"}
    assert [e["evidence_id"] for e in wire["fields"][0]["own_evidence"]] == ["field0_source1"]
    assert [e["evidence_id"] for e in wire["fields"][2]["own_evidence"]] == ["field2_source1"]
    assert wire["fields"][2]["answer_points"] == ["inner", "None"]
    assert original == snapshot


def test_same_source_gets_distinct_field_handles_but_same_stored_provenance():
    body = json.loads(messages()[-1]["content"])
    body["candidate"]["questions"][1]["evidence_ids"] = ["e1"]
    data = accepted(body)
    assert data["checks"][0]["evidence_ids"] != data["checks"][2]["evidence_ids"]
    result = FieldSupportVerdict.model_validate(data, context=body).review()
    assert result.grounds["explanation"][0].source == result.grounds["question_2"][0].source == "e1"
    data["checks"][2]["evidence_ids"] = data["checks"][0]["evidence_ids"]
    with pytest.raises(ValidationError):
        FieldSupportVerdict.model_validate(data, context=body)


def test_general_context_fills_near_edge_of_large_gap_without_crossing_full_gap():
    from lecturelens_agent.study.context import evidence_gaps

    evidence = [
        {"evidence_id": "left", "source_type": "SUBTITLE", "start_ms": 0, "end_ms": 1000, "text": "Method."},
        {
            "evidence_id": "right",
            "source_type": "SUBTITLE",
            "start_ms": 180000,
            "end_ms": 181000,
            "text": "Conclusion.",
        },
    ]
    assert evidence_gaps(evidence) == []
    assert evidence_gaps(evidence, general=True) == [(60000, "left", 1000, 61000, "SUBTITLE", "gap")]


def test_new_string_input_signal_does_not_certify_changed_program_or_reject_reproduction():
    from lecturelens_agent.study.strings import copied_string_input

    evidence = [{"text": 'The string "planet" is rebound to "planer".'}]
    original = "s='planet'\ns=s[:-1]+'r'\nprint(s)"
    assert copied_string_input("一道新字符串代码输出题", original, evidence)
    assert copied_string_input("Give a new string output exercise", original, evidence)
    assert not copied_string_input("复现课堂程序", original, evidence)
    assert not copied_string_input("new string practice", original.replace("planet", "rocket"), evidence)
    assert not copied_string_input("new string practice", "print(123)", evidence)
    assert not copied_string_input("new code exercise using the same strings", original, evidence)


def test_answer_comparison_must_reject_mismatch_and_persist_exact_observation():
    body = json.loads(messages()[-1]["content"])
    data = accepted(body)
    check = data["checks"][1]
    check["answer_check"] = {"answer": "A point may satisfy neither equation.", "matches": False}
    with pytest.raises(ValidationError):
        FieldSupportVerdict.model_validate(data, context=body)
    check.update(
        issue="incorrect_answer", correction="Do not claim every other point satisfies one equation."
    )
    review = FieldSupportVerdict.model_validate(data, context=body).review()
    assert review.issues == ["incorrect_answer"]
    assert not review.answer_observations[0].matches_reference
    assert review.answer_observations[0].expected_answer == check["answer_check"]["answer"]
    del check["answer_check"]
    with pytest.raises(ValidationError):
        FieldSupportVerdict.model_validate(data, context=body)


@pytest.mark.parametrize(
    "defect", ["borrowed", "missing_field", "duplicate_field", "invented_goal", "silent_correction"]
)
def test_field_review_rejects_unbound_support(defect):
    body = json.loads(messages()[-1]["content"])
    data = accepted(body)
    if defect == "borrowed":
        data["checks"][0]["evidence_ids"] = ["field2_source1"]
    elif defect == "missing_field":
        data["checks"].pop()
    elif defect == "duplicate_field":
        data["checks"][1]["field"] = "explanation"
    elif defect == "invented_goal":
        data["checks"][2].update(
            issue="goal_mismatch", correction="Change the example.", goal_quote="Use ONLY the original inputs"
        )
    else:
        data["checks"][0]["correction"] = "Actually the explanation is wrong."
    with pytest.raises(ValidationError):
        FieldSupportVerdict.model_validate(data, context=body)


def test_support_observations_and_complete_three_field_corrections_survive_validation():
    body = json.loads(messages()[-1]["content"])
    data = accepted(body)
    for check in data["checks"]:
        check.update(
            issue="unsupported_explanation" if check["field"] == "explanation" else "unsupported_question",
            correction="x" * 100,
        )
    result = FieldSupportVerdict.model_validate(data, context=body).review()
    assert result.feedback.count("x" * 100) == 3
    assert result.grounds["question_2"][0].source == "e2"
    assert result.grounds["question_2"][0].quote == "The two print statements print inner and None."
    assert result.factual_check.count("Observed course fact") == 3


def test_coverage_is_blind_to_the_candidate_refusal_even_after_protocol_retry():
    original = review_messages(
        "Practice substitution",
        {"kind": "insufficient_evidence", "reason": "SECRET WRONG REFUSAL"},
        [{"evidence_id": "a", "text": "Substitute zero to check the origin."}],
        structured_support=True,
    )
    body = json.loads(original[-1]["content"])
    body["protocol_feedback"] = {"instruction": "SECRET WRONG REFUSAL"}
    original[-1]["content"] = json.dumps(body)
    wire = review_wire_messages(original)
    assert "SECRET" not in json.dumps(wire)
    result = CoverageVerdict.model_validate(
        dict(
            course_fact="The course demonstrates substitution.",
            evidence_ids=["e1"],
            support="demonstrated_method",
            missing_goal_quote="",
        ),
        context=body,
    ).review()
    assert result.issues == ["unjustified_abstention"]
    assert result.grounds["explanation"][0].quote == "Substitute zero to check the origin."
    with pytest.raises(ValidationError):
        CoverageVerdict.model_validate(
            dict(
                course_fact="No support.",
                evidence_ids=[],
                support="absent",
                missing_goal_quote="an invented requirement",
            ),
            context=body,
        )


def test_empty_evidence_cannot_claim_answerable_coverage():
    body = json.loads(
        review_messages(
            "Teach eigenvalues",
            {"kind": "insufficient_evidence", "reason": "none"},
            [],
            structured_support=True,
        )[-1]["content"]
    )
    data = dict(
        course_fact="No observed evidence.",
        evidence_ids=[],
        support="absent",
        missing_goal_quote="eigenvalues",
    )
    assert not CoverageVerdict.model_validate(data, context=body).review().issues
    data.update(support="direct", missing_goal_quote="")
    with pytest.raises(ValidationError):
        CoverageVerdict.model_validate(data, context=body)


def test_computed_view_hides_verified_answers_only_after_actual_proof_and_forbids_recalculation():
    candidate, observation = interval_practice(arguments())
    original = review_messages(
        "Practice halving",
        {**candidate, "kind": "practice"},
        [{"evidence_id": "caption-a", "text": "Guess the midpoint; use higher/lower feedback."}],
        example_checks=[observation],
        structured_support=True,
    )
    body = json.loads(original[-1]["content"])
    fields = field_view(body)["fields"]
    assert fields[2]["calculation_verified"] and "answer_points" not in fields[2]
    assert "answer_points" in body["candidate"]["questions"][1]
    data = accepted(body)
    data["checks"][2].update(issue="incorrect_answer", correction="Override the computed value.")
    with pytest.raises(ValidationError):
        FieldSupportVerdict.model_validate(data, context=body)
    body["candidate"]["questions"][1]["answer_points"] = ["forged"]
    with pytest.raises(ValueError, match="unverified"):
        field_view(body)


@pytest.mark.parametrize("cancel", [False, True])
def test_runtime_reserves_wire_budget_and_keeps_review_observations_private(setup, cancel):
    store, _, runtime, scope = setup
    reservations = []
    reserve = store.reserve

    def capture(*args, **kwargs):
        reservations.append(args)
        return reserve(*args, **kwargs)

    store.reserve = capture

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        wire = review_wire_messages(messages)
        schema = review_schema(
            body["candidate"]["kind"], body.get("rubric_policy"), body["review_mode"], context=body
        )
        expected = (
            len(json.dumps(wire, ensure_ascii=False).encode())
            + len(json.dumps([schema]).encode())
            + output_tokens(body["review_mode"])
        )
        assert reservations[-1][2:] == ("model", expected)
        data = accepted(body)
        for check in data["checks"]:
            check["course_fact"] = "Private support observation"
        if cancel:
            store.command(StudyCommand(**scope, operation="CANCEL"), "mock")
        return {"review": FieldSupportVerdict.model_validate(data, context=body).review().model_dump()}

    runtime.provider.review = review
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == ("cancelled" if cancel else "succeeded")
    assert bool(result["artifact"]) != cancel
    assert "Private support observation" not in json.dumps(test_study.read(setup, "EVENTS"))
    if not cancel:
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT result FROM study_tool_result WHERE run_id=%s", (result["run"]["run_id"],)
            ).fetchall()
        assert "Private support observation" in json.dumps(rows)


def test_search_support_observation_replays_without_repeating_coverage_call(setup):
    from lecturelens_agent.study.store import RunStopped

    store, _, runtime, _ = setup
    reviews = []
    original_save = store.save_tool
    interrupted = False

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "method", "practice_kind": "general"},
            }
        assert body["course_coverage"]["can_answer"] is True
        assert body["course_coverage"]["evidence_ids"] == ["e1"]
        assert body["course_coverage"]["advisory"] is True
        candidate = draft()
        for field in [candidate, *candidate["questions"]]:
            field["evidence_ids"] = ["e1"]
        return {
            "name": "create_practice_set",
            "arguments": {
                **{k: candidate[k] for k in ("title", "explanation", "evidence_ids")},
                "concept": candidate["questions"][0],
                "application": candidate["questions"][1],
                "method_id": "m1",
            },
        }

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        reviews.append(body["review_mode"])
        if body["review_mode"] == "course_methods_v1":
            return {
                "review": MethodCoverageVerdict.model_validate(
                    dict(
                        methods=[
                            {
                                "operation": "Check a stopping condition",
                                "input": "Algorithm",
                                "output": "Stops or not",
                                "evidence_id": "e1",
                            }
                        ],
                        course_fact="A demonstrated method.",
                        evidence_ids=["e1"],
                        support="demonstrated_method",
                        missing_goal_quote="",
                    ),
                    context=body,
                )
                .review()
                .model_dump()
            }
        return {
            "review": FieldSupportVerdict.model_validate(accepted(body), context=body).review().model_dump()
        }

    def save(*args, **kwargs):
        nonlocal interrupted
        result = original_save(*args, **kwargs)
        if not interrupted:
            interrupted = True
            raise RunStopped()
        return result

    runtime.provider.decide, runtime.provider.review, store.save_tool = decide, review, save
    run = test_study.start(setup)
    runtime.execute(run)
    assert test_study.read(setup)["run"]["model_calls"] == 2
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == 4
    assert reviews == ["course_methods_v1", "field_support_scoped_goals_v1"]
