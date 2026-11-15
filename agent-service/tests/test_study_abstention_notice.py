"""The first abstention of a Run waits for one reformulated search.

Mirrors b2-cost-lure in the 2026-11-14 probe: two searches missed the taught passages,
the model abstained with budget left, and the abstention review (which sees only the
retrieved passages) accepted it.
"""

import json

import test_study

from lecturelens_agent.study.context import (
    ABSTENTION_NOTICE,
    ABSTENTION_NOTICE_MIN_MODEL_CALLS,
    ABSTENTION_NOTICE_MIN_TOOL_CALLS,
)
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.store import RUN_TOOL_CALL_LIMIT

setup = test_study.setup

REPORT = {
    "name": "report_insufficient_evidence",
    "arguments": {"reason": "The retrieved passages do not cover the requested comparison."},
}


def events(setup):
    return test_study.read(setup, "EVENTS")["events"]


def started_tools(setup):
    return [e["payload"]["tool"] for e in events(setup) if e["event_type"] == "tool_started"]


def notices(setup):
    return [
        e["payload"]
        for e in events(setup)
        if e["event_type"] == "protocol_retry_scheduled" and e["payload"].get("purpose") == "abstention_check"
    ]


def provider(runtime, after_notice):
    contexts = []

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        contexts.append(context)
        if not context["history"]:
            return {"name": "search_course_evidence", "arguments": {"query": "first wording"}}
        if "abstention_notice" in context and after_notice == "search":
            return {"name": "search_course_evidence", "arguments": {"query": "course terms"}}
        if len(context["history"]) >= 2 and after_notice == "search":
            context["history"].append({"tool": "read_evidence_window"})
            return MockProvider().decide([{"content": json.dumps(context)}], timeout)
        return REPORT

    runtime.provider.decide = decide
    return contexts


def test_constants_are_defined_once_with_the_reserved_tool_call():
    assert ABSTENTION_NOTICE_MIN_TOOL_CALLS == 2  # one search, then the reserved last call
    assert ABSTENTION_NOTICE_MIN_MODEL_CALLS == 3


def test_first_abstention_is_withheld_and_a_new_search_can_reach_practice(setup):
    _, _, runtime, _ = setup
    contexts = provider(runtime, after_notice="search")
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded", result["run"]["error_code"]
    assert result["artifact"]["kind"] == "practice"
    # The withheld report never executed; the reformulated search did.
    assert started_tools(setup) == ["search_course_evidence", "search_course_evidence", "create_practice_set"]
    assert [p["error_code"] for p in notices(setup)] == ["SEARCH_REQUIRED"]
    with_notice = [c for c in contexts if "abstention_notice" in c]
    assert len(with_notice) == 1 and with_notice[0]["abstention_notice"] == ABSTENTION_NOTICE
    assert all("abstention_notice" not in c for c in contexts if c is not with_notice[0])


def test_a_repeated_abstention_executes_and_is_reviewed(setup):
    _, _, runtime, _ = setup
    provider(runtime, after_notice="report")
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["artifact"]["kind"] == "insufficient_evidence"
    assert started_tools(setup) == ["search_course_evidence", "report_insufficient_evidence"]
    assert len(notices(setup)) == 1


def test_no_notice_when_the_budget_cannot_fit_a_reformulation(setup):
    store, _, runtime, _ = setup
    provider(runtime, after_notice="search")
    run = test_study.start(setup)
    with store.connect() as conn:
        # After the first search one tool call remains: it is reserved for the abstention.
        conn.execute(
            "UPDATE study_run SET tool_calls=%s WHERE run_id=%s", (RUN_TOOL_CALL_LIMIT - 2, run["run_id"])
        )
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["artifact"]["kind"] == "insufficient_evidence"
    assert notices(setup) == []


def test_abstention_after_a_search_in_the_same_response_is_not_withheld(setup):
    _, _, runtime, _ = setup

    def decide(messages, timeout):
        context = json.loads(messages[-1]["content"])
        if not context["history"]:
            return {"name": "search_course_evidence", "arguments": {"query": "first wording"}}
        return {
            "calls": [{"name": "search_course_evidence", "arguments": {"query": "other wording"}}, REPORT]
        }

    runtime.provider.decide = decide
    runtime.execute(test_study.start(setup))
    assert test_study.read(setup)["artifact"]["kind"] == "insufficient_evidence"
    assert notices(setup) == []


def test_notice_state_survives_recovery_and_is_given_only_once(setup):
    from lecturelens_agent.study.store import RunStopped

    _, authority, runtime, _ = setup
    provider(runtime, after_notice="search")
    read = authority.read
    stopped = []

    def interrupted(scope, action="CHECK", **arguments):
        # Stop inside the reformulated search, after the post-notice decision was checkpointed.
        if action == "SEARCH" and arguments.get("query") == "course terms" and not stopped:
            stopped.append(True)
            raise RunStopped()
        return read(scope, action, **arguments)

    authority.read = interrupted
    run = test_study.start(setup)
    runtime.execute(run)
    assert test_study.read(setup)["run"]["status"] == "running" and stopped
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded", result["run"]["error_code"]
    # The interrupted search resumes under its own call ID; no decision or notice is repeated.
    assert started_tools(setup) == ["search_course_evidence", "search_course_evidence", "create_practice_set"]
    assert len(notices(setup)) == 1
