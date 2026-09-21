import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_answer_points import draft

from lecturelens_agent.study.contracts import IntervalPracticeArgs, StudyCommand
from lecturelens_agent.study.intervals import interval_practice

setup = test_study.setup


def arguments():
    base = draft()
    return {
        **{key: base[key] for key in ("title", "explanation", "evidence_ids")},
        "language": "en",
        "concept": base["questions"][0],
        "application": {"lower": -8, "upper": 24, "feedback": "higher", "evidence_ids": ["caption-a"]},
    }


@pytest.mark.parametrize(
    "lower,upper,feedback,interval,midpoint",
    [
        (-8, 24, "higher", "(8, 24]", 16),
        (-8, 24, "lower", "[-8, 8)", 0),
        (-7, 6, "higher", "(-0.5, 6]", 2.75),
        (-7, 6, "lower", "[-7, -0.5)", -3.75),
    ],
)
def test_strict_real_bounds_and_midpoints_are_exact_without_implicit_rounding(
    lower, upper, feedback, interval, midpoint
):
    args = arguments()
    args["application"].update(lower=lower, upper=upper, feedback=feedback)
    artifact, observation = interval_practice(args)
    q = artifact["questions"][1]
    assert "real number" in q["question"]
    assert q["answer"] == q["rubric"]
    assert interval in q["answer"]
    assert observation["application"]["next_midpoint"] == midpoint
    assert observation["application"]["remaining_interval"] == interval


def test_worked_example_has_own_citations_and_preserves_requested_application_conditions():
    args = arguments()
    args["worked_example"] = {"lower": 0, "upper": 80, "feedback": "lower", "evidence_ids": ["caption-b"]}
    artifact, observation = interval_practice(args)
    assert "[0, 40)" in artifact["explanation"]
    assert "caption-b" in artifact["evidence_ids"]
    assert observation["worked_example"]["next_midpoint"] == 20
    assert "16" not in artifact["questions"][1]["question"]
    args["worked_example"] = dict(args["application"])
    changed, computed = interval_practice(args)
    assert computed["worked_example"]["problem"]["feedback"] == "higher"
    assert computed["application"]["problem"]["feedback"] == "higher"
    assert "variation" not in computed
    assert computed["application"]["problem"] == args["application"]
    assert "(8, 24]" in changed["questions"][1]["answer"]
    assert changed["questions"][1]["answer"] != changed["explanation"]
    assert args["application"] == args["worked_example"]  # Input is not mutated.


def test_large_bounds_keep_fractional_midpoint_in_the_published_answer():
    args = arguments()
    args["application"].update(lower=999998, upper=1000000)
    artifact, observation = interval_practice(args)
    assert observation["application"]["next_midpoint"] == 999999.5
    assert "= 999999.5." in artifact["questions"][1]["answer"]


@pytest.mark.parametrize(
    "changes",
    [{"upper": -8}, {"lower": 25}, {"upper": 1000001}, {"feedback": "equal"}, {"answer": "invented"}],
)
def test_invalid_or_unbounded_conditions_and_model_supplied_output_are_rejected(changes):
    args = arguments()
    args["application"].update(changes)
    with pytest.raises(ValidationError):
        IntervalPracticeArgs.model_validate(args)


@pytest.mark.parametrize("crash,foreign", [(False, False), (True, False), (False, True)])
def test_interval_tool_keeps_scope_answers_private_and_replays_committed_result(
    setup, monkeypatch, crash, foreign
):
    import lecturelens_agent.study.runtime as module

    store, _, runtime, scope = setup
    calls = []
    original = module.interval_practice

    def compute(args, evidence=None):
        calls.append(args)
        return original(args, evidence)

    monkeypatch.setattr(module, "interval_practice", compute)

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {"name": "search_course_evidence", "arguments": {"query": "halving intervals"}}
        args = arguments()
        args["evidence_ids"] = args["concept"]["evidence_ids"] = ["e1"]
        args["application"]["evidence_ids"] = ["foreign" if foreign else "e1"]
        return {"name": "create_interval_practice", "arguments": args}

    original_review = runtime.provider.review

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        assert body["example_checks"][0]["application"]["next_midpoint"] == 16
        return original_review(messages, timeout)

    runtime.provider.decide, runtime.provider.review = decide, review
    run = test_study.start(setup)
    save = store.save_tool
    if crash:

        def after_commit(*args, **kwargs):
            result = save(*args, **kwargs)
            if result.get("artifact_id"):
                store.save_tool = save
                raise SystemExit("after artifact commit")
            return result

        store.save_tool = after_commit
        with pytest.raises(SystemExit):
            runtime.execute(run)
    runtime.execute(run)
    result = test_study.read(setup)
    if foreign:
        assert result["run"]["error_code"] == "UNSUPPORTED_CITATION" and not calls
    else:
        assert result["run"]["status"] == "succeeded" and len(calls) == 1
        assert "Next midpoint:" not in json.dumps(result, default=str)
        answer = store.command(StudyCommand(**scope, operation="ANSWERS"), "mock")["questions"][1]
        assert "(8 + 24) / 2 = 16" in answer["answer"]


@pytest.mark.parametrize("feedback", ["higher", "lower"])
def test_identical_requested_examples_keep_conditions_and_proof(feedback):
    from lecturelens_agent.study.quality import verified_application

    args = arguments()
    args["application"]["feedback"] = feedback
    args["worked_example"] = dict(args["application"])
    artifact, observation = interval_practice(args)
    assert observation["worked_example"]["problem"]["feedback"] == feedback
    assert observation["application"]["problem"]["feedback"] == feedback
    assert "variation" not in observation
    assert verified_application(artifact, [observation])
    assert ("[-8, 8)" if feedback == "lower" else "(8, 24]") in artifact["questions"][1]["answer"]
    assert args["application"] == args["worked_example"]


def test_focused_interval_explanation_uses_computed_example_and_exact_observed_result_quote():
    from lecturelens_agent.study.contracts import tool_schemas
    from lecturelens_agent.study.quality import verified_application, verified_worked_example

    args = arguments()
    args.pop("explanation")
    args.update(focus="compare_sequential", reported_evidence_ids=["result-source"])
    args["worked_example"] = dict(args["application"])
    quote = "This trial took 7 guesses, compared with 83 sequential guesses."
    candidate, observation = interval_practice(args, [{"evidence_id": "result-source", "text": quote}])
    assert quote in candidate["explanation"]
    assert "result-source" in candidate["evidence_ids"]
    assert verified_application(candidate, [observation])
    assert verified_worked_example(candidate, [observation])
    assert observation["application"]["problem"] == args["application"]
    with pytest.raises(ValueError, match="authoritative"):
        interval_practice(args, [{"evidence_id": "unrelated", "text": quote}])
    args["explanation"] = "Invent a different numerical answer."
    with pytest.raises(ValidationError, match="omit free prose"):
        interval_practice(args)
    args.pop("explanation")
    args["reported_evidence_ids"] = []
    with pytest.raises(ValidationError, match="requires cited"):
        interval_practice(args)
    args["focus"] = "halving"
    candidate, _ = interval_practice(args)
    assert quote not in candidate["explanation"]
    schema = next(
        t["function"]["parameters"]
        for t in tool_schemas()
        if t["function"]["name"] == "create_interval_practice"
    )
    assert "explanation" not in schema["properties"]
    assert "focus" in schema["required"]
    assert "legacy" not in schema["properties"]["focus"]["enum"]


@pytest.mark.parametrize("foreign", [False, True])
def test_reported_result_passage_obeys_runtime_authority_and_persists_exact_quote(setup, foreign):
    from test_study import read, start

    store, authority, runtime, _ = setup
    original = authority.read
    quote = "The measured comparison was 7 guesses against 83 guesses."

    def observed(run, action="CHECK", **kwargs):
        result = original(run, action, **kwargs)
        for item in result.get("evidence", []):
            item["text"] = quote
            if item["evidence_id"] in {"e1", "e2"}:
                item["evidence_id"] = "canonical-" + item["evidence_id"]
        return result

    authority.read = observed

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "Compare guessing", "practice_kind": "interval_halving"},
            }
        args = arguments()
        args.pop("explanation")
        args["evidence_ids"] = args["concept"]["evidence_ids"] = args["application"]["evidence_ids"] = ["e1"]
        args["concept"] = {"skill": "compare_methods", "evidence_ids": ["e1"]}
        args.update(focus="compare_sequential", reported_evidence_ids=["foreign" if foreign else "e1"])
        return {"name": "create_interval_practice", "arguments": args}

    runtime.provider.decide = decide
    run = start(setup)
    runtime.execute(run)
    output = read(setup)
    if foreign:
        assert output["run"]["error_code"] == "UNSUPPORTED_CITATION"
        assert not output["artifact"]
    else:
        assert output["run"]["status"] == "succeeded"
        assert quote in output["artifact"]["explanation"]
        assert "canonical-e1" in output["artifact"]["evidence_ids"]
        assert all("answer" not in q for q in output["artifact"]["questions"])


@pytest.mark.parametrize("skill", ["midpoint_reason", "feedback_role", "compare_methods"])
@pytest.mark.parametrize("language", ["en", "zh"])
def test_interval_concept_choice_is_distinct_from_numeric_application_and_shares_its_rubric(skill, language):
    from lecturelens_agent.study.contracts import tool_schemas

    args = arguments()
    args.update(language=language, concept={"skill": skill, "evidence_ids": ["caption-b"]})
    candidate, _ = interval_practice(args)
    concept, application = candidate["questions"]
    assert concept["answer"] == concept["rubric"]
    assert concept["evidence_ids"] == ["caption-b"]
    assert application["evidence_ids"] == ["caption-a"]
    assert not any(c.isdigit() for c in concept["question"] + concept["answer"])
    assert any(c.isdigit() for c in application["question"])
    schema = next(
        t["function"]["parameters"]
        for t in tool_schemas()
        if t["function"]["name"] == "create_interval_practice"
    )
    assert schema["properties"]["concept"] == {"$ref": "#/$defs/HalvingConcept"}
    assert "AnswerPointsQuestion" not in schema["$defs"]


@pytest.mark.parametrize(
    "change",
    [{"skill": "invent_midpoint"}, {"answer_points": ["51 to 100 has midpoint 75"]}, {"evidence_ids": []}],
)
def test_interval_concept_rejects_unknown_skill_or_answer_override(change):
    args = arguments()
    args["concept"] = {"skill": "midpoint_reason", "evidence_ids": ["caption-a"], **change}
    with pytest.raises(ValidationError):
        interval_practice(args)
