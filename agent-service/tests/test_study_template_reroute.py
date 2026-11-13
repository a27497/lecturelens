"""A computed template rejected for goal_mismatch is withdrawn for the Run, and review
evidence selections share one declared bound across schema, prompt and review input."""

import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_answer_points import draft
from test_study_goals import goal_verdict

from lecturelens_agent.study.context import (
    PRACTICE_KIND_NOTICE,
    REVIEW_EVIDENCE_LIMIT,
    TEMPLATE_PRACTICE_KINDS,
    build_messages,
    closed_practice_kinds,
)
from lecturelens_agent.study.contracts import materialize_practice
from lecturelens_agent.study.goals import ClaimCheck
from lecturelens_agent.study.provider import decision_schemas
from lecturelens_agent.study.quality import (
    LEGACY_REVIEW_RETRY,
    REVIEW_JSON_RETRY,
    review_contract,
    review_messages,
    review_retry_instruction,
    review_schema,
)
from lecturelens_agent.study.support_review import (
    COVERAGE_SYSTEM,
    FIELD_EVIDENCE_INSTRUCTION,
    FIELD_SYSTEM,
    CoverageVerdict,
    FieldCheck,
    GoalFieldCheck,
    MethodCoverageVerdict,
)

setup = test_study.setup

PEAK_GOAL = "练习一维峰值查找的分治算法：为什么看中间元素并向更大的邻居一侧递归？"


def search(kind):
    return {
        "tool": "search_course_evidence",
        "arguments": {"query": "peak finding", "practice_kind": kind},
        "result": {"evidence_ids": ["a"], "practice_kind": kind},
    }


def candidate(tool, issues, accepted=False):
    return {
        "tool": tool,
        "arguments": {"title": "Draft"},
        "result": {"quality": {"accepted": accepted, "issues": issues, "feedback": "Address the goal."}},
    }


EVIDENCE = [
    {"evidence_id": "a", "text": "Look at the middle element.", "start_ms": 0, "end_ms": 1000},
]


def decision(history):
    messages, _ = build_messages("system", PEAK_GOAL, EVIDENCE, history, [])
    tools = {tool["function"]["name"]: tool for tool in decision_schemas(messages)}
    return json.loads(messages[-1]["content"]), tools


def search_kinds(tools):
    return tools["search_course_evidence"]["function"]["parameters"]["properties"]["practice_kind"]["enum"]


def max_length(model, field):
    return next(item.max_length for item in model.model_fields[field].metadata if hasattr(item, "max_length"))


# --- Withdrawing a computed template after goal_mismatch ---


def test_goal_mismatch_on_interval_template_withdraws_tool_and_kind_until_another_search():
    history = [
        search("interval_halving"),
        candidate("create_interval_practice", ["goal_mismatch", "unsupported_question"]),
    ]
    context, tools = decision(history)
    assert context["closed_practice_kinds"] == ["interval_halving"]
    assert context["practice_kind_notice"] == PRACTICE_KIND_NOTICE
    assert "create_interval_practice" not in tools
    assert "create_practice_set" not in tools  # still bound to the closed kind until a new search
    assert {"search_course_evidence", "report_insufficient_evidence"} <= set(tools)
    assert "interval_halving" not in search_kinds(tools) and "general" in search_kinds(tools)

    context, tools = decision([*history, search("general")])
    assert context["closed_practice_kinds"] == ["interval_halving"]
    assert "create_practice_set" in tools and "create_interval_practice" not in tools
    assert "interval_halving" not in search_kinds(tools)


def test_closed_search_cost_withdraws_its_cost_mode_tool_but_not_general_practice():
    history = [search("search_cost"), candidate("create_practice_set", ["goal_mismatch"])]
    _, tools = decision(history)
    assert "create_practice_set" not in tools
    assert "search_cost" not in search_kinds(tools)
    _, tools = decision([*history, search("general")])
    assert "create_practice_set" in tools
    assert "application" in tools["create_practice_set"]["function"]["parameters"]["properties"]


@pytest.mark.parametrize(
    "kind,tool,issues,accepted",
    [
        # Adaptable templates and free-form practice repair inside the same tool.
        ("general", "create_practice_set", ["goal_mismatch"], False),
        ("linear_points", "create_linear_practice", ["goal_mismatch"], False),
        ("python_strings", "create_python_practice", ["goal_mismatch"], False),
        # A template rejection for another reason is repaired inside the template.
        ("interval_halving", "create_interval_practice", ["unsupported_explanation"], False),
        ("selection_steps", "create_sequence_practice", [], True),
    ],
)
def test_other_rejections_keep_the_decision_context_and_tools_unchanged(kind, tool, issues, accepted):
    history = [search(kind), candidate(tool, issues, accepted)]
    assert closed_practice_kinds(history) == []
    context, tools = decision(history)
    assert "closed_practice_kinds" not in context and "practice_kind_notice" not in context
    _, before = decision(history[:1])
    assert set(tools) == set(before)
    assert search_kinds(tools) == search_kinds(before)
    assert kind in search_kinds(tools) or kind not in TEMPLATE_PRACTICE_KINDS


def test_closed_kinds_follow_the_search_that_produced_each_rejected_candidate():
    history = [
        search("selection_steps"),
        candidate("create_sequence_practice", ["goal_mismatch"]),
        search("interval_halving"),
        candidate("create_interval_practice", ["goal_mismatch"]),
        search("selection_steps"),
    ]
    assert closed_practice_kinds(history) == ["selection_steps", "interval_halving"]


def interval_arguments(lower=-8):
    base = draft()
    for field in [base, *base["questions"]]:
        field["evidence_ids"] = ["e1"]
    return {
        **{key: base[key] for key in ("title", "explanation", "evidence_ids")},
        "language": "zh",
        "concept": base["questions"][0],
        "application": {"lower": lower, "upper": 24, "feedback": "higher", "evidence_ids": ["e1"]},
    }


def general_arguments():
    value = draft()
    for field in [value, *value["questions"]]:
        field["evidence_ids"] = ["e1"]
    return {
        **{key: value[key] for key in ("title", "explanation", "evidence_ids")},
        "concept": value["questions"][0],
        "application": value["questions"][1],
        "method_id": "m1",
    }


def reroute_provider(runtime, after_rejection):
    contexts, reviews = [], []

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        contexts.append(context)
        if not context["evidence"]:
            kind = "interval_halving"
            return {"name": "search_course_evidence", "arguments": {"query": "peak", "practice_kind": kind}}
        if "closed_practice_kinds" not in context:
            return {"name": "create_interval_practice", "arguments": interval_arguments()}
        if context.get("practice_kind") == "interval_halving":
            return after_rejection()
        return {"name": "create_practice_set", "arguments": general_arguments()}

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        reviews.append(body["review_mode"])
        if body["review_mode"] == "course_methods_v1":
            data = {
                "course_fact": "Compare the middle element with its neighbours.",
                "evidence_ids": ["e1"],
                "support": "demonstrated_method",
                "missing_goal_quote": "",
                "methods": [
                    {
                        "operation": "比较中间元素与邻居",
                        "input": "数组",
                        "output": "递归方向",
                        "evidence_id": "e1",
                    }
                ],
            }
            return {"review": MethodCoverageVerdict.model_validate(data, context=body).review().model_dump()}
        if "computed" in body["review_mode"]:
            return {"review": {"issues": ["goal_mismatch"], "feedback": "This is not peak finding."}}
        data = goal_verdict(body)
        data["application_method_check"] = data["checks"][2].pop("method_alignment")
        verdict = review_contract(review_mode=body["review_mode"]).model_validate(data, context=body)
        return {"review": verdict.review().model_dump()}

    runtime.provider.decide, runtime.provider.review = decide, review
    return contexts, reviews


def run_events(setup):
    events = test_study.read(setup, "EVENTS")["events"]
    tools = [e["payload"]["tool"] for e in events if e["event_type"] == "tool_started"]
    quality = [e["payload"]["accepted"] for e in events if e["event_type"] == "quality_checked"]
    return tools, quality


def test_rejected_interval_template_reroutes_through_a_new_search_and_succeeds(setup):
    _, _, runtime, _ = setup
    contexts, reviews = reroute_provider(
        runtime,
        lambda: {
            "name": "search_course_evidence",
            "arguments": {"query": "peak", "practice_kind": "general"},
        },
    )
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    tools, quality = run_events(setup)
    assert tools == [
        "search_course_evidence",
        "create_interval_practice",
        "search_course_evidence",
        "create_practice_set",
    ]
    assert quality == [False, True]
    assert ["practice_kind_notice" in c for c in contexts] == [False, False, True, True]
    assert reviews == [
        "field_support_computed_goals_v1",
        "course_methods_v1",
        "field_support_scoped_goals_v1",
    ]
    assert result["run"]["model_calls"] == 7
    assert result["artifact"]["kind"] == "practice"


@pytest.mark.parametrize(
    "retry",
    [
        {
            "name": "search_course_evidence",
            "arguments": {"query": "again", "practice_kind": "interval_halving"},
        },
        {"name": "create_interval_practice", "arguments": interval_arguments(lower=-6)},
    ],
)
def test_closed_template_cannot_run_again_even_if_a_provider_ignores_the_schema(setup, retry):
    _, _, runtime, _ = setup
    _, reviews = reroute_provider(runtime, lambda: json.loads(json.dumps(retry)))
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "failed"
    assert result["run"]["error_code"] == "INVALID_TOOL_ARGUMENTS"
    assert result["artifact"] is None
    tools, quality = run_events(setup)
    assert tools == ["search_course_evidence", "create_interval_practice"]
    assert quality == [False]
    assert reviews == ["field_support_computed_goals_v1"]  # no review spent on the withdrawn template


# --- One declared bound for review evidence selections ---


def observation_body(count):
    evidence = [{"evidence_id": f"x{i}", "text": f"Passage {i} checks a point."} for i in range(count)]
    messages = review_messages(
        "Practice substitution",
        {"kind": "insufficient_evidence", "reason": ""},
        evidence,
        structured_support=True,
        observe_methods=True,
    )
    return json.loads(messages[-1]["content"])


def coverage(ids):
    return {
        "course_fact": "The course checks a point by substitution.",
        "evidence_ids": ids,
        "support": "demonstrated_method",
        "missing_goal_quote": "",
        "methods": [{"operation": "Substitute", "input": "Point", "output": "Holds", "evidence_id": "e1"}],
    }


def test_review_selection_bound_matches_the_review_input_bound():
    body = observation_body(REVIEW_EVIDENCE_LIMIT + 2)
    assert len(body["evidence"]) == REVIEW_EVIDENCE_LIMIT
    every = [item["evidence_id"] for item in body["evidence"]]
    verdict = MethodCoverageVerdict.model_validate(coverage(every), context=body)
    assert len(verdict.review().grounds["explanation"]) == REVIEW_EVIDENCE_LIMIT
    with pytest.raises(ValidationError, match="too_long|at most"):
        MethodCoverageVerdict.model_validate(coverage([*every, every[0]]), context=body)
    for model in (FieldCheck, GoalFieldCheck, CoverageVerdict, ClaimCheck):
        assert max_length(model, "evidence_ids") == REVIEW_EVIDENCE_LIMIT
    wire = review_schema(review_mode="course_methods_v1")["function"]["parameters"]
    assert wire["properties"]["evidence_ids"]["maxItems"] == REVIEW_EVIDENCE_LIMIT


def test_prompts_state_the_shared_bound_and_goal_mode_still_drops_the_field_instruction():
    assert f"select up to {REVIEW_EVIDENCE_LIMIT} evidence_ids" in COVERAGE_SYSTEM
    assert FIELD_EVIDENCE_INSTRUCTION in FIELD_SYSTEM
    assert f"1-{REVIEW_EVIDENCE_LIMIT}" in FIELD_EVIDENCE_INSTRUCTION
    evidence = [
        {"evidence_id": "caption-a", "text": "Without explicit return, the call returns None."},
        {"evidence_id": "caption-b", "text": "An inner print shows inner, then None is printed."},
    ]
    practice = {**materialize_practice(draft()), "kind": "practice"}
    plain = review_messages("Practice None", practice, evidence, structured_support=True)
    goals = review_messages("Practice None", practice, evidence, structured_support=True, check_goal=True)
    assert FIELD_EVIDENCE_INSTRUCTION in plain[0]["content"]
    assert FIELD_EVIDENCE_INSTRUCTION not in goals[0]["content"]
    assert "Do not return evidence_ids" in goals[0]["content"]


def test_one_retry_instruction_per_review_error_code():
    assert review_retry_instruction("MODEL_TOOL_CONTRACT") == REVIEW_JSON_RETRY
    assert review_retry_instruction("MODEL_REVIEW_CONTRACT") == LEGACY_REVIEW_RETRY
