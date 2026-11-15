"""The persistent tool-call limit is unchanged; its last call is reserved for a candidate.

Mirrors the R2 b2-cost-lure probe Run, where window reads used all eight tool calls
before any candidate and the Run could only end budget_exceeded.
"""

import json

import pytest
import test_study
from test_study_template_reroute import interval_arguments, run_events

from lecturelens_agent.study.context import (
    EXPLORATION_TOOLS,
    TOOL_CALL_NOTICE,
    TOOL_CALL_NOTICE_AT,
    build_messages,
)
from lecturelens_agent.study.provider import decision_schemas
from lecturelens_agent.study.store import RUN_MODEL_CALL_LIMIT, RUN_TOOL_CALL_LIMIT

setup = test_study.setup


def test_limits_and_notice_threshold_are_unchanged_constants():
    assert RUN_TOOL_CALL_LIMIT == 8 and RUN_MODEL_CALL_LIMIT == 12
    assert set(EXPLORATION_TOOLS) == {
        "search_course_evidence",
        "read_evidence_window",
        "check_python_example",
    }
    assert TOOL_CALL_NOTICE_AT == 2


@pytest.mark.parametrize("left,withdrawn", [(1, True), (2, False), (None, False)])
def test_schema_withdraws_exploration_only_at_the_reserved_last_call(left, withdrawn):
    evidence = [{"evidence_id": "a", "text": "Look at the middle.", "start_ms": 0, "end_ms": 1000}]
    history = [
        {
            "tool": "search_course_evidence",
            "arguments": {"query": "q", "practice_kind": "general"},
            "result": {"evidence_ids": ["a"], "practice_kind": "general"},
        }
    ]
    budget = {"candidates_left": 2, **({"tool_calls_left": left} if left is not None else {})}
    messages, _ = build_messages("system", "goal", evidence, history, [], budget=budget)
    names = {tool["function"]["name"] for tool in decision_schemas(messages)}
    assert "report_insufficient_evidence" in names and "create_practice_set" in names
    assert bool(names & set(EXPLORATION_TOOLS)) is not withdrawn


def windowed_authority(authority):
    """Searches return s1..s8; a window adds two neighbours. Text names the canonical ID."""
    base = authority.read

    def read(scope, action="CHECK", **arguments):
        if action == "SEARCH":
            result = base(scope, "READ", evidence_ids=[f"s{i}" for i in range(1, 9)])
        elif action == "WINDOW":
            anchor = arguments["evidence_id"]
            result = base(scope, "READ", evidence_ids=[f"{anchor}-prev", anchor, f"{anchor}-next"])
        else:
            result = base(scope, action, **arguments)
        for item in result.get("evidence", []):
            item["text"] = f"Passage {item['evidence_id']}."
        return result

    authority.read = read


def exploring_provider(runtime, last_reads):
    """Search once, then read unread windows: 2, 2, then 3 per response, then draft.

    last_reads > 0 makes the provider ignore the withdrawn schema at the last call.
    """
    contexts, schemas, read = [], [], set()

    def unread(context, count):
        refs = []
        for item in context["evidence"]:
            canonical = item["text"].removeprefix("Passage ").removesuffix(".")
            if canonical not in read and len(refs) < count:
                read.add(canonical)
                refs.append(item["evidence_id"])
        return [{"name": "read_evidence_window", "arguments": {"evidence_id": ref}} for ref in refs]

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        contexts.append(context)
        schemas.append({tool["function"]["name"] for tool in decision_schemas(messages)})
        if not context["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "halving", "practice_kind": "interval_halving"},
            }
        decisions = len(contexts) - 1
        if decisions <= 2:
            return {"calls": unread(context, 2)}
        if decisions == 3:
            return {"calls": unread(context, 3)}
        if last_reads:
            return {"calls": unread(context, last_reads)}
        return {"name": "create_interval_practice", "arguments": interval_arguments()}

    runtime.provider.decide = decide
    return contexts, schemas


def reserved_events(setup):
    return [
        e["payload"]
        for e in test_study.read(setup, "EVENTS")["events"]
        if e["event_type"] == "tool_rejected"
        and e["payload"].get("error_code") == "TOOL_CALL_BUDGET_RESERVED"
    ]


def test_exploration_cannot_take_the_last_tool_call_so_a_candidate_follows(setup):
    _, authority, runtime, _ = setup
    windowed_authority(authority)
    contexts, schemas = exploring_provider(runtime, last_reads=0)
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded", result["run"]["error_code"]
    tools, quality = run_events(setup)
    # 1 search + 2 + 2 + 2 reads (the third read of that response was skipped) + candidate.
    assert tools == ["search_course_evidence", *["read_evidence_window"] * 6, "create_interval_practice"]
    assert quality == [True]
    assert result["run"]["tool_calls"] == RUN_TOOL_CALL_LIMIT
    assert result["run"]["model_calls"] <= RUN_MODEL_CALL_LIMIT
    skipped = reserved_events(setup)
    assert [(p["tool"], p["offset"], p["failure_category"]) for p in skipped] == [
        ("read_evidence_window", 2, "budget")
    ]
    # Earlier contexts are unchanged; the remaining count appears only near the limit.
    assert all("tool_calls_left" not in c.get("budget", {}) for c in contexts[:-1])
    assert contexts[-1]["budget"]["tool_calls_left"] == 1
    assert contexts[-1]["budget"]["tool_call_notice"] == TOOL_CALL_NOTICE
    assert not schemas[-1] & set(EXPLORATION_TOOLS)
    assert "create_interval_practice" in schemas[-1] and "report_insufficient_evidence" in schemas[-1]
    assert all(s & {"read_evidence_window"} for s in schemas[1:-1])


def test_provider_ignoring_the_withdrawn_schema_cannot_spend_the_reserved_call(setup):
    _, authority, runtime, _ = setup
    windowed_authority(authority)
    exploring_provider(runtime, last_reads=1)
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "failed"
    assert result["run"]["error_code"] == "INVALID_TOOL_ARGUMENTS"
    assert result["run"]["tool_calls"] == RUN_TOOL_CALL_LIMIT - 1
    assert result["artifact"] is None
    assert len(reserved_events(setup)) == 2
