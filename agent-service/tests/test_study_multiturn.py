import json

import pytest
from test_study import read, setup, start  # noqa: F401 -- shared isolated PostgreSQL fixture

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.semantic import resolve_goal, review_goal, semantic_context


def test_explanation_review_keeps_raw_followup_demand_without_losing_resolved_referent():
    context = resolve_goal(
        semantic_context(
            "What does the second method do in more detail?",
            [{"explanation": "The first method scans. The second method halves its input."}],
        ),
        "Expand every equation in the second method through each recurrence level.",
    )
    assert review_goal(context, "explanation") == context["raw_question"]
    assert context["resolved_goal"].startswith("Expand every equation")
    assert review_goal(context, "practice") == context["resolved_goal"]


@pytest.mark.parametrize(
    "raw,resolved",
    [
        ("那它为什么最后会得到 log n？", "解释 T(n)=T(n/2)+Θ(1) 的递归层数为何是 log n。"),
        (
            "你刚才引用的那段里，老师接下来是怎么说的？",
            "延续上一轮运行时间比较的引用片段，解释老师接下来的结论。",
        ),
        ("你刚才说的第二种是什么意思？再具体一点。", "进一步解释上一轮比较中的分治算法。"),
        (
            "用一个更简单的例子解释你刚才那句话。",
            "用更简单的课程支持例子解释上一轮 Θ(n) 与 Θ(log n) 的比较。",
        ),
        ("那一直这样递归下去，数组最后变成什么样？", "解释分治峰值查找递归的终止子数组和基本情况。"),
    ],
)
def test_one_model_selected_goal_is_shared_with_coverage_and_final_review(setup, raw, resolved):  # noqa: F811
    store, _, runtime, scope = setup
    runtime.execute(start(setup))
    previous = read(setup)["artifact"]
    request = store.command(
        StudyCommand(**scope, operation="START", request_key="follow-up", goal=raw), "mock"
    )
    run = next(r for r in store.candidates() if r["run_id"] == request["run"]["run_id"])
    original_decide, original_review = runtime.provider.decide, runtime.provider.review
    seen = []

    def decide(messages, timeout):
        first = json.loads(messages[1]["content"])
        seen.append(first["semantic_context"])
        result = original_decide(messages, timeout)
        if result["name"] == "search_course_evidence":
            result["arguments"].update(resolved_goal=resolved, practice_kind="general")
        elif result["name"] == "create_practice_set":
            arguments = result["arguments"]
            questions = arguments.pop("questions")
            arguments.update(concept=questions[0], application=questions[1], method_id="m1")
        return result

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        assert body["goal"] == resolved
        assert body["semantic_context"]["raw_question"] == raw
        assert body["semantic_context"]["resolved_goal"] == resolved
        seen.append(body["semantic_context"])
        if body.get("review_mode") == "course_methods_v1":
            return {
                "review": {
                    "issues": ["unjustified_abstention"],
                    "feedback": "Protocol fixture; not a semantic assessment.",
                    "method_observations": [
                        {
                            "operation": "choose a stopping condition",
                            "input": "algorithm",
                            "output": "a stopping rule",
                            "evidence_id": "e1",
                            "quote": body["evidence"][0]["text"],
                        }
                    ],
                }
            }
        return original_review(messages, timeout)

    runtime.provider.decide, runtime.provider.review = decide, review
    runtime.execute(run)
    assert read(setup)["run"]["status"] == "succeeded"
    assert all(s["previous_turns"][0]["artifact_id"] == previous["artifact_id"] for s in seen)
    assert seen[0]["previous_turns"][0]["evidence_references"]
    assert all(s["resolved_goal"] == resolved for s in seen[1:])


def test_resolved_goal_is_frozen_across_retrieval_retries():
    context = semantic_context("how about that one?", [{"goal": "compare two methods"}])
    frozen = resolve_goal(context, "explain the second method")
    assert resolve_goal(frozen, "change the task") == frozen
    assert context["resolved"] is False


def test_decision_context_keeps_continuation_times_without_duplicate_historical_citations():
    from lecturelens_agent.study.context import build_messages

    previous = {
        "artifact_id": "old-artifact",
        "kind": "explanation",
        "goal": "compare",
        "explanation": "Teacher measured the same input.",
        "evidence_ids": ["old-source"],
        "evidence_references": [
            {"evidence_id": "old-source", "start_ms": 100, "end_ms": 200},
            {"evidence_id": "old-translation", "start_ms": 100, "end_ms": 200},
        ],
    }
    semantic = semantic_context("What came next?", [previous])
    messages, _ = build_messages("Teach", "What came next?", [], [], [previous], semantic=semantic)
    visible = json.loads(messages[1]["content"])["semantic_context"]["previous_turns"][0]
    assert visible["artifact_id"] == previous["artifact_id"]
    assert visible["explanation"] == previous["explanation"]
    assert visible["evidence_references"] == [{"start_ms": 100, "end_ms": 200}]
    assert "old-source" not in messages[1]["content"]
    assert semantic["previous_turns"][0] == previous


def test_followup_first_read_freezes_goal_without_search_even_when_ledger_empty(setup):  # noqa: F811
    store, authority, runtime, scope = setup
    decisions, observations = [], []
    original_read = authority.read

    def course_read(s, action="CHECK", **arguments):
        assert "resolved_goal" not in arguments
        observations.append(action)
        return original_read(s, action, **arguments)

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        decisions.append(body)
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "stopping", "practice_kind": "general", "output_kind": "explanation"},
            }
        if body.get("semantic_context", {}).get("previous_turns") and not body["history"]:
            return {
                "name": "read_evidence_window",
                "arguments": {
                    "evidence_id": "e1",
                    "resolved_goal": "Explain the stopping condition from the prior answer.",
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

    # Deterministic acceptance verifies orchestration only, never quality.
    runtime.provider.decide = decide
    authority.read = course_read
    initial = store.command(
        StudyCommand(**scope, operation="START", request_key="explanation", goal="Explain stopping."), "mock"
    )
    runtime.execute(next(r for r in store.candidates() if r["run_id"] == initial["run"]["run_id"]))
    assert read(setup)["artifact"]["kind"] == "explanation"
    requested = store.command(
        StudyCommand(
            **scope, operation="START", request_key="read-followup", goal="Explain that more concretely."
        ),
        "mock",
    )
    follow = next(r for r in store.candidates() if r["run_id"] == requested["run"]["run_id"])
    assert store.supported_facts(follow) == []
    before = observations.count("SEARCH")
    runtime.execute(follow)
    assert read(setup)["run"]["status"] == "succeeded"
    assert observations.count("SEARCH") == before and "WINDOW" in observations
    latest = decisions[-1]
    assert latest["goal"] == "Explain the stopping condition from the prior answer."
    assert latest["output_kind"] == "explanation"
    with store.connect() as conn:
        tool = conn.execute(
            "SELECT arguments FROM study_tool_result WHERE run_id=%s AND tool_name='read_evidence_window'",
            (follow["run_id"],),
        ).fetchone()
    assert tool["arguments"]["resolved_goal"] == latest["goal"]


@pytest.mark.parametrize("ambiguous", [False, True])
def test_verified_hash_context_survives_tool_checkpoint_and_read(setup, ambiguous):  # noqa: F811
    store, authority, runtime, _ = setup
    original = authority.read
    calls = []
    from hashlib import sha256

    excerpt = "An algorithm needs a stopping condition."
    fingerprint = sha256(excerpt.encode()).hexdigest()

    def read_context(scope, action="CHECK", **arguments):
        result = original(scope, action, **arguments)
        if action != "CHECK":
            calls.append((action, arguments))
            if action in {"READ", "WINDOW"}:
                assert arguments["hit_hashes"] == {"e1": fingerprint, "e2": fingerprint}
                assert arguments["hit_spans"] == (
                    {}
                    if ambiguous
                    else {"e1": {"start": 0, "end": len(excerpt)}, "e2": {"start": 0, "end": len(excerpt)}}
                )
            for item in result["evidence"]:
                item.update(
                    match_hash=fingerprint, match_resolution="AMBIGUOUS_TEXT" if ambiguous else "UNIQUE_HASH"
                )
                if not ambiguous:
                    item.update(match_start=0, match_end=len(excerpt))
        return result

    authority.read = read_context
    original_save = store.save_tool

    def save(*args, **kwargs):
        result = original_save(*args, **kwargs)
        if result.get("evidence_contexts"):
            store.save_tool = original_save
            raise SystemExit("after persisted verified match context")
        return result

    store.save_tool = save
    with pytest.raises(SystemExit):
        runtime.execute(start(setup))
    runtime.execute(start(setup))
    assert read(setup)["run"]["status"] == "succeeded"
    assert any(action == "READ" for action, _ in calls)


@pytest.mark.parametrize("output_kind", [None, "explanation"])
def test_ambiguous_verified_match_is_not_lost_to_same_interval_deduplication(output_kind):
    from lecturelens_agent.study.context import build_messages

    evidence = [
        dict(
            evidence_id="original",
            text="An earlier source prefix.",
            start_ms=10,
            end_ms=20,
            source_type="SUBTITLE",
        ),
        dict(
            evidence_id="translation",
            text="Verified matched tail only.",
            start_ms=10,
            end_ms=20,
            source_type="SUBTITLE_TRANSLATION",
            match_hash="a" * 64,
            match_resolution="AMBIGUOUS_TEXT",
        ),
    ]
    messages, aliases = build_messages(
        "system",
        "explain matched tail",
        evidence,
        [
            {
                "tool": "search_course_evidence",
                "arguments": {"query": "matched tail"},
                "result": {"evidence_ids": ["original", "translation"], "output_kind": output_kind},
            }
        ],
        [],
    )
    visible = json.loads(messages[-1]["content"])["evidence"]
    assert "Verified matched tail only." in [item["text"] for item in visible]
    assert "translation" in aliases.values()
