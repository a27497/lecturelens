"""Study review/repair robustness: review tool-JSON retry, actionable review
retry diagnostics, and repairs that only rename a rejected candidate."""

import json

import pytest
import test_study
from test_study_goals import goal_verdict

from lecturelens_agent.study.method_scope import METHOD_SYSTEM, MethodSelection
from lecturelens_agent.study.provider import ChatProvider, ModelResponseError
from lecturelens_agent.study.quality import (
    REVIEW_JSON_RETRY,
    STRUCTURED_REVIEW_RETRY,
    review_contract,
    review_messages,
    review_wire_messages,
)
from lecturelens_agent.study.runtime import candidate_substance
from lecturelens_agent.study.support_review import MethodCoverageVerdict

setup = test_study.setup

JSON_FAILURE = {"stage": "tool_contract", "reason": "arguments_json"}


def observation_messages(**feedback):
    messages = review_messages(
        "Practice substitution",
        {"kind": "insufficient_evidence", "reason": ""},
        [{"evidence_id": "a", "text": "Substitute zero to check the origin."}],
        structured_support=True,
        observe_methods=True,
    )
    if feedback:
        body = json.loads(messages[-1]["content"])
        body["protocol_feedback"] = feedback
        messages[-1] = {**messages[-1], "content": json.dumps(body)}
    return messages


def method(label):
    return {"operation": label, "input": "Point", "output": "On line or not", "evidence_id": "e1"}


def coverage(methods):
    return {
        "course_fact": "The course checks a point by substitution.",
        "evidence_ids": ["e1"],
        "support": "demonstrated_method",
        "missing_goal_quote": "",
        "methods": methods,
    }


def max_length(model, field):
    return next(item.max_length for item in model.model_fields[field].metadata if hasattr(item, "max_length"))


# --- Review schema diagnostics and retry feedback (MODEL_REVIEW_CONTRACT) ---


def test_review_violation_reports_declared_path_and_bound_without_model_text(monkeypatch):
    arguments = coverage([method("Substitute"), method("Compare"), method("PRIVATE third")])
    arguments["PRIVATE_extra_key"] = "PRIVATE prose"
    monkeypatch.setattr(
        ChatProvider,
        "_request",
        lambda *args: {"calls": [{"name": "assess_study_candidate", "arguments": arguments}], "usage": {}},
    )
    provider = ChatProvider("http://127.0.0.1:9/v1", "test-model", "private-key")
    with pytest.raises(ModelResponseError, match="MODEL_REVIEW_CONTRACT") as failure:
        provider.review(observation_messages(), 10)
    violations = failure.value.diagnostics["validation"]
    assert {"field": "other", "type": "too_long", "path": "methods", "max_length": 2} in [
        {k: v for k, v in item.items() if k != "min_length"} for item in violations
    ]
    assert {"field": "other", "type": "extra_forbidden", "path": "other"} in violations
    assert "PRIVATE" not in json.dumps(failure.value.diagnostics)


def test_review_violation_names_an_overlong_method_string(monkeypatch):
    arguments = coverage([method("x" * 121)])
    monkeypatch.setattr(
        ChatProvider,
        "_request",
        lambda *args: {"calls": [{"name": "assess_study_candidate", "arguments": arguments}], "usage": {}},
    )
    provider = ChatProvider("http://127.0.0.1:9/v1", "test-model", "private-key")
    with pytest.raises(ModelResponseError, match="MODEL_REVIEW_CONTRACT") as failure:
        provider.review(observation_messages(), 10)
    assert failure.value.diagnostics["validation"] == [
        {"field": "other", "type": "string_too_long", "path": "methods.0.operation", "max_length": 120}
    ]


def test_structured_retry_forwards_only_validated_violations_and_fixed_instruction():
    wire = review_wire_messages(
        observation_messages(
            error="MODEL_REVIEW_CONTRACT",
            instruction="SECRET free text",
            diagnostics={
                "stage": "review_schema",
                "validation": [
                    {"field": "other", "type": "too_long", "path": "methods", "max_length": 2},
                    {"field": "other", "type": "SECRET type!", "path": "methods"},
                    {"field": "other", "type": "string_too_long", "path": "SECRET prose", "max_length": 120},
                ],
            },
        )
    )
    feedback = json.loads(wire[-1]["content"])["protocol_feedback"]
    assert feedback == {
        "instruction": STRUCTURED_REVIEW_RETRY,
        "violations": [
            {"type": "too_long", "path": "methods", "max_length": 2},
            {"type": "string_too_long", "max_length": 120},
        ],
    }
    assert "SECRET" not in json.dumps(wire)


def test_structured_retry_after_invalid_json_asks_for_valid_json():
    wire = review_wire_messages(observation_messages(error="MODEL_TOOL_CONTRACT", diagnostics=JSON_FAILURE))
    assert json.loads(wire[-1]["content"])["protocol_feedback"] == {"instruction": REVIEW_JSON_RETRY}


def test_method_prompt_limits_never_exceed_the_validator():
    # An output that obeys the prompt must always validate; retries then name the bound.
    assert "up to TWO methods" in METHOD_SYSTEM
    assert max_length(MethodCoverageVerdict, "methods") == 2
    assert "each <=80 characters" in METHOD_SYSTEM
    for field in ("operation", "input", "output"):
        assert max_length(MethodSelection, field) >= 80


# --- Review tool-call JSON retry (MODEL_TOOL_CONTRACT during review) ---


@pytest.mark.parametrize("repeat_failure", [False, True])
def test_candidate_review_retries_invalid_tool_json_once(setup, repeat_failure):
    store, _, runtime, _ = setup
    original = runtime.provider.review
    inputs = []

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        inputs.append(body)
        if len(inputs) == 1 or repeat_failure:
            raise ModelResponseError(
                "MODEL_TOOL_CONTRACT", {"prompt_tokens": 100, "completion_tokens": 20}, JSON_FAILURE
            )
        return original(messages, timeout)

    runtime.provider.review = review
    run = test_study.start(setup)
    runtime.execute(run)
    result = test_study.read(setup)
    assert len(inputs) == 2
    assert inputs[0]["candidate"] == inputs[1]["candidate"]
    assert "protocol_feedback" not in inputs[0]
    assert inputs[1]["protocol_feedback"]["error"] == "MODEL_TOOL_CONTRACT"
    assert inputs[1]["protocol_feedback"]["diagnostics"] == JSON_FAILURE
    assert result["run"]["model_calls"] == 5
    events = test_study.read(setup, "EVENTS")["events"]
    retries = [e["payload"] for e in events if e["event_type"] == "protocol_retry_scheduled"]
    assert retries == [
        {
            "error_code": "MODEL_TOOL_CONTRACT",
            "failure_category": "model_protocol",
            "retry": 1,
            "purpose": "review",
        }
    ]
    if repeat_failure:
        assert result["run"]["status"] == "failed"
        assert result["run"]["error_code"] == "MODEL_TOOL_CONTRACT"
        assert result["artifact"] is None
    else:
        assert result["run"]["status"] == "succeeded"
        assert "protocol_feedback" not in json.dumps(result["artifact"])


def test_other_review_failures_are_still_not_retried(setup):
    _, _, runtime, _ = setup
    calls = []

    def review(messages, timeout):
        calls.append(messages)
        raise ModelResponseError("MODEL_OUTPUT_TRUNCATED", {"completion_tokens": 900}, {"stage": "response"})

    runtime.provider.review = review
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert len(calls) == 1
    assert result["run"]["error_code"] == "MODEL_OUTPUT_TRUNCATED"
    assert not any(
        e["event_type"] == "protocol_retry_scheduled" for e in test_study.read(setup, "EVENTS")["events"]
    )


@pytest.mark.parametrize("code", ["MODEL_TOOL_CONTRACT", "MODEL_REVIEW_CONTRACT"])
def test_course_observation_retry_carries_error_and_diagnostics(setup, code):
    from test_study_answer_points import draft

    _, _, runtime, _ = setup
    calls = []
    diagnostics = (
        JSON_FAILURE
        if code == "MODEL_TOOL_CONTRACT"
        else {
            "stage": "review_schema",
            "validation": [{"field": "other", "type": "too_long", "path": "methods"}],
        }
    )

    def choose(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "stop", "practice_kind": "general"},
            }
        value = draft()
        for field in [value, *value["questions"]]:
            field["evidence_ids"] = ["e1"]
        return {
            "name": "create_practice_set",
            "arguments": {
                **{k: value[k] for k in ("title", "explanation", "evidence_ids")},
                "concept": value["questions"][0],
                "application": value["questions"][1],
                "method_id": "m1",
            },
        }

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        calls.append(body)
        if len(calls) == 1:
            raise ModelResponseError(code, {"prompt_tokens": 10, "completion_tokens": 5}, diagnostics)
        if body["review_mode"] == "course_methods_v1":
            assert body["protocol_feedback"] == {"error": code, "diagnostics": diagnostics}
            data = coverage([method("Check stopping")])
            data["course_fact"] = "Stopping"
            result = MethodCoverageVerdict.model_validate(data, context=body).review()
        else:
            data = goal_verdict(body)
            data["application_method_check"] = data["checks"][2].pop("method_alignment")
            result = (
                review_contract(review_mode=body["review_mode"]).model_validate(data, context=body).review()
            )
        return {"review": result.model_dump()}

    runtime.provider.decide, runtime.provider.review = choose, review
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded" and result["run"]["model_calls"] == 5
    events = test_study.read(setup, "EVENTS")["events"]
    retries = [e["payload"] for e in events if e["event_type"] == "protocol_retry_scheduled"]
    assert [(r["error_code"], r["purpose"]) for r in retries] == [(code, "course_observation")]


# --- Repairs that only rename the rejected candidate (QUALITY_REPAIR_EXHAUSTED) ---


def test_candidate_substance_ignores_only_presentation_fields():
    arguments = {"title": "A", "explanation": "Same", "evidence_ids": ["x"]}
    same = candidate_substance("create_interval_practice", arguments)
    assert candidate_substance("create_interval_practice", {**arguments, "title": "Renamed"}) == same
    assert candidate_substance("create_interval_practice", {**arguments, "explanation": "New"}) != same
    assert candidate_substance("create_practice_set", arguments) != same
    assert candidate_substance("create_interval_practice", arguments, {"operation": "m"}) != same


def rename_only_provider(runtime, *, fix_after_feedback):
    original = runtime.provider.decide
    decisions, reviews = [], []

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        decisions.append(context.get("repair_notice", ""))
        notice = "repair_notice" in context
        call = original(messages, timeout)
        if call["name"] == "create_practice_set" and context.get("quality"):
            call["arguments"]["title"] = "Renamed candidate"
            if notice and fix_after_feedback:
                call["arguments"]["explanation"] += " 修订：补充课程依据。"
        return call

    def review(messages, timeout):
        reviews.append(json.loads(messages[-1]["content"]))
        accepted = fix_after_feedback and len(reviews) == 2
        return {"review": {"issues": [] if accepted else ["goal_mismatch"], "feedback": "Address the goal."}}

    runtime.provider.decide, runtime.provider.review = decide, review
    return decisions, reviews


def test_rename_only_repair_is_not_reviewed_again_and_ends_after_one_notice(setup):
    _, _, runtime, _ = setup
    decisions, reviews = rename_only_provider(runtime, fix_after_feedback=False)
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "failed"
    assert result["run"]["error_code"] == "QUALITY_REPAIR_EXHAUSTED"
    assert result["artifact"] is None
    assert len(reviews) == 1  # the unchanged content never spends a second review
    assert result["run"]["model_calls"] == 6  # search, window, draft, review, rename, rename
    notices = [d for d in decisions if "NOT executed or reviewed" in d]
    assert len(notices) == 1
    assert "rejected candidate c2" in notices[0] and '["goal_mismatch"]' in notices[0]
    events = test_study.read(setup, "EVENTS")["events"]
    retries = [e["payload"] for e in events if e["event_type"] == "protocol_retry_scheduled"]
    assert retries == [
        {
            "error_code": "REPEATED_TOOL_WITHOUT_PROGRESS",
            "failure_category": "model_tool_selection",
            "retry": 1,
            "purpose": "quality_repair",
        }
    ]
    assert [e["payload"]["accepted"] for e in events if e["event_type"] == "quality_checked"] == [False]


def test_rename_only_repair_notice_allows_a_real_repair_to_succeed(setup):
    _, _, runtime, _ = setup
    decisions, reviews = rename_only_provider(runtime, fix_after_feedback=True)
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["artifact"]["title"] == "Renamed candidate"
    assert len(reviews) == 2
    assert reviews[1]["candidate"]["explanation"] != reviews[0]["candidate"]["explanation"]
    assert result["run"]["model_calls"] == 7
    assert sum("NOT executed or reviewed" in d for d in decisions) == 1


def test_new_run_in_the_same_session_starts_with_a_fresh_repair_notice(setup):
    _, _, runtime, _ = setup
    rename_only_provider(runtime, fix_after_feedback=False)
    runtime.execute(test_study.start(setup, key="first-run"))
    assert test_study.read(setup)["run"]["error_code"] == "QUALITY_REPAIR_EXHAUSTED"
    decisions, reviews = rename_only_provider(runtime, fix_after_feedback=True)
    runtime.execute(test_study.start(setup, key="second-run"))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    assert sum("NOT executed or reviewed" in d for d in decisions) == 1
