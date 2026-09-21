import copy
import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_answer_points import draft

from lecturelens_agent.study.contracts import PythonPracticeArgs, StudyCommand, python_practice
from lecturelens_agent.study.examples import check_example

setup = test_study.setup


def arguments():
    data = draft()
    return {
        **{key: data[key] for key in ("title", "explanation", "evidence_ids")},
        "language": "en",
        "concept": data["questions"][0],
        "program": "s = 'world'\nprint(s[:2] + s[3:])\nprint(s[:2] + s[3:])",
        "program_evidence_ids": ["caption-a"],
    }


def test_exact_program_produces_question_answer_and_rubric_with_repeated_lines():
    args = arguments()
    artifact = python_practice(args, check_example(args["program"]))
    question = artifact["questions"][1]
    assert args["program"] in question["question"]
    assert question["answer"] == question["rubric"] == "wold\nwold\n"
    assert "word" not in question["answer"]
    assert question["evidence_ids"] == args["program_evidence_ids"]
    args["answer"] = "word"
    with pytest.raises(ValidationError):
        PythonPracticeArgs.model_validate(args)


@pytest.mark.parametrize(
    "program", ["print('x')\nimport os", "s='world'", "print(1/0)", "print('x'*256)\nprint('y'*256)"]
)
def test_partial_unsupported_empty_error_and_large_output_cannot_be_published(program):
    args = arguments() | {"program": program}
    with pytest.raises(ValueError):
        python_practice(args, check_example(program))


@pytest.mark.parametrize("crash", [False, True])
@pytest.mark.parametrize("string_mode", [False, True])
def test_real_pg_computed_practice_is_authorized_private_and_replayed_once(
    setup, monkeypatch, crash, string_mode
):
    import lecturelens_agent.study.runtime as module

    store, _, runtime, scope = setup
    computations = []
    original_check = module.check_example

    def compute(program):
        computations.append(program)
        return original_check(program)

    monkeypatch.setattr(module, "check_example", compute)

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {"name": "search_course_evidence", "arguments": {"query": "strings"}}
        args = arguments()
        if string_mode:
            args.pop("explanation")
            args["concept"] = {"skill": "rebinding", "evidence_ids": ["e1"]}
            args.pop("program")
            args["program_plan"] = {
                "initial": "world",
                "rebindings": [
                    {"operation": "prefix_slice", "value": "wo", "start": 3},
                    {"operation": "prefix_slice", "value": "wo", "start": 2},
                ],
                "print_positions": [1, 2],
            }
        args["evidence_ids"] = args["concept"]["evidence_ids"] = args["program_evidence_ids"] = ["e1"]
        return {"name": "create_python_practice", "arguments": args}

    original_review = runtime.provider.review

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        assert body["example_checks"][0]["stdout"] == "wold\nwold\n"
        assert body["candidate"]["questions"][1]["answer"] == "wold\nwold\n"
        return original_review(messages, timeout)

    runtime.provider.decide, runtime.provider.review = decide, review
    run = test_study.start(setup)
    original_save = store.save_tool
    if crash:

        def save(*args, **kwargs):
            result = original_save(*args, **kwargs)
            if result.get("artifact_id"):
                store.save_tool = original_save
                raise SystemExit("after committed artifact")
            return result

        store.save_tool = save
        with pytest.raises(SystemExit):
            runtime.execute(run)
    runtime.execute(run)
    public = test_study.read(setup)
    assert public["run"]["status"] == "succeeded"
    assert len(computations) == 1
    assert "wold" not in json.dumps(public, default=str)
    private = store.command(StudyCommand(**scope, operation="ANSWERS"), "mock")
    assert private["questions"][1]["answer"] == "wold\nwold\n"
    assert "wold" not in json.dumps(test_study.read(setup, "EVENTS"), default=str)
    if string_mode:
        with store.connect() as connection:
            recorded = connection.execute(
                "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='create_python_practice'",
                (run["run_id"],),
            ).fetchone()["result"]
        assert recorded["program_plan"]["print_positions"] == [1, 2]
        assert recorded["program_plan"]["rebindings"][1]["start"] == 2


def test_computed_practice_rejects_foreign_program_evidence_before_calculation(setup, monkeypatch):
    import lecturelens_agent.study.runtime as module

    _, _, runtime, _ = setup
    original = runtime.provider.decide
    computed = []
    monkeypatch.setattr(module, "check_example", lambda code: computed.append(code))

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return original(messages, timeout)
        args = copy.deepcopy(arguments())
        args["evidence_ids"] = args["concept"]["evidence_ids"] = ["e1"]
        args["program_evidence_ids"] = ["foreign"]
        return {"name": "create_python_practice", "arguments": args}

    runtime.provider.decide = decide
    runtime.execute(test_study.start(setup))
    assert test_study.read(setup)["run"]["error_code"] == "UNSUPPORTED_CITATION"
    assert not computed


def test_computed_practice_real_protocol_repairs_within_original_budget(setup):
    store, _, runtime, scope = setup
    reviews = []

    class Provider:
        mode = "real"

        def decide(self, messages, timeout):
            body = json.loads(messages[-1]["content"])
            if not body["evidence"]:
                return {"name": "search_course_evidence", "arguments": {"query": "strings"}}
            data = arguments()
            data["evidence_ids"] = data["concept"]["evidence_ids"] = data["program_evidence_ids"] = ["e1"]
            if body.get("quality"):
                data["explanation"] = "Corrected explanation with source support."
            return {"name": "create_python_practice", "arguments": data}

        def review(self, messages, timeout):
            body = json.loads(messages[-1]["content"])
            assert body["review_mode"] == "field_support_computed_goals_v1"
            assert body["example_checks"][0]["stdout"] == "wold\nwold\n"
            reviews.append(body)
            return {
                "review": {
                    "issues": ["unsupported_explanation"] if len(reviews) == 1 else [],
                    "feedback": "Correct the explanation from its course citations.",
                }
            }

    runtime.provider = Provider()
    result = store.command(
        StudyCommand(**scope, operation="START", request_key="computed-real", goal="Explain strings"), "real"
    )
    run = next(r for r in store.candidates() if r["run_id"] == result["run"]["run_id"])
    runtime.execute(run)
    result = store.command(StudyCommand(**scope, operation="READ"), "real")
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == 5
    assert result["run"]["tool_calls"] == 3
    assert len(reviews) == 2


@pytest.mark.parametrize("language", ["en", "zh"])
@pytest.mark.parametrize("skill", ["immutability", "rebinding"])
def test_string_scaffold_preserves_own_sources_and_computed_program(language, skill):
    args = arguments()
    args.pop("explanation")
    args.update(language=language, concept={"skill": skill, "evidence_ids": ["concept-only"]})
    artifact = python_practice(args, check_example(args["program"]))
    assert artifact["evidence_ids"] == args["evidence_ids"]
    assert artifact["questions"][0]["evidence_ids"] == ["concept-only"]
    assert artifact["questions"][1]["evidence_ids"] == args["program_evidence_ids"]
    assert artifact["questions"][1]["answer"] == "wold\nwold\n"
    assert all(q["answer"] == q["rubric"] for q in artifact["questions"])
    for claim in ("TypeError", "memory", "内存", "garbage"):
        assert claim not in json.dumps(artifact, ensure_ascii=False)
    args["explanation"] = "An unsolicited error-class or memory-lifetime assertion."
    with pytest.raises(ValidationError):
        PythonPracticeArgs.model_validate(args)


def test_string_schema_selected_by_model_search_kind_preserves_general_python():
    from lecturelens_agent.study.provider import decision_schemas

    def schema(kind):
        messages = [
            {"role": "user", "content": json.dumps({"goal": "Explain course code"})},
            {"role": "tool", "content": json.dumps({"practice_kind": kind})},
        ]
        return next(
            t["function"]["parameters"]
            for t in decision_schemas(messages)
            if t["function"]["name"] == "create_python_practice"
        )

    structured = schema("python_strings")
    assert "explanation" not in structured["properties"]
    assert "AnswerPointsQuestion" not in structured["$defs"]
    assert structured["properties"]["concept"] == {"$ref": "#/$defs/StringConcept"}
    general = schema("python_strings_or_code")
    assert "explanation" in general["required"]
    assert "StringConcept" not in general["$defs"]
    with pytest.raises(ValidationError):
        PythonPracticeArgs.model_validate({**arguments(), "explanation": ""})


@pytest.mark.parametrize(
    "initial,prefix,expected",
    [
        ("z", "Q", "z\nQ\n"),
        ("red blue", "X", "red blue\nXed blue\n"),
        ("你好", "世", "你好\n世好\n"),
        ("'\\x", "!", "'\\x\n!\\x\n"),
    ],
)
def test_string_plan_literals_are_data_and_outputs_follow_state_order(initial, prefix, expected):
    from lecturelens_agent.study.strings import render_string_program

    program = render_string_program(
        {
            "initial": initial,
            "rebindings": [{"operation": "prefix_slice", "value": prefix}],
            "print_positions": [0, 1],
        }
    )
    assert check_example(program)["stdout"] == expected


@pytest.mark.parametrize(
    "change",
    [
        {"variable": "print"},
        {"variable": "for"},
        {"variable": "s;import os"},
        {"print_positions": [1]},
        {"print_positions": [0, 0]},
        {"print_positions": [True]},
        {"rebindings": [{"operation": "upper", "value": ""}]},
        {"initial": "x" * 41},
    ],
)
def test_string_plan_rejects_unbounded_or_ambiguous_operations(change):
    from lecturelens_agent.study.strings import render_string_program

    with pytest.raises(ValidationError):
        render_string_program({"initial": "x", "rebindings": [], "print_positions": [0], **change})


def test_string_plan_provider_validates_then_preserves_the_original_plan():
    from lecturelens_agent.study.provider import ChatProvider, ModelResponseError

    provider = ChatProvider("http://127.0.0.1:1", "qwen3-max", "")
    args = arguments()
    args.pop("program")
    args.pop("explanation")
    args["concept"] = {"skill": "rebinding", "evidence_ids": ["e1"]}
    args["program_plan"] = {"initial": "x", "rebindings": [], "print_positions": [0]}
    provider._request = lambda *unused: {
        "calls": [{"name": "create_python_practice", "arguments": copy.deepcopy(args)}],
        "usage": {},
    }
    messages = [
        {"role": "user", "content": json.dumps({"goal": "string output"})},
        {"role": "tool", "content": json.dumps({"practice_kind": "python_strings"})},
    ]
    result = provider.decide(messages, 1)
    assert result["calls"][0]["arguments"]["program_plan"] == args["program_plan"]
    assert "program" not in result["calls"][0]["arguments"]
    args.pop("program_plan")
    args["program"] = "s='x'\nprint(s)"
    with pytest.raises(ModelResponseError) as caught:
        provider.decide(messages, 1)
    assert caught.value.diagnostics["reason"] == "string_program_plan_required"
