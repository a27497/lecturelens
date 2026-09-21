import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_answer_points import draft

from lecturelens_agent.study.contracts import GenericPracticeArgs, StudyCommand, materialize_practice
from lecturelens_agent.study.provider import decision_schemas

setup = test_study.setup


def arguments():
    base = draft()
    return {
        **{key: base[key] for key in ("title", "explanation", "evidence_ids")},
        "concept": base["questions"][0],
        "cost_scenario": "repeated_lookups",
        "language": "en",
        "application_evidence_ids": ["caption-a"],
    }


@pytest.mark.parametrize("scenario", ["single_lookup", "repeated_lookups"])
@pytest.mark.parametrize("language", ["en", "zh"])
def test_cost_mode_preserves_asymptotic_costs_without_invented_numbers(scenario, language):
    args = arguments()
    args.update(cost_scenario=scenario, language=language)
    candidate = materialize_practice(GenericPracticeArgs.model_validate(args).to_draft())
    question = candidate["questions"][1]
    assert question["answer"] == question["rubric"] == "\n".join(question["answer_points"])
    assert all(term in question["answer"] for term in ("O(n)", "O(n log n)", "O(log n)"))
    assert not any(c.isdigit() for c in question["answer"])
    assert question["evidence_ids"] == ["caption-a"]
    assert "O(" not in question["question"]  # The public question does not give its answer.


def test_cost_contract_rejects_free_answer_override_and_requires_own_course_citations():
    args = arguments()
    args["application"] = draft()["questions"][1]
    with pytest.raises(ValidationError, match="own application"):
        GenericPracticeArgs.model_validate(args)
    args.pop("application")
    args["application_evidence_ids"] = []
    with pytest.raises(ValidationError, match="course citations"):
        GenericPracticeArgs.model_validate(args)
    args["application_evidence_ids"] = ["caption-a"]
    args["steps"] = 10010
    with pytest.raises(ValidationError):
        GenericPracticeArgs.model_validate(args)


def test_generated_cost_claims_cite_shared_method_and_scenario_but_not_unrelated_concept():
    args = arguments()
    args["evidence_ids"] = ["method-costs"]
    args["concept"]["evidence_ids"] = ["concept-only"]
    args["application_evidence_ids"] = ["scenario", "method-costs"]
    candidate = materialize_practice(GenericPracticeArgs.model_validate(args).to_draft())
    assert candidate["questions"][0]["evidence_ids"] == ["concept-only"]
    assert candidate["questions"][1]["evidence_ids"] == ["method-costs", "scenario"]


def test_model_selected_cost_mode_changes_only_the_generic_drafting_contract():
    messages = [
        {"role": "user", "content": json.dumps({"goal": "Compare preparation and query costs"})},
        {"role": "tool", "content": json.dumps({"practice_kind": "search_cost"})},
    ]
    tools = decision_schemas(messages)
    assert not any(t["function"]["name"] == "create_interval_practice" for t in tools)
    schema = next(
        t["function"]["parameters"] for t in tools if t["function"]["name"] == "create_practice_set"
    )
    assert "cost_scenario" in schema["required"]
    assert "application" not in schema["properties"]
    messages[-1]["content"] = json.dumps({"practice_kind": "general"})
    schema = next(
        t["function"]["parameters"]
        for t in decision_schemas(messages)
        if t["function"]["name"] == "create_practice_set"
    )
    assert "application" in schema["required"]
    assert "cost_scenario" not in schema["properties"]


@pytest.mark.parametrize("foreign", [False, True])
def test_cost_scenario_roundtrips_canonical_refs_and_stores_private_answers(setup, foreign):
    store, authority, runtime, scope = setup
    original = authority.read

    def observed(run, action="CHECK", **kwargs):
        result = original(run, action, **kwargs)
        for item in result.get("evidence", []):
            if item["evidence_id"] in {"e1", "e2"}:
                item["evidence_id"] = "canonical-" + item["evidence_id"]
            if item["evidence_id"] == "canonical-e2":
                item.update(start_ms=10000, end_ms=11000)
        return result

    authority.read = observed

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "Compare searching", "practice_kind": "search_cost"},
            }
        args = arguments()
        args["evidence_ids"] = args["concept"]["evidence_ids"] = ["e1"]
        args["application_evidence_ids"] = ["foreign" if foreign else "e2"]
        return {"name": "create_practice_set", "arguments": args}

    runtime.provider.decide = decide
    run = test_study.start(setup)
    runtime.execute(run)
    result = test_study.read(setup)
    if foreign:
        assert result["run"]["error_code"] == "UNSUPPORTED_CITATION"
        assert not result["artifact"]
    else:
        assert result["run"]["status"] == "succeeded"
        assert "answer" not in result["artifact"]["questions"][1]
        assert result["artifact"]["questions"][1]["evidence_ids"] == ["canonical-e1", "canonical-e2"]
        private = store.command(StudyCommand(**scope, operation="ANSWERS"), "mock")["questions"][1]
        assert private["answer"] == private["rubric"]
        assert "O(n log n)" in private["answer"]
