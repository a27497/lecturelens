"""Long ASR cues on the two-search, one-window Study path; deterministic mechanics only.

With ASR clip merge on, one subtitle cue covers one merged clip of roughly 100 s. Java
bounds every Evidence text to 1,200 characters, so such a cue reaches the Agent as a
full-size passage cut mid-sentence. The fixture mirrors that shape and Java's SEARCH,
WINDOW and READ selection. Providers are scripted: this pins reservation mechanics, the
stored outcome and the loop guard, never model quality.
"""

import hashlib
import json

import pytest
import test_study
from test_study_goals import goal_verdict

from lecturelens_agent.study import call_journal
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import ModelResponseError
from lecturelens_agent.study.quality import review_contract
from lecturelens_agent.study.store import (
    RUN_MODEL_CALL_LIMIT,
    RUN_RESERVED_TOKEN_LIMIT,
    RUN_TOOL_CALL_LIMIT,
)
from lecturelens_agent.study.support_review import MethodCoverageVerdict

setup = test_study.setup

GOAL = "练习一维峰值查找的分治法：为什么先看中间元素，再向较大邻居的一侧递归？"
CUE_MS = 100_000
SPEECH = (
    "So let's start with the one dimensional version of peak finding, which is the simple case. ",
    "We have an array of numbers, and a position is a peak if it is at least as large as its neighbors. ",
    "The straightforward algorithm walks from the left end and looks at every element until it finds one. ",
    "In the worst case that walk looks at all n elements, so the straightforward algorithm is theta of n. ",
    "Can we do better than that? The answer is yes, and the idea is divide and conquer on the array. ",
    "Look at the middle position n over two and compare it against the element to its left and right. ",
    "If the element on the left is larger, then a peak has to exist somewhere in the left half. ",
    "So we recurse on the left half only, and we throw away the other half of the array completely. ",
    "Otherwise if the element on the right is larger, we recurse on the right half for the same reason. ",
    "And if neither neighbor is larger, then the middle position is itself a peak and we are done. ",
    "Why is this correct? Because going toward the larger neighbor, the values cannot fall forever. ",
    "The work is T of n equals T of n over two plus a constant, since we do one comparison step. ",
    "That recurrence unrolls log n times, so the divide and conquer algorithm is theta of log n. ",
    "For a million elements that is the difference between a million steps and about twenty steps. ",
    "Keep that argument in mind, because the two dimensional version is going to reuse the same idea. ",
)
# Ranked dense hits by cue index. The scripted observer selects the top hit of a search as
# its method source; the second query either keeps that cue (reuse) or drops it (observe again).
FIRST_HITS = (9, 10, 12, 14)
OVERLAPPING_HITS = (10, 9, 16, 12)
SHIFTED_HITS = (10, 16, 12, 17)
FINAL_REVIEW = "field_support_scoped_goals_v1"


def cue_text(index):
    # About 150 words per minute for 100 s is ~1,500 characters; Java keeps the first 1,200.
    spoken = f"Okay, so this is part {index + 1} of the lecture. " + "".join(
        SPEECH[(index + offset) % len(SPEECH)] for offset in range(len(SPEECH))
    )
    assert len(spoken) > 1200
    return spoken[:1200]


def long_cues(count=32):
    # Merged clips are contiguous: each cue starts where the previous one ends.
    return [
        {
            "evidence_id": hashlib.sha256(f"long-cue-{index}".encode()).hexdigest(),
            "text": cue_text(index),
            "start_ms": index * CUE_MS,
            "end_ms": (index + 1) * CUE_MS,
            "source_type": "SUBTITLE",
        }
        for index in range(count)
    ]


def search_context(cues, hits):
    # Java returns the ranked hits, then each hit's next and previous cue, at most eight.
    # A translation hit is replaced by the original speech of the same interval, so an
    # aligned SUBTITLE_TRANSLATION never reaches the Agent on this path.
    picked = list(dict.fromkeys(hits))
    for step in (1, -1):
        for anchor in hits:
            neighbor = anchor + step
            if 0 <= neighbor < len(cues) and len(picked) < 8 and neighbor not in picked:
                picked.append(neighbor)
    return [cues[index] for index in picked]


def long_cue_scenario(
    setup, monkeypatch, *, second_hits=OVERLAPPING_HITS, retry=None, keep_searching=False, cues=None
):
    """Batched searches, one explicit window read, then one candidate and its review.

    `retry` is (review stage, occurrence): that call violates the protocol once, as a real
    provider did on a course-method observation. `keep_searching` replaces the script with
    a model that only ever asks for another search whose hits drop the observed method.
    """
    store, authority, runtime, scope = setup
    cues = cues or long_cues()
    position = {cue["evidence_id"]: index for index, cue in enumerate(cues)}
    original = authority.read
    searches = []
    requests = []
    begin = call_journal.begin

    def record_request(*args, **kwargs):
        requests.append({"tokens": args[4], "metadata": args[5], "detail": args[6]})
        return begin(*args, **kwargs)

    monkeypatch.setattr(call_journal, "begin", record_request)

    def read(run, action="CHECK", **kwargs):
        response = original(run, action, **kwargs)
        if action == "SEARCH":
            first = 5 * len(searches) + 2
            hits = (
                tuple(range(first, first + 4)) if keep_searching else second_hits if searches else FIRST_HITS
            )
            picked = search_context(cues, hits)
            searches.append([position[cue["evidence_id"]] for cue in picked])
        elif action == "WINDOW":
            anchor = position[kwargs["evidence_id"]]
            picked = cues[max(0, anchor - 1) : anchor + 2]
        elif action == "READ":
            picked = [cue for cue in cues if cue["evidence_id"] in kwargs["evidence_ids"]]
        else:
            picked = []
        return {**response, "evidence": [dict(cue) for cue in picked]}

    def search(query):
        return {"name": "search_course_evidence", "arguments": {"query": query, "practice_kind": "general"}}

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if keep_searching:
            return search(f"peak finding, attempt {len(body['history']) + 1}")
        if not body["history"]:
            return {
                "calls": [
                    search("一维峰值查找 分治 看中间元素 divide and conquer middle element"),
                    search("为什么向更大的邻居一侧递归 recurse toward the larger neighbor"),
                ]
            }
        ref = body["course_coverage"]["methods"]["m1"]["evidence_id"]
        if len(body["history"]) == 2:
            return {"name": "read_evidence_window", "arguments": {"evidence_id": ref}}
        return {
            "name": "create_practice_set",
            "arguments": {
                "title": "一维峰值查找的分治法",
                "explanation": (
                    "课程先比较中间位置 n/2 与它左右两个相邻元素：如果某一侧的邻居更大，"
                    "那一半里一定存在峰值，于是只在那一半递归。"
                    "每一步只做常数次比较并丢掉一半数组，所以总代价是 Θ(log n)。"
                ),
                "evidence_ids": [ref],
                "concept": {
                    "question": "为什么比较中间元素和邻居之后，可以只在较大邻居所在的一半继续查找？",
                    "answer_points": ["朝更大的邻居方向取值不会一直下降，所以那一半必然含有峰值。"],
                    "evidence_ids": [ref],
                },
                "application": {
                    "question": (
                        "数组为 [1, 3, 4, 7, 6, 5, 2]。按课程的分治法，先看下标 3 的元素 7，"
                        "接下来应该向哪一侧递归，还是可以直接停止？写出比较过程。"
                    ),
                    "answer_points": [
                        "7 的左邻居 4 和右邻居 6 都不比它大，所以 7 本身就是峰值。",
                        "不需要再向任何一侧递归，直接停止。",
                    ],
                    "evidence_ids": [ref],
                },
                "method_id": "m1",
            },
        }

    seen = {}

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        stage = body["review_mode"]
        seen[stage] = seen.get(stage, 0) + 1
        if retry == (stage, seen[stage]):
            raise ModelResponseError(
                "MODEL_REVIEW_CONTRACT",
                {"prompt_tokens": 2933, "completion_tokens": 251},
                {"stage": "review_schema"},
            )
        if stage == "course_methods_v1":
            data = {
                "course_fact": "课程用分治法查找一维峰值：比较中间元素和左右邻居，再向更大的一侧递归。",
                "evidence_ids": ["e1"],
                "support": "direct",
                "missing_goal_quote": "",
                "methods": [
                    {
                        "operation": "比较中间元素与左右邻居，向更大的邻居一侧递归",
                        "input": "一维数组和当前查找范围",
                        "output": "峰值位置，或下一步要递归的一半",
                        "evidence_id": "e1",
                    }
                ],
            }
            result = MethodCoverageVerdict.model_validate(data, context=body).review()
        else:
            data = goal_verdict(body)
            data["application_method_check"] = data["checks"][2].pop("method_alignment")
            result = review_contract(review_mode=stage).model_validate(data, context=body).review()
        return {"review": result.model_dump()}

    authority.read = read
    runtime.provider.decide, runtime.provider.review = decide, review
    started = store.command(
        StudyCommand(**scope, operation="START", request_key="long-cue-run", goal=GOAL), "mock"
    )
    run = next(row for row in store.candidates() if row["run_id"] == started["run"]["run_id"])
    runtime.execute(run)
    response = test_study.read(setup)
    events = test_study.read(setup, "EVENTS")["events"]
    with store.connect() as conn:
        models = conn.execute(
            "SELECT metadata,reserved_tokens FROM study_model_call WHERE run_id=%s "
            "ORDER BY (metadata->>'attempt')::int",
            (run["run_id"],),
        ).fetchall()
        tools = conn.execute(
            "SELECT tool_name,result FROM study_tool_result WHERE run_id=%s", (run["run_id"],)
        ).fetchall()
    summary = {
        key: response["run"][key]
        for key in ("status", "error_code", "model_calls", "tool_calls", "reserved_tokens")
    }
    failed_attempts = {e["payload"]["attempt"] for e in events if e["event_type"] == "model_failed"}
    summary.update(
        reservations=[row["reserved_tokens"] for row in models],
        # A trailing "!" marks the attempt whose response violated the protocol.
        stages=[
            row["metadata"].get("review_stage", row["metadata"]["purpose"])
            + ("!" if row["metadata"]["attempt"] in failed_attempts else "")
            for row in models
        ],
        reused_observations=sum(bool(row["result"].get("reused_method_observation")) for row in tools),
        requested_reservations=[item["tokens"] for item in requests],
        budget_rejected=next((e["payload"] for e in events if e["event_type"] == "budget_rejected"), None),
        searches=searches,
    )
    print("LONG_CUE_BUDGET", json.dumps({"retry": retry, **summary}, sort_keys=True))
    return response, summary, requests


OBSERVE, FAILED_OBSERVE = "course_methods_v1", "course_methods_v1!"
# Reservations are the compact UTF-8 bytes of the wire messages and schemas plus the output
# allowance, so they do not depend on the Run limits. A prompt, schema or evidence-bound
# change moves these sequences and has to update them deliberately.
# name: (second search hits, failing review, method source cue, stages, reservations)
PATHS = {
    "reused_observation": (
        OVERLAPPING_HITS,
        None,
        9,
        ["decision", OBSERVE, "decision", "decision", FINAL_REVIEW],
        [4587, 13263, 15907, 16365, 18725],
    ),
    "second_observation": (
        SHIFTED_HITS,
        None,
        10,
        ["decision", OBSERVE, OBSERVE, "decision", "decision", FINAL_REVIEW],
        [4587, 13263, 13263, 15907, 16407, 18725],
    ),
    "reused_observation_retried": (
        OVERLAPPING_HITS,
        (OBSERVE, 1),
        9,
        ["decision", FAILED_OBSERVE, OBSERVE, "decision", "decision", FINAL_REVIEW],
        [4587, 13263, 13567, 15907, 16365, 18725],
    ),
    "reused_observation_final_review_retried": (
        OVERLAPPING_HITS,
        (FINAL_REVIEW, 1),
        9,
        ["decision", OBSERVE, "decision", "decision", FINAL_REVIEW + "!", FINAL_REVIEW],
        [4587, 13263, 15907, 16365, 18725, 19029],
    ),
    # The recorded Run with a protocol retry: the second search's observation failed once.
    "second_observation_retried": (
        SHIFTED_HITS,
        (OBSERVE, 2),
        10,
        ["decision", OBSERVE, FAILED_OBSERVE, OBSERVE, "decision", "decision", FINAL_REVIEW],
        [4587, 13263, 13263, 13567, 15907, 16407, 18725],
    ),
    "second_observation_final_review_retried": (
        SHIFTED_HITS,
        (FINAL_REVIEW, 1),
        10,
        ["decision", OBSERVE, OBSERVE, "decision", "decision", FINAL_REVIEW + "!", FINAL_REVIEW],
        [4587, 13263, 13263, 15907, 16407, 18725, 19029],
    ),
}


@pytest.mark.parametrize("path", list(PATHS))
def test_long_cue_searches_window_and_review_persist_one_practice_artifact(setup, monkeypatch, path):
    second_hits, retry, method_cue, stages, reservations = PATHS[path]
    response, summary, _ = long_cue_scenario(setup, monkeypatch, second_hits=second_hits, retry=retry)
    # A budget stop reports its diagnostics here instead of a bare status mismatch.
    assert response["run"]["status"] == "succeeded", summary
    assert response["run"]["error_code"] is None and summary["budget_rejected"] is None
    artifact = response["artifact"]
    assert artifact["kind"] == "practice" and artifact["explanation"]
    assert len(artifact["questions"]) == 2
    assert len(test_study.read(setup, "ANSWERS")["questions"]) == 2
    events = test_study.read(setup, "EVENTS")["events"]
    assert sum(e["event_type"] == "artifact_created" for e in events) == 1
    assert sum(e["event_type"] == "quality_checked" for e in events) == 1
    assert sum(e["event_type"] == "protocol_retry_scheduled" for e in events) == (1 if retry else 0)
    store = setup[0]
    with store.connect() as conn:
        private = conn.execute(
            "SELECT content FROM study_artifact WHERE run_id=%s", (response["run"]["run_id"],)
        ).fetchone()["content"]
    assert private["questions"][1]["evidence_ids"][0] == long_cues()[method_cue]["evidence_id"]
    assert private["questions"][1]["answer_points"][1] == "不需要再向任何一侧递归，直接停止。"
    # Every cue is cut mid-sentence by the 1,200-character bound, so citation completion
    # follows the contiguous selected cues: one cited cue brings six full-size sources.
    assert len(artifact["citations"]) == 6
    assert all(len(item["text"]) == 1200 for item in artifact["citations"])

    assert summary["stages"] == stages
    assert summary["reservations"] == summary["requested_reservations"] == reservations
    assert summary["reserved_tokens"] == sum(reservations)
    assert summary["model_calls"] == len(reservations) <= RUN_MODEL_CALL_LIMIT
    assert summary["tool_calls"] == 4 <= RUN_TOOL_CALL_LIMIT
    assert summary["reused_observations"] == (2 if second_hits == OVERLAPPING_HITS else 1)
    # Headroom: the heaviest variant (two observations plus a final-review retry) reserves
    # 101,181 over seven model calls. Model calls, not reservations, are the nearer limit.
    assert summary["reserved_tokens"] <= 101181 < RUN_RESERVED_TOKEN_LIMIT
    assert summary["model_calls"] <= 7 < RUN_MODEL_CALL_LIMIT


def test_model_that_only_keeps_searching_is_stopped_by_the_model_call_limit_without_artifact(
    setup, monkeypatch
):
    # Each search that loses the observed method costs one decision and one observation
    # but a single tool call, so the model-call limit is the guard that ends this loop.
    assert RUN_MODEL_CALL_LIMIT < 2 * RUN_TOOL_CALL_LIMIT
    cues = long_cues(5 * (RUN_MODEL_CALL_LIMIT // 2 + 1) + 8)
    response, summary, requests = long_cue_scenario(setup, monkeypatch, keep_searching=True, cues=cues)
    assert response["run"]["status"] == "budget_exceeded" and response["artifact"] is None
    assert response["run"]["error_code"] == "RUN_BUDGET_EXCEEDED"
    rejected = summary["budget_rejected"]
    assert rejected["reason"] == "model_calls"
    assert rejected["model_calls"] == rejected["model_call_limit"] == RUN_MODEL_CALL_LIMIT
    assert summary["model_calls"] == RUN_MODEL_CALL_LIMIT
    assert summary["tool_calls"] == rejected["tool_calls"] == RUN_MODEL_CALL_LIMIT // 2
    assert summary["reused_observations"] == 0
    assert summary["stages"].count(OBSERVE) == RUN_MODEL_CALL_LIMIT // 2
    # The rejected request is sized but never reserved, and nothing else stopped the Run first.
    assert len(requests) == RUN_MODEL_CALL_LIMIT + 1
    assert summary["reserved_tokens"] == sum(summary["reservations"]) < RUN_RESERVED_TOKEN_LIMIT
    assert rejected["requested_tokens"] == summary["requested_reservations"][-1]
    assert rejected["reserved_tokens"] == summary["reserved_tokens"]
    events = test_study.read(setup, "EVENTS")["events"]
    assert not any(e["event_type"] == "artifact_created" for e in events)
