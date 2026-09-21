import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_intervals import arguments

from lecturelens_agent.study.contracts import IntervalPracticeArgs, tool_schemas
from lecturelens_agent.study.grounded import ComputedCourseReviewVerdict
from lecturelens_agent.study.intervals import interval_practice
from lecturelens_agent.study.quality import review_messages, review_schema

setup = test_study.setup


def context():
    candidate, observation = interval_practice(arguments())
    evidence = [
        {
            "evidence_id": "caption-a",
            "text": "Guess the midpoint and discard half using higher or lower feedback.",
        }
    ]
    return json.loads(
        review_messages(
            "Practice halving", {**candidate, "kind": "practice"}, evidence, example_checks=[observation]
        )[-1]["content"]
    )


def verdict():
    return {
        "explanation": {"issue": "none", "correction": "", "anchors": []},
        "question_1": {"issue": "none", "answer": "", "evidence": ["e1"]},
        "question_2": {"issue": "none", "answer": "", "evidence": ["e1"]},
    }


def test_computed_review_preserves_support_rejection_but_does_not_solicit_guessed_arithmetic():
    body = context()
    assert body["review_mode"] == "computed_application"
    assert not ComputedCourseReviewVerdict.model_validate(verdict(), context=body).review().issues
    data = verdict()
    data["question_2"].update(issue="unsupported_question", answer="The course does not teach halving.")
    result = ComputedCourseReviewVerdict.model_validate(data, context=body).review()
    assert result.issues == ["unsupported_question"]
    assert result.grounds["question_2"][1].quote == body["evidence"][0]["text"]
    data["question_2"].update(issue="incorrect_answer", answer="Keep the excluded midpoint.")
    with pytest.raises(ValidationError):
        ComputedCourseReviewVerdict.model_validate(data, context=body)
    schema = review_schema("practice", "answer_points_v1", "computed_application")
    assert (
        "incorrect_answer"
        not in schema["function"]["parameters"]["$defs"]["ComputedQuestionCheck"]["properties"]["issue"][
            "enum"
        ]
    )


@pytest.mark.parametrize("mutation", ["answer", "problem", "question"])
def test_computed_mode_cannot_be_forged_for_changed_answer_or_conditions(mutation):
    body = context()
    if mutation == "answer":
        body["candidate"]["questions"][1].update(answer="wrong", answer_points=["wrong"])
    elif mutation == "problem":
        body["example_checks"][0]["application"]["problem"]["upper"] = 100
    else:
        body["candidate"]["questions"][1]["question"] += " Assume integers instead."
    with pytest.raises(ValidationError, match="actual calculation"):
        ComputedCourseReviewVerdict.model_validate(verdict(), context=body)


def test_optional_worked_example_schema_exposes_object_fields_and_retains_null_semantics():
    schema = next(
        t["function"]["parameters"]
        for t in tool_schemas()
        if t["function"]["name"] == "create_interval_practice"
    )
    worked = schema["properties"]["worked_example"]
    assert worked["type"] == ["object", "null"]
    assert set(worked["required"]) == {"lower", "upper", "feedback", "evidence_ids"}
    assert "worked_example" not in schema["required"]
    data = arguments()
    data["worked_example"] = None
    IntervalPracticeArgs.model_validate(data)
    data["worked_example"] = "An unstructured example"
    with pytest.raises(ValidationError):
        IntervalPracticeArgs.model_validate(data)


def test_python_proof_recomputes_output_and_does_not_trust_forged_observation():
    from test_study_python_practice import arguments as python_arguments

    from lecturelens_agent.study.contracts import python_practice
    from lecturelens_agent.study.examples import check_example
    from lecturelens_agent.study.quality import verified_application

    args = python_arguments()
    observation = {
        "program": args["program"],
        "evidence_ids": args["program_evidence_ids"],
        **check_example(args["program"]),
    }
    candidate = python_practice(args, observation)
    assert verified_application(candidate, [observation])
    observation["stdout"] = "forged"
    candidate["questions"][1].update(answer_points=["forged"], answer="forged", rubric="forged")
    assert not verified_application(candidate, [observation])


def test_search_completes_short_missing_caption_through_authority_and_journals_window(setup):
    from lecturelens_agent.study.contracts import StudyCommand

    store, authority, runtime, scope = setup
    original = authority.read
    evidence = [
        {
            "evidence_id": name,
            "source_type": "SUBTITLE",
            "text": "Half an interval.",
            "start_ms": i * 1000,
            "end_ms": (i + 1) * 1000,
        }
        for i, name in enumerate(["left", "continuation", "right", "outside"])
    ]
    reads = []

    def read(run, action="CHECK", **args):
        assert "practice_kind" not in args  # Python owns this choice, not Java.
        reads.append((action, args))
        base = original(run)
        if action == "SEARCH":
            base["evidence"] = [evidence[0], evidence[2]]
        elif action == "WINDOW":
            base["evidence"] = [*evidence, {**evidence[1], "evidence_id": "ocr", "source_type": "OCR"}]
        elif action == "READ":
            base["evidence"] = [e for e in evidence if e["evidence_id"] in args["evidence_ids"]]
        return base

    authority.read = read

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "halving", "practice_kind": "interval_halving"},
            }
        assert len(body["evidence"]) == 3
        assert body["practice_kind"] == "interval_halving"
        return {
            "name": "report_insufficient_evidence",
            "arguments": {"reason": "No course support for the requested different topic."},
        }

    runtime.provider.decide = decide
    result = store.command(
        StudyCommand(**scope, operation="START", goal="another topic", request_key="gap"), "mock"
    )
    run = next(r for r in store.candidates() if r["run_id"] == result["run"]["run_id"])
    runtime.execute(run)
    result = store.command(StudyCommand(**scope, operation="READ"), "mock")
    assert result["run"]["status"] == "succeeded"
    with store.connect() as conn:
        search = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='search_course_evidence'",
            (run["run_id"],),
        ).fetchone()["result"]
    assert search["evidence_ids"] == ["left", "right", "continuation"]
    assert search["context_windows"] == ["left"]
    assert search["practice_kind"] == "interval_halving"
    assert len([r for r in reads if r[0] == "WINDOW"]) == 1


@pytest.mark.parametrize(
    "value,accepted",
    [
        ("prose example", False),
        (json.dumps({"lower": 0, "upper": 80, "feedback": "lower", "evidence_ids": ["caption-a"]}), True),
        (json.dumps({"answer": "invented"}), False),
    ],
)
def test_optional_object_transport_decode_is_lossless_logged_and_still_schema_checked(value, accepted):
    from lecturelens_agent.study.provider import ChatProvider, ModelResponseError

    provider = ChatProvider(base_url="http://127.0.0.1:9/v1", model="test")
    args = arguments()
    args["worked_example"] = value
    response = {"calls": [{"name": "create_interval_practice", "arguments": args}], "usage": {}}
    provider._request = lambda *a: response
    messages = [
        {
            "role": "user",
            "content": json.dumps({"history": [{"tool": "search_course_evidence"}], "evidence": []}),
        }
    ]
    if accepted:
        result = provider.decide(messages, 10)
        assert result["calls"][0]["arguments"]["worked_example"] == json.loads(value)
        assert result["protocol_repairs"] == ["worked_example_json_object"]
    else:
        with pytest.raises(ModelResponseError):
            provider.decide(messages, 10)


@pytest.mark.parametrize(
    "quote,valid", [("integer targets", True), ("", False), ("use a real target", False)]
)
def test_goal_mismatch_requires_actual_learner_words_not_reviewer_instructions(quote, valid):
    body = context()
    body["goal"] = "Use integer targets only."
    data = verdict()
    data["question_2"].update(
        issue="goal_mismatch", answer="Use integers as the learner requested.", goal_quote=quote
    )
    if valid:
        review = ComputedCourseReviewVerdict.model_validate(data, context=body).review()
        assert review.issues == ["goal_mismatch"]
        assert any(g.source == "goal" and g.quote == quote for g in review.grounds["question_2"])
    else:
        with pytest.raises(ValidationError, match="exact goal quote"):
            ComputedCourseReviewVerdict.model_validate(data, context=body)


def test_factual_audit_is_required_on_wire_private_and_not_a_verdict_override():
    body = context()
    assert all(item["source"] in {"explanation", "goal"} for item in body["source_catalog"].values())
    data = verdict()
    data["factual_check"] = "The source supports halving; the application matches that method."
    result = ComputedCourseReviewVerdict.model_validate(data, context=body).review()
    assert result.factual_check == data["factual_check"]
    assert not result.issues
    data["question_1"].update(issue="unsupported_question", answer="Use the cited halving method.")
    rejected = ComputedCourseReviewVerdict.model_validate(data, context=body).review()
    assert rejected.issues == ["unsupported_question"]
    assert rejected.factual_check == result.factual_check
    for mode in [None, "computed_application"]:
        schema = review_schema("practice", "answer_points_v1", mode)["function"]["parameters"]
        assert schema["required"][0] == "factual_check"
    data["factual_check"] = "x" * 801
    with pytest.raises(ValidationError):
        ComputedCourseReviewVerdict.model_validate(data, context=body)


def test_search_completes_only_contiguous_unfinished_speech_and_records_authority_window(setup):
    from test_study import read, start

    store, authority, runtime, _ = setup
    original = authority.read
    evidence = [
        dict(evidence_id=f"c{i}", source_type="SUBTITLE", text=text, start_ms=i * 1000, end_ms=(i + 1) * 1000)
        for i, text in enumerate(
            ["Take the elements", "starting at one and", "create a string.", "Unrelated next topic."]
        )
    ]
    reads = []

    def authority_read(run, action="CHECK", **args):
        result = original(run)
        reads.append(action)
        if action == "SEARCH":
            result["evidence"] = evidence[:1]
        elif action == "WINDOW":
            index = next(i for i, e in enumerate(evidence) if e["evidence_id"] == args["evidence_id"])
            result["evidence"] = [
                *reversed(evidence[max(0, index - 1) : index + 2]),
                {**evidence[1], "evidence_id": "ocr", "source_type": "OCR"},
            ]
        elif action == "READ":
            result["evidence"] = [e for e in evidence if e["evidence_id"] in args["evidence_ids"]]
        return result

    authority.read = authority_read

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {"name": "search_course_evidence", "arguments": {"query": "string"}}
        assert [e["text"] for e in body["evidence"]] == [e["text"] for e in evidence[:3]]
        return {
            "name": "report_insufficient_evidence",
            "arguments": {"reason": "No evidence for a different requested topic."},
        }

    runtime.provider.decide = decide
    run = start(setup)
    runtime.execute(run)
    assert read(setup)["run"]["status"] == "succeeded"
    assert reads.count("WINDOW") == 2
    with store.connect() as conn:
        result = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='search_course_evidence'",
            (run["run_id"],),
        ).fetchone()["result"]
    assert result["evidence_ids"] == ["c0", "c1", "c2"]
    assert result["context_windows"] == ["c0", "c1"]


def test_goal_mismatch_preserves_candidate_two_sources_and_goal_without_contract_overflow():
    body = context()
    body["goal"] = "Use integer-only practice."
    body["evidence"].append({"evidence_id": "e2", "text": "Discard the other half."})
    body["candidate"]["questions"][1]["evidence_ids"].append("e2")
    data = verdict()
    data["question_2"].update(
        issue="goal_mismatch",
        answer="Use integer-only practice.",
        evidence=["e1", "e2"],
        goal_quote="integer-only",
    )
    review = ComputedCourseReviewVerdict.model_validate(data, context=body).review()
    assert [q.source for q in review.grounds["question_2"]] == ["question_2.question", "e1", "e2", "goal"]
    assert review.issues == ["goal_mismatch"]


def test_computed_reviewer_view_hides_only_verified_answers_and_validates_against_original():
    from lecturelens_agent.study.provider import ChatProvider
    from lecturelens_agent.study.quality import review_wire_messages

    body = context()
    messages = [{"role": "system", "content": "Review."}, {"role": "user", "content": json.dumps(body)}]
    wire = review_wire_messages(messages)
    sent = json.loads(wire[-1]["content"])
    assert "answer" not in sent["candidate"]["questions"][1]
    assert "answer_points" not in sent["candidate"]["questions"][1]
    assert "example_checks" not in sent
    assert sent["candidate"]["questions"][0] == body["candidate"]["questions"][0]
    assert sent["candidate"]["questions"][1]["question"] == body["candidate"]["questions"][1]["question"]
    assert sent["evidence"] == body["evidence"]
    assert json.loads(messages[-1]["content"]) == body
    provider = ChatProvider("http://127.0.0.1:1", "test", "unused")

    def request(actual, schemas, timeout, max_tokens):
        assert actual == wire
        return {"calls": [{"name": "assess_study_candidate", "arguments": verdict()}], "usage": {}}

    provider._request = request
    assert not provider.review(messages, 10)["review"]["issues"]
    body["candidate"]["questions"][1]["answer_points"] = ["wrong result"]
    with pytest.raises(ValueError, match="unverified"):
        review_wire_messages([*messages[:-1], {"role": "user", "content": json.dumps(body)}])


@pytest.mark.parametrize("kind", ["interval", "sequence"])
@pytest.mark.parametrize("language", ["en", "zh"])
def test_worked_solution_view_preserves_unverified_prose_and_rejects_changed_proofs(kind, language):
    from copy import deepcopy

    from test_study_sequences import arguments as sequence_arguments

    from lecturelens_agent.study.quality import review_wire_messages
    from lecturelens_agent.study.sequences import sequence_practice

    args = arguments() if kind == "interval" else sequence_arguments()
    args["language"] = language
    # Long prose crosses catalog boundaries; it must stay visible even when it
    # contains a numerical error or a claim resembling a computed solution.
    args["explanation"] = "Unverified claim: the answer is 999. " * 8
    args["worked_example"] = dict(args["application"])
    compile_practice = interval_practice if kind == "interval" else sequence_practice
    candidate, observation = compile_practice(args)
    messages = review_messages(
        "Explain the requested example.",
        candidate,
        [{"evidence_id": "caption-a", "text": "The course teaches this method."}],
        example_checks=[observation],
    )
    original = deepcopy(messages)
    wire = json.loads(review_wire_messages(messages)[-1]["content"])
    assert wire["candidate"]["explanation"] == args["explanation"]
    assert wire["verified_worked_example"]["evidence_ids"] == ["e1"]
    assert "999" in wire["source_catalog"]["explanation:1"]["quote"]
    assert (
        "".join(item["quote"] for item in wire["source_catalog"].values() if item["source"] == "explanation")
        == args["explanation"]
    )
    assert messages == original
    assert (
        not ComputedCourseReviewVerdict.model_validate(verdict(), context=json.loads(messages[-1]["content"]))
        .review()
        .issues
    )
    body = json.loads(messages[-1]["content"])
    for mutation in ("text", "problem", "citation"):
        changed = deepcopy(body)
        if mutation == "text":
            changed["candidate"]["explanation"] += " Wrong extra claim."
        elif mutation == "problem":
            problem = changed["example_checks"][0]["worked_example"]["problem"]
            problem["upper" if kind == "interval" else "passes"] = 1
        else:
            changed["example_checks"][0]["worked_example"]["problem"]["evidence_ids"] = ["foreign"]
        result = json.loads(
            review_wire_messages([*messages[:-1], {"role": "user", "content": json.dumps(changed)}])[-1][
                "content"
            ]
        )
        assert "verified_worked_example" not in result
        assert result["candidate"]["explanation"] == changed["candidate"]["explanation"]
