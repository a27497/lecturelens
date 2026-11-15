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
    RUN_CANDIDATE_LIMIT,
    TEMPLATE_PRACTICE_KINDS,
    build_messages,
    closed_practice_kinds,
    counted_candidates,
    template_mismatch,
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
from lecturelens_agent.study.runtime import SYSTEM as RUNTIME_SYSTEM
from lecturelens_agent.study.store import RUN_MODEL_CALL_LIMIT
from lecturelens_agent.study.support_review import (
    COVERAGE_SYSTEM,
    FIELD_EVIDENCE_INSTRUCTION,
    FIELD_SYSTEM,
    CoverageVerdict,
    FieldCheck,
    GoalFieldCheck,
    GoalFieldSupportVerdict,
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


# --- T2: an unsupported tool-generated question also closes the template ---


@pytest.mark.parametrize(
    "kind,field_issues,closed",
    [
        ("interval_halving", {"question_2": ["unsupported_question"]}, True),
        ("search_cost", {"question_2": ["unsupported_question"]}, True),
        # The model-written concept question and explanation remain repairable in place.
        ("interval_halving", {"question_1": ["unsupported_question"]}, False),
        ("interval_halving", {"explanation": ["unsupported_explanation"]}, False),
        # Free-form practice writes its own application.
        ("general", {"question_2": ["unsupported_question"]}, False),
    ],
)
def test_unsupported_generated_question_closes_only_template_kinds(kind, field_issues, closed):
    rejected = {"tool": "create_practice_set", "arguments": {"title": "Draft"}}
    rejected["result"] = {
        "quality": {
            "accepted": False,
            "issues": sorted({i for found in field_issues.values() for i in found}),
            "feedback": "Fix it.",
            "field_issues": field_issues,
        }
    }
    assert closed_practice_kinds([search(kind), rejected]) == ([kind] if closed else [])
    assert template_mismatch(rejected["result"]["quality"]) is ("question_2" in field_issues)


def test_field_review_records_issues_per_field():
    from test_study_goals import goal_body

    body = goal_body()
    data = goal_verdict(body)
    data["checks"][2].update(issue="unsupported_question", correction="Use a taught operation.")
    review = GoalFieldSupportVerdict.model_validate(data, context=body).review()
    assert review.field_issues == {"question_2": ["unsupported_question"]}
    assert "unsupported_question" in review.issues
    accepted = GoalFieldSupportVerdict.model_validate(goal_verdict(body), context=body).review()
    assert accepted.field_issues == {}


# --- T3: a closed template's candidate does not use a repair slot ---


def test_closed_template_candidate_is_not_counted_toward_the_candidate_limit():
    closed = [search("interval_halving"), candidate("create_interval_practice", ["goal_mismatch"])]
    assert counted_candidates(closed) == 0
    rerouted = [*closed, search("general"), candidate("create_practice_set", ["unsupported_question"])]
    assert counted_candidates(rerouted) == 1
    ordinary = [search("general"), candidate("create_practice_set", ["goal_mismatch"])]
    assert counted_candidates([*ordinary, ordinary[1]]) == 2
    assert f"At most {RUN_CANDIDATE_LIMIT} candidates." in RUNTIME_SYSTEM


def staged_provider(runtime, interval_review, general_reviews):
    """Interval candidate first, then general candidates reviewed in the given order."""
    contexts, reviews, general = [], [], []

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        contexts.append(context)
        if not context["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "peak", "practice_kind": "interval_halving"},
            }
        if "closed_practice_kinds" not in context:
            return {"name": "create_interval_practice", "arguments": interval_arguments()}
        if context.get("practice_kind") == "interval_halving":
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "peak", "practice_kind": "general"},
            }
        arguments = general_arguments()
        arguments["explanation"] += " 修订" * len(general)  # each repair changes content
        general.append(arguments)
        return {"name": "create_practice_set", "arguments": arguments}

    pending = list(general_reviews)

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
            return {"review": interval_review}
        verdict = pending.pop(0)
        if verdict is not None:
            return {"review": verdict}
        data = goal_verdict(body)
        data["application_method_check"] = data["checks"][2].pop("method_alignment")
        accepted = review_contract(review_mode=body["review_mode"]).model_validate(data, context=body)
        return {"review": accepted.review().model_dump()}

    runtime.provider.decide, runtime.provider.review = decide, review
    return contexts, reviews


GENERATED_QUESTION_REJECTION = {
    "issues": ["unsupported_question"],
    "feedback": "question_2: the course does not teach guessing a hidden number.",
    "field_issues": {"question_2": ["unsupported_question"]},
}
EXPLANATION_REJECTION = {"issues": ["unsupported_explanation"], "feedback": "Cite the explanation source."}


def test_closed_template_returns_its_slot_so_two_general_attempts_remain(setup):
    _, _, runtime, _ = setup
    contexts, reviews = staged_provider(runtime, GENERATED_QUESTION_REJECTION, [EXPLANATION_REJECTION, None])
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    tools, quality = run_events(setup)
    assert tools == [
        "search_course_evidence",
        "create_interval_practice",
        "search_course_evidence",
        "create_practice_set",
        "create_practice_set",
    ]
    assert quality == [False, False, True]
    left = [c["budget"]["candidates_left"] for c in contexts if "budget" in c]
    assert left[-1] == RUN_CANDIDATE_LIMIT - 1  # the closed template candidate was not counted
    assert result["run"]["model_calls"] == 9
    assert result["run"]["model_calls"] <= RUN_MODEL_CALL_LIMIT


def test_after_a_returned_slot_two_ordinary_rejections_still_exhaust_the_run(setup):
    _, _, runtime, _ = setup
    staged_provider(runtime, GENERATED_QUESTION_REJECTION, [EXPLANATION_REJECTION, EXPLANATION_REJECTION])
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["error_code"] == "QUALITY_REPAIR_EXHAUSTED"
    _, quality = run_events(setup)
    assert quality == [False, False, False]


def test_ordinary_template_rejection_still_counts_toward_the_limit(setup):
    _, _, runtime, _ = setup
    # unsupported_explanation on a template candidate is repaired in place and counted.
    contexts, _ = staged_provider(runtime, EXPLANATION_REJECTION, [])
    runtime.execute(test_study.start(setup))
    assert not any("closed_practice_kinds" in c for c in contexts)
    assert [c["budget"]["candidates_left"] for c in contexts if "budget" in c][-1] == RUN_CANDIDATE_LIMIT - 1


# --- T1: window reads batched in one response keep the decision's authorization ---


def test_second_window_read_in_one_response_survives_eviction_by_the_first(setup):
    _, authority, runtime, _ = setup
    base = authority.read

    def read(scope, action="CHECK", **arguments):
        if action == "SEARCH":
            return base(scope, "READ", evidence_ids=[f"s{i}" for i in range(1, 9)])
        if action == "WINDOW":
            anchor = arguments["evidence_id"]
            return base(scope, "READ", evidence_ids=[f"{anchor}-prev", anchor, f"{anchor}-next"])
        return base(scope, action, **arguments)

    authority.read = read
    calls = []

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        calls.append(context)
        if not context["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "halving", "practice_kind": "interval_halving"},
            }
        if len(calls) == 2:
            # e2 is visible now; the first read's three passages evict it from the eight-ID selection.
            return {
                "calls": [
                    {"name": "read_evidence_window", "arguments": {"evidence_id": "e1"}},
                    {"name": "read_evidence_window", "arguments": {"evidence_id": "e2"}},
                ]
            }
        return {"name": "create_interval_practice", "arguments": interval_arguments()}

    runtime.provider.decide = decide
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded", result["run"]["error_code"]
    tools, _ = run_events(setup)
    assert tools == [
        "search_course_evidence",
        "read_evidence_window",
        "read_evidence_window",
        "create_interval_practice",
    ]


# --- Phase R2: method_citation_check rejections use the same closure decision ---


def method_check_rejection():
    from lecturelens_agent.study.context import METHOD_CITATION_CHECK
    from lecturelens_agent.study.quality import repair_review

    verdict = repair_review(["unsupported_question"])
    verdict.feedback = "The application must cite its selected method's observed source."
    rejected = {"tool": "create_practice_set", "arguments": {"title": "Draft"}}
    rejected["result"] = {
        "quality": {"accepted": False, "source": METHOD_CITATION_CHECK, **verdict.model_dump()}
    }
    return rejected


@pytest.mark.parametrize("kind", [*TEMPLATE_PRACTICE_KINDS, "general", "linear_points", "python_strings"])
def test_method_citation_rejection_closes_exactly_the_template_kinds(kind):
    rejected = method_check_rejection()
    # The stored verdict is unchanged: the check still writes no field_issues.
    assert rejected["result"]["quality"]["field_issues"] == {}
    assert template_mismatch(rejected["result"]["quality"])
    closed = kind in TEMPLATE_PRACTICE_KINDS
    assert closed_practice_kinds([search(kind), rejected]) == ([kind] if closed else [])
    assert counted_candidates([search(kind), rejected]) == (0 if closed else 1)


def test_unsupported_issue_without_question_2_attribution_still_does_not_close():
    # A model review naming another field, or an unattributed check, keeps in-place repair.
    for source, field_issues in [
        ("model_review", {"question_1": ["unsupported_question"]}),
        ("model_review", {}),
        ("citation_check", {}),
    ]:
        rejected = candidate("create_practice_set", ["unsupported_question"])
        rejected["result"]["quality"].update(source=source, field_issues=field_issues)
        assert closed_practice_kinds([search("search_cost"), rejected]) == []


@pytest.mark.parametrize(
    "history",
    [
        [search("general"), method_check_rejection()],
        [search("linear_points"), method_check_rejection()],
        [search("search_cost"), candidate("create_practice_set", ["unsupported_explanation"])],
        [search("interval_halving")],
    ],
)
def test_contexts_without_a_closure_are_byte_identical_to_the_previous_rule(history, monkeypatch):
    from lecturelens_agent.study import context as module

    current = build_messages("system", PEAK_GOAL, EVIDENCE, history, [], budget={"candidates_left": 1})
    monkeypatch.setattr(
        module, "question_2_issues", lambda q: (q.get("field_issues") or {}).get("question_2", [])
    )
    previous = build_messages("system", PEAK_GOAL, EVIDENCE, history, [], budget={"candidates_left": 1})
    assert json.dumps(current, sort_keys=True) == json.dumps(previous, sort_keys=True)
    assert "closed_practice_kinds" not in current[0][-1]["content"]


def separate_method_source(authority):
    """Keep e2 away from e1 so citation completion cannot add the method source to question_2."""
    original = authority.read

    def read(scope, action="CHECK", **kwargs):
        result = original(scope, action, **kwargs)
        for item in result.get("evidence", []):
            if item["evidence_id"] == "e2":
                item.update(start_ms=10000, end_ms=11000)
        return result

    authority.read = read


def method_check_provider(runtime, first_kind, cost_method_id=None):
    """The first candidate cites only e2 in question_2; the observed method's source is e1."""
    contexts, decided = [], []

    def decide(messages, timeout):
        from test_study_costs import arguments as cost_arguments

        context = json.loads(messages[-1]["content"])
        contexts.append(context)
        if not context["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "cost", "practice_kind": first_kind},
            }
        decided.append(context.get("practice_kind"))
        if context.get("practice_kind") == "search_cost":
            args = cost_arguments()
            args["evidence_ids"] = args["concept"]["evidence_ids"] = args["application_evidence_ids"] = ["e2"]
            if cost_method_id:
                args["method_id"] = cost_method_id
            return {"name": "create_practice_set", "arguments": args}
        arguments = general_arguments()
        if len(decided) == 1:
            # As in the probe Runs: the shared citations include both passages, question_2 omits e1.
            arguments["evidence_ids"] = ["e1", "e2"]
            arguments["application"]["evidence_ids"] = ["e2"]
        return {"name": "create_practice_set", "arguments": arguments}

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if body["review_mode"] == "course_methods_v1":
            data = {
                "course_fact": "Compare the costs of lookups.",
                "evidence_ids": ["e1"],
                "support": "demonstrated_method",
                "missing_goal_quote": "",
                "methods": [
                    {"operation": "比较代价", "input": "查找次数", "output": "复杂度", "evidence_id": "e1"}
                ],
            }
            return {"review": MethodCoverageVerdict.model_validate(data, context=body).review().model_dump()}
        data = goal_verdict(body)
        if "application_method" in body:
            data["application_method_check"] = data["checks"][2].pop("method_alignment")
        verdict = review_contract(review_mode=body["review_mode"]).model_validate(data, context=body)
        return {"review": verdict.review().model_dump()}

    runtime.provider.decide, runtime.provider.review = decide, review
    return contexts


def stored_qualities(store, run):
    with store.connect() as conn:
        rows = conn.execute(
            "SELECT call_id, result->'quality' AS quality FROM study_tool_result WHERE run_id=%s AND result ? 'quality'",
            (run["run_id"],),
        ).fetchall()
    return [row["quality"] for row in sorted(rows, key=lambda r: int(r["call_id"].rsplit(":", 1)[1]))]


def test_general_application_cites_its_method_source_before_review(setup):
    """Phase S1: an omitted method source is bound, not rejected by method_citation_check.

    In the 2026-11-14 probe all three method_citation_check rejections were this omission.
    """
    store, authority, runtime, _ = setup
    separate_method_source(authority)
    contexts = method_check_provider(runtime, "general")
    reviewed = []
    review = runtime.provider.review

    def capture(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if body["review_mode"] != "course_methods_v1":
            reviewed.append(body)
        return review(messages, timeout)

    runtime.provider.review = capture
    run = test_study.start(setup)
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded", result["run"]["error_code"]
    tools, quality = run_events(setup)
    assert tools == ["search_course_evidence", "create_practice_set"]
    assert quality == [True]
    assert [q["source"] for q in stored_qualities(store, run)] == ["mock_demo"]
    with store.connect() as conn:
        stored = conn.execute(
            "SELECT arguments FROM study_tool_result WHERE run_id=%s AND tool_name='create_practice_set'",
            (run["run_id"],),
        ).fetchone()["arguments"]
    # The model cited only e2; the observed method's source e1 is bound before review.
    assert stored["questions"][1]["evidence_ids"] == ["e2", "e1"]
    assert stored["questions"][0]["evidence_ids"] == ["e1"]  # concept citations are not changed
    assert len(reviewed) == 1 and reviewed[0]["application_method"]["evidence_id"]
    artifact = result["artifact"]
    assert set(artifact["questions"][1]["evidence_ids"]) <= set(artifact["evidence_ids"])
    assert not any("closed_practice_kinds" in c for c in contexts)


@pytest.mark.parametrize("method_id", [None, "m1"])
def test_cost_template_cannot_reach_method_citation_check_in_the_current_runtime(setup, method_id):
    """search_cost observes no course methods, so the R2 attribution is a guard, not an observed path."""
    store, authority, runtime, _ = setup
    separate_method_source(authority)
    method_check_provider(runtime, "search_cost", cost_method_id=method_id)
    run = test_study.start(setup)
    runtime.execute(run)
    result = test_study.read(setup)
    if method_id:
        assert result["run"]["error_code"] == "UNOBSERVED_APPLICATION_METHOD"
        assert stored_qualities(store, run) == []
    else:
        assert result["run"]["status"] == "succeeded", result["run"]["error_code"]
        assert [q["source"] for q in stored_qualities(store, run)] == ["mock_demo"]
