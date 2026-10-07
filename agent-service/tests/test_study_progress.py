import json

import pytest
from test_study import read, setup, start  # noqa: F401

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.progress import coverage_fingerprint, evidence_fingerprint
from lecturelens_agent.study.provider import decision_schemas


def test_progress_identity_preserves_goal_authority_and_window():
    scope = {"owner_id": 42, "course_id": "one", "revision": 1}
    evidence = [{"evidence_id": "a", "text": "same window", "start_ms": 0, "end_ms": 1000}]
    semantic = {"resolved_goal": "Explain the second method"}
    original = coverage_fingerprint(scope, semantic, evidence, "general")
    assert original == coverage_fingerprint(scope, semantic, list(reversed(evidence)), "general")
    for changed in ({**scope, "owner_id": 43}, {**scope, "course_id": "two"}, {**scope, "revision": 2}):
        assert original != coverage_fingerprint(changed, semantic, evidence, "general")
    assert original != coverage_fingerprint(
        scope, {"resolved_goal": "Explain the first method"}, evidence, "general"
    )
    assert evidence_fingerprint(scope, evidence) != evidence_fingerprint(
        scope, [{**evidence[0], "text_start": 200}]
    )


@pytest.mark.parametrize("kind", ["general", "interval_halving", "python_strings", "search_cost"])
@pytest.mark.parametrize(
    "condition", [{"no_progress": True}, {"budget": {"model_calls_left_after_response": 1}}]
)
def test_no_progress_or_low_budget_preserves_final_review_for_all_subjects(kind, condition):
    schemas = decision_schemas(
        [
            {"role": "user", "content": json.dumps({"goal": "Explain the current result"})},
            {"role": "tool", "content": json.dumps({"practice_kind": kind, **condition})},
        ]
    )
    names = {tool["function"]["name"] for tool in schemas}
    assert "create_explanation" in names and "report_insufficient_evidence" in names
    assert not names & {"search_course_evidence", "read_evidence_window", "check_python_example"}


def test_model_selected_explanation_workflow_keeps_reads_and_atomic_candidate_tool():
    schemas = decision_schemas(
        [
            {"role": "user", "content": json.dumps({"goal": "Explain the observed method"})},
            {
                "role": "tool",
                "content": json.dumps({"practice_kind": "general", "output_kind": "explanation"}),
            },
        ]
    )
    assert {t["function"]["name"] for t in schemas} == {
        "search_course_evidence",
        "read_evidence_window",
        "create_explanation",
        "report_insufficient_evidence",
    }


@pytest.mark.parametrize("remaining,reads", [(12000, False), (64000, True)])
def test_byte_budget_reserves_a_decision_and_final_review_before_more_observations(remaining, reads):
    schemas = decision_schemas(
        [
            {"role": "user", "content": json.dumps({"goal": "Explain the observed method"})},
            {
                "role": "tool",
                "content": json.dumps(
                    {
                        "output_kind": "explanation",
                        "practice_kind": "general",
                        "budget": {
                            "model_calls_left_after_response": 4,
                            "reserved_bytes_and_output_left": remaining,
                        },
                    }
                ),
            },
        ]
    )
    names = {s["function"]["name"] for s in schemas}
    assert {"create_explanation", "report_insufficient_evidence"} <= names
    assert ("search_course_evidence" in names) is reads
    assert ("read_evidence_window" in names) is reads


def test_explanation_search_does_not_spend_a_practice_method_review(setup):  # noqa: F811
    store, _, runtime, scope = setup

    def decide(messages, timeout):
        if not any(m["role"] == "tool" for m in messages):
            return {
                "name": "search_course_evidence",
                "arguments": {
                    "query": "stopping rule",
                    "practice_kind": "general",
                    "output_kind": "explanation",
                },
            }
        return {
            "name": "create_explanation",
            "arguments": {
                "title": "Stopping",
                "explanation": "An algorithm needs a stopping condition.",
                "evidence_ids": ["e1"],
            },
        }

    stages = []
    review = runtime.provider.review

    def tracked_review(messages, timeout):
        stages.append(json.loads(messages[-1]["content"]).get("review_mode"))
        return review(messages, timeout)

    runtime.provider.decide = decide
    runtime.provider.review = tracked_review
    response = store.command(
        StudyCommand(
            **scope, operation="START", request_key="explanation", goal="Explain the stopping condition."
        ),
        "mock",
    )
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"]))
    assert read(setup)["run"]["status"] == "succeeded"
    assert stages == ["atomic_answer_spans_v2"]
    assert read(setup)["run"]["model_calls"] == 3


def test_window_progress_compares_the_current_authorized_read_not_old_search(setup):  # noqa: F811
    store, authority, runtime, scope = setup
    original_read = authority.read

    def updated_read(scope, action="CHECK", **arguments):
        result = original_read(scope, action, **arguments)
        if action in {"READ", "WINDOW"}:
            for item in result["evidence"]:
                item["text"] += " The stopping rule is already present in this window."
        return result

    authority.read = updated_read

    def decide(messages, timeout):
        tools = [m for m in messages if m["role"] == "tool"]
        if not tools:
            return {
                "name": "search_course_evidence",
                "arguments": {
                    "query": "stopping rule",
                    "practice_kind": "general",
                    "output_kind": "explanation",
                },
            }
        if len(tools) == 1:
            return {"name": "read_evidence_window", "arguments": {"evidence_id": "e1"}}
        assert json.loads(tools[-1]["content"])["no_progress"]
        return {
            "name": "create_explanation",
            "arguments": {
                "title": "Stopping",
                "explanation": "An algorithm needs a stopping condition.",
                "evidence_ids": ["e1"],
            },
        }

    runtime.provider.decide = decide
    response = store.command(
        StudyCommand(
            **scope, operation="START", request_key="window", goal="Explain the stopping condition."
        ),
        "mock",
    )
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"]))
    assert read(setup)["run"]["status"] == "succeeded"
    with store.connect() as conn:
        result = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='read_evidence_window'",
            (response["run"]["run_id"],),
        ).fetchone()["result"]
    assert result["no_progress"] is True


@pytest.mark.parametrize("crash", [False, True])
def test_different_anchors_with_identical_observations_do_not_repeat_coverage(setup, crash):  # noqa: F811
    store, _, runtime, _ = setup
    coverage_calls = []

    def decide(messages, timeout):
        tools = [m for m in messages if m["role"] == "tool"]
        if not tools:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "stopping rule", "practice_kind": "general"},
            }
        if len(tools) == 1:
            return {
                "calls": [
                    {"name": "read_evidence_window", "arguments": {"evidence_id": ref}}
                    for ref in ["e1", "e2"]
                ]
            }
        assert json.loads(tools[-1]["content"])["no_progress"]
        return {
            "name": "report_insufficient_evidence",
            "arguments": {"reason": "These observed passages do not support this requested topic."},
        }

    original_review = runtime.provider.review

    def review(messages, timeout):
        if json.loads(messages[-1]["content"]).get("review_mode") == "course_methods_v1":
            coverage_calls.append(messages)
            return {
                "review": {
                    "issues": [],
                    "feedback": "Absent; protocol fixture only.",
                    "method_observations": [],
                }
            }
        return original_review(messages, timeout)

    runtime.provider.decide, runtime.provider.review = decide, review
    run = start(setup)
    original_save = store.save_tool
    if crash:

        def save(*args, **kwargs):
            result = original_save(*args, **kwargs)
            if args[3] == "read_evidence_window":
                store.save_tool = original_save
                raise SystemExit("after durable observation")
            return result

        store.save_tool = save
        with pytest.raises(SystemExit):
            runtime.execute(run)
    runtime.execute(run)
    assert read(setup)["run"]["status"] == "succeeded"
    assert len(coverage_calls) == 1
    assert read(setup)["run"]["model_calls"] == 5
    with store.connect() as conn:
        results = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='read_evidence_window'",
            (run["run_id"],),
        ).fetchall()
    assert len(results) == 2
    assert all(r["result"]["no_progress"] and r["result"]["reused_method_observation"] for r in results)
