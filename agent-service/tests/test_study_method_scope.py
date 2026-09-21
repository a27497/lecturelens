import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_answer_points import draft
from test_study_support_review import accepted, messages

from lecturelens_agent.study.context import build_messages
from lecturelens_agent.study.provider import decision_schemas
from lecturelens_agent.study.quality import review_messages, review_schema, review_wire_messages
from lecturelens_agent.study.support_review import (
    FieldSupportVerdict,
    MethodCoverageVerdict,
    ScopedFieldSupportVerdict,
)

setup = test_study.setup


def observation():
    return {
        "operation": "Check the returned value",
        "input": "Function call",
        "output": "Returned value",
        "evidence_id": "e2",
        "quote": "The two print statements print inner and None.",
    }


def test_method_observation_requires_actual_quoted_source_and_stays_candidate_blind():
    request = review_messages(
        "Practice returning values",
        {"kind": "insufficient_evidence", "reason": "HIDDEN CANDIDATE"},
        [{"evidence_id": "source", "text": "Without return, the result is None."}],
        structured_support=True,
        observe_methods=True,
    )
    body = json.loads(request[-1]["content"])
    assert body["review_mode"] == "course_methods_v1"
    assert "HIDDEN CANDIDATE" not in json.dumps(review_wire_messages(request))
    method = {**{k: v for k, v in observation().items() if k != "quote"}, "evidence_id": "e1"}
    data = {
        "course_fact": "Default return value",
        "evidence_ids": ["e1"],
        "support": "direct",
        "missing_goal_quote": "",
        "methods": [method],
    }
    result = MethodCoverageVerdict.model_validate(data, context=body).review()
    assert result.method_observations[0].quote == "Without return, the result is None."
    for defect in [{"quote": "Invented course statement"}, {"evidence_id": "unseen"}, {"quote": "   "}]:
        bad = {**data, "methods": [{**method, **defect}]}
        with pytest.raises(ValidationError):
            MethodCoverageVerdict.model_validate(bad, context=body)
    with pytest.raises(ValidationError):
        MethodCoverageVerdict.model_validate({**data, "methods": []}, context=body)


def test_scope_mismatch_cannot_be_accepted_or_hidden_by_correct_mathematics():
    body = json.loads(messages()[-1]["content"])
    body["application_method"] = observation()
    data = accepted(body)
    data["checks"][2]["method_alignment"] = {
        "operation": "Classify all functions",
        "output": "General classification",
        "matches": False,
    }
    with pytest.raises(ValidationError):
        FieldSupportVerdict.model_validate(data, context=body)
    data["checks"][2].update(issue="unsupported_question", correction="Use the demonstrated value check.")
    result = FieldSupportVerdict.model_validate(data, context=body).review()
    assert result.issues == ["unsupported_question"]
    assert result.method_assessment.output == "General classification"
    assert result.answer_observations[1].matches_reference  # Correctness does not erase scope failure.
    del data["checks"][2]["answer_check"]
    result = FieldSupportVerdict.model_validate(data, context=body).review()
    assert result.issues == ["unsupported_question"]
    assert len(result.answer_observations) == 1  # A rejected unsupported task need not be solved.
    del data["checks"][2]["method_alignment"]
    with pytest.raises(ValidationError):
        FieldSupportVerdict.model_validate(data, context=body)


def test_method_source_cannot_be_borrowed_from_another_field():
    body = json.loads(messages()[-1]["content"])
    body["application_method"] = {
        **observation(),
        "evidence_id": "e1",
        "quote": "Without return, the result is None.",
    }
    with pytest.raises(ValueError, match="own source"):
        accepted(body)


def test_scoped_wire_contract_always_requires_one_top_level_method_check():
    body = json.loads(messages()[-1]["content"])
    body.update(review_mode="field_support_scoped_v1", application_method=observation())
    data = accepted(body)
    method_check = data["checks"][2].pop("method_alignment")
    schema = review_schema("practice", "answer_points_v1", "field_support_scoped_v1")["function"][
        "parameters"
    ]
    assert "application_method_check" in schema["required"]
    assert "method_alignment" not in schema["$defs"]["FieldCheck"]["properties"]
    with pytest.raises(ValidationError):
        ScopedFieldSupportVerdict.model_validate(data, context=body)
    data["application_method_check"] = method_check
    result = ScopedFieldSupportVerdict.model_validate(data, context=body).review()
    assert result.method_assessment.matches and result.issues == []


def test_window_refresh_replaces_method_choices_and_new_search_clears_them():
    evidence = [{"evidence_id": "source", "text": "Source", "start_ms": 0, "end_ms": 1}]
    method = {**observation(), "evidence_id": "source"}
    history = [
        {
            "tool": "search_course_evidence",
            "arguments": {},
            "result": {"practice_kind": "general", "course_coverage": {"methods": {"m1": method}}},
        },
        {
            "tool": "read_evidence_window",
            "arguments": {"evidence_id": "source"},
            "result": {"course_coverage": {"methods": {"m2": method}}},
        },
    ]
    wire, _ = build_messages("system", "goal", evidence, history, [])
    context = json.loads(wire[-1]["content"])
    assert list(context["course_coverage"]["methods"]) == ["m2"]
    assert context["course_coverage"]["methods"]["m2"]["evidence_id"] == "e1"
    params = next(
        s["function"]["parameters"]
        for s in decision_schemas(wire)
        if s["function"]["name"] == "create_practice_set"
    )
    assert params["properties"]["method_id"]["enum"] == ["m2"]
    assert "method_id" in params["required"]
    history.append(
        {
            "tool": "search_course_evidence",
            "arguments": {},
            "result": {"practice_kind": "general", "course_coverage": {"methods": {}}},
        }
    )
    wire, _ = build_messages("system", "goal", evidence, history, [])
    assert "create_practice_set" not in [s["function"]["name"] for s in decision_schemas(wire)]
    history[-1]["result"] = {"practice_kind": "python_strings"}
    wire, _ = build_messages("system", "goal", evidence, history, [])
    assert "course_coverage" not in json.loads(wire[-1]["content"])


@pytest.mark.parametrize("selected", ["m1", "m2", None])
def test_runtime_binds_only_observed_method_and_keeps_plan_private(setup, selected):
    store, _, runtime, _ = setup

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        if not context["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "stopping", "practice_kind": "general"},
            }
        assert list(context["course_coverage"]["methods"]) == ["m1"]
        value = draft()
        for field in [value, *value["questions"]]:
            field["evidence_ids"] = ["e1"]
        return {
            "name": "create_practice_set",
            "arguments": {
                **{k: value[k] for k in ("title", "explanation", "evidence_ids")},
                "concept": value["questions"][0],
                "application": value["questions"][1],
                "method_id": selected,
            },
        }

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if body["review_mode"] == "course_methods_v1":
            data = {
                "course_fact": "Stopping condition",
                "evidence_ids": ["e1"],
                "support": "direct",
                "missing_goal_quote": "",
                "methods": [
                    {
                        **{k: v for k, v in observation().items() if k != "quote"},
                        "evidence_id": "e1",
                    }
                ],
            }
            result = MethodCoverageVerdict.model_validate(data, context=body).review()
        else:
            assert body["application_method"]["quote"] == "An algorithm needs a stopping condition."
            result = FieldSupportVerdict.model_validate(accepted(body), context=body).review()
        return {"review": result.model_dump()}

    runtime.provider.decide, runtime.provider.review = decide, review
    run = test_study.start(setup)
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == ("succeeded" if selected == "m1" else "failed")
    assert bool(result["artifact"]) == (selected == "m1")
    if selected != "m1":
        assert result["run"]["error_code"] == "APPLICATION_METHOD_REQUIRED"
    assert "method_assessment" not in json.dumps(test_study.read(setup, "EVENTS"))
    if selected == "m1":
        with store.connect() as conn:
            records = conn.execute(
                "SELECT result FROM study_tool_result WHERE run_id=%s", (run["run_id"],)
            ).fetchall()
        assert "application_method" in json.dumps(records)
        assert "method_assessment" in json.dumps(records)
