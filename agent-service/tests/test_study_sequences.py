import json
from copy import deepcopy

import pytest
import test_study
from pydantic import ValidationError
from test_study_answer_points import draft

from lecturelens_agent.study.contracts import SequenceExample, StudyCommand, tool_schemas
from lecturelens_agent.study.quality import verified_application
from lecturelens_agent.study.sequences import sequence_practice

setup = test_study.setup


def arguments():
    base = draft()
    return {
        **{key: base[key] for key in ("title", "explanation", "evidence_ids")},
        "language": "en",
        "concept": base["questions"][0],
        "application": {
            "values": [8, 2, 4, 9, 3],
            "passes": 2,
            "method": "largest_to_right",
            "evidence_ids": ["caption-a"],
        },
    }


@pytest.mark.parametrize(
    "method,expected,regions",
    [
        ("largest_to_right", [[8, 2, 4, 3, 9], [3, 2, 4, 8, 9]], [[9], [8, 9]]),
        ("smallest_to_left", [[2, 8, 4, 9, 3], [2, 3, 4, 9, 8]], [[2], [2, 3]]),
    ],
)
@pytest.mark.parametrize("language", ["en", "zh"])
def test_each_pass_preserves_unsorted_elements_and_computes_the_correct_sorted_region(
    method, expected, regions, language
):
    args = arguments()
    args["application"]["method"] = method
    args["language"] = language
    original = deepcopy(args)
    artifact, result = sequence_practice(args)
    assert [step["array"] for step in result["application"]["states"]] == expected
    assert [step["sorted_region"] for step in result["application"]["states"]] == regions
    assert artifact["questions"][1]["answer"] == artifact["questions"][1]["rubric"]
    assert verified_application(artifact, [result])
    assert args == original
    artifact["questions"][1]["answer_points"][-1] = "Fully sorted already"
    assert not verified_application(artifact, [result])


@pytest.mark.parametrize(
    "change",
    [
        {"values": [1, 1, 2]},
        {"values": list(range(9))},
        {"values": [0, 1000]},
        {"passes": 0},
        {"passes": 4},
        {"values": [1, 2], "passes": 2},
        {"method": "invented"},
        {"answer": "invented"},
    ],
)
def test_sequence_problem_is_bounded_and_cannot_contain_guessed_results(change):
    data = {**arguments()["application"], **change}
    with pytest.raises(ValidationError):
        SequenceExample.model_validate(data)


def test_worked_array_has_own_citations_and_uses_the_requested_method_without_mutation():
    args = arguments()
    args["worked_example"] = {**args["application"], "values": [6, 2, 9, 5], "evidence_ids": ["caption-b"]}
    artifact, observation = sequence_practice(args)
    assert "[5, 2, 6, 9]" in artifact["explanation"]
    assert "caption-b" in artifact["evidence_ids"]
    assert "caption-b" not in artifact["questions"][1]["evidence_ids"]
    assert observation["worked_example"]["states"][-1]["array"] == [5, 2, 6, 9]
    schema = next(
        t["function"]["parameters"]
        for t in tool_schemas()
        if t["function"]["name"] == "create_sequence_practice"
    )
    assert schema["properties"]["worked_example"]["type"] == ["object", "null"]


@pytest.mark.parametrize("crash,foreign", [(False, False), (True, False), (False, True)])
@pytest.mark.parametrize("structured", [False, True])
def test_sequence_runtime_keeps_private_answers_checks_ownership_and_replays_committed_computation(
    setup, monkeypatch, crash, foreign, structured
):
    import lecturelens_agent.study.runtime as module

    store, _, runtime, scope = setup
    original = module.sequence_practice
    calls = []

    def compute(args):
        calls.append(args)
        return original(args)

    monkeypatch.setattr(module, "sequence_practice", compute)

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "selection", "practice_kind": "selection_steps"},
            }
        args = arguments()
        if structured:
            args.pop("explanation")
            args["concept"] = {"skill": "boundary", "evidence_ids": ["e1"]}
        args["evidence_ids"] = args["concept"]["evidence_ids"] = ["e1"]
        args["application"]["evidence_ids"] = ["foreign" if foreign else "e1"]
        return {"name": "create_sequence_practice", "arguments": args}

    runtime.provider.decide = decide
    run = test_study.start(setup)
    save = store.save_tool
    if crash:

        def after_commit(*args, **kwargs):
            result = save(*args, **kwargs)
            if result.get("artifact_id"):
                store.save_tool = save
                raise SystemExit("after commit")
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
        assert "After pass" not in json.dumps(result, default=str)
        answer = store.command(StudyCommand(**scope, operation="ANSWERS"), "mock")["questions"][1]
        assert "[3, 2, 4, 8, 9]" in answer["answer"]


@pytest.mark.parametrize("method", ["largest_to_right", "smallest_to_left"])
@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("skill", ["boundary", "placement", "progress"])
def test_structured_method_explanation_and_concept_follow_selected_direction(method, language, skill):
    args = arguments()
    args.pop("explanation")
    args["language"] = language
    args["concept"] = {"skill": skill, "evidence_ids": ["own-method"]}
    args["application"]["method"] = method
    artifact, result = sequence_practice(args)
    text = artifact["explanation"]
    if language == "en":
        assert (
            "maximum in the unsorted prefix"
            if method == "largest_to_right"
            else "minimum in the unsorted suffix"
        ) in text
    else:
        assert ("未排序前缀中找最大值" if method == "largest_to_right" else "未排序后缀中找最小值") in text
    assert artifact["questions"][0]["evidence_ids"] == ["own-method"]
    assert "own-method" not in artifact["questions"][1]["evidence_ids"]
    assert verified_application(artifact, [result])
    assert all(q["answer"] == q["rubric"] for q in artifact["questions"])


def test_structured_sequence_rejects_free_override_or_conflicting_example_method():
    from lecturelens_agent.study.contracts import SequencePracticeArgs

    args = arguments()
    args["concept"] = {"skill": "progress", "evidence_ids": ["own"]}
    with pytest.raises(ValidationError):
        SequencePracticeArgs.model_validate(args)
    args.pop("explanation")
    args["worked_example"] = {**args["application"], "method": "smallest_to_left"}
    with pytest.raises(ValidationError):
        SequencePracticeArgs.model_validate(args)
    schema = next(
        t["function"]["parameters"]
        for t in tool_schemas()
        if t["function"]["name"] == "create_sequence_practice"
    )
    assert "explanation" not in schema["properties"]
    assert "AnswerPointsQuestion" not in schema["$defs"]
