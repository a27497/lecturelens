import json
from types import SimpleNamespace

import pytest

from lecturelens_real_eval.tutor.light import LIGHT_ABSTENTION, LightTutorRuntime
from lecturelens_real_eval.tutor.light_retrieval import MAX_CONTEXT, targeted_queries


@pytest.mark.parametrize(
    "question",
    [
        "What is a semaphore, and when is it initialized?",
        "Why does the loop stop, and how does the caller observe its result?",
        "Explain how a queue works.",
        "Explain the difference between groups.",
        "How does the example at 03:10 start, and what happens next?",
        "At 03:10, what is the invariant? Why does the invariant at 03:10 hold?",
        "什么是信号量？它如何记录可用资源？",
    ],
)
def test_single_topic_and_ambiguous_requests_keep_one_query(question):
    assert targeted_queries(question) == [question]


@pytest.mark.parametrize(
    "question",
    [
        "What is the difference between a queue and a stack?",
        "How does a queue differ from a stack?",
        "How is a queue different from a stack?",
        "How do a queue and a stack differ?",
        "How does a queue compare with a stack?",
        "Which rules govern traversal? Compare a queue and a stack.",
    ],
)
def test_natural_comparisons_find_both_subjects(question):
    assert targeted_queries(question) == [question, "a queue", "a stack"]


def test_chinese_comparison_finds_both_subjects():
    question = "队列和堆栈有什么区别？"
    assert targeted_queries(question) == [question, "队列", "堆栈"]


@pytest.mark.parametrize(
    ("question", "first", "second"),
    [
        (
            "At 03:10, why is the lock acquired, and how is the deadlock resolved at 12:40?",
            "At 03:10, why is the lock acquired",
            "how is the deadlock resolved at 12:40",
        ),
        (
            "Describe lock acquisition at 03:10 and at 12:40 how the deadlock is resolved.",
            "Describe lock acquisition at 03:10",
            "at 12:40 how the deadlock is resolved",
        ),
        (
            "How does the opening example acquire the lock? How does the final example release it?",
            "How does the opening example acquire the lock",
            "How does the final example release it",
        ),
        (
            "前半段如何取得锁？后半段如何解除死锁？",
            "前半段如何取得锁",
            "后半段如何解除死锁",
        ),
    ],
)
def test_explicit_cross_segment_questions_focus_each_location(question, first, second):
    assert targeted_queries(question) == [question, first, second]


def test_runtime_fuses_only_current_authorized_rows_and_rereads_in_bounded_batches():
    calls = []

    class Authority:
        def read(self, scope, action, **arguments):
            calls.append((action, arguments))
            assert scope == {"owner_id": 7, "course_id": "lab", "revision": 2}
            if action == "TUTOR_SEARCH":
                offset = len(calls) - 1
                ids = ["shared", *(f"e{offset}-{i}" for i in range(7))]
            else:
                ids = list(reversed(arguments["evidence_ids"]))
            return {"evidence": [{"evidence_id": eid, "text": f"Evidence {eid}"} for eid in ids]}

    runtime = LightTutorRuntime(SimpleNamespace(engine="light"), Authority())
    state = runtime.prepare(
        {"owner_id": 7, "course_id": "lab", "revision": 2},
        {"learner_text": "Compare mutex ownership and semaphore permits.", "socratic": False},
        [],
    )
    assert len(state["searches"]) == 3
    assert calls[:3] == [
        ("TUTOR_SEARCH", {"query": entry["query"], "tutor_strategy": "HYBRID_16"})
        for entry in state["searches"]
    ]
    assert len(calls[3:]) == 2 and all(len(args["evidence_ids"]) == 8 for _, args in calls[3:])
    context = json.loads(state["messages"][-1]["content"])["current_evidence"]
    assert len(context) == len({r["evidence_id"] for r in context}) == MAX_CONTEXT
    assert state["selected"] == [r["evidence_id"] for r in context]
    assert context[0]["evidence_id"] == "shared"
    assert {eid.split("-")[0] for eid in state["selected"][1:]} == {"e0", "e1", "e2"}
    assert state["abstention"] == LIGHT_ABSTENTION
    assert "formulas or solution steps before" in state["messages"][0]["content"]
