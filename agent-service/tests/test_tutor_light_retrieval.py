import json
from types import SimpleNamespace

import pytest

from lecturelens_real_eval.tutor.light import LIGHT_ABSTENTION, LightTutorRuntime
from lecturelens_real_eval.tutor.light_retrieval import MAX_CONTEXT, retrieve_context, targeted_queries


def test_queries_focus_compared_subjects_and_separate_interrogatives():
    assert targeted_queries("Explain the difference between groups.") == [
        "Explain the difference between groups."
    ]
    assert targeted_queries("What is the difference between a queue and a stack?")[1:] == [
        "a queue",
        "a stack",
    ]
    assert targeted_queries("How does a queue differ from a stack?")[1:] == ["a queue", "a stack"]
    assert targeted_queries("How is a queue different from a stack?")[1:] == ["a queue", "a stack"]
    assert targeted_queries("How do a queue and a stack differ?")[1:] == ["a queue", "a stack"]
    assert targeted_queries("How does a queue compare with a stack?")[1:] == ["a queue", "a stack"]
    assert targeted_queries("队列和堆栈有什么区别？")[1:] == ["队列", "堆栈"]
    assert targeted_queries("Why does the loop stop, and how does the caller observe its result?")[1:] == [
        "Why does the loop stop",
        "how does the caller observe its result",
    ]
    assert targeted_queries("Explain how a queue works.") == ["Explain how a queue works."]


@pytest.mark.parametrize(
    ("question", "history", "wire_queries", "split"),
    [
        ("  What is a queue?  ", [], b'["What is a queue?"]', False),
        (
            "What is a queue?",
            [{"learner_text": "Earlier topic"}],
            b'["What is a queue?", "Earlier topic\\nEarlier topic"]',
            False,
        ),
        (
            "How does a queue differ from a stack?",
            [{"learner_text": "Earlier topic"}],
            b'["How does a queue differ from a stack?", "a queue", "a stack"]',
            True,
        ),
        (
            "Why does the loop stop, and how does the caller observe its result?",
            [],
            b'["Why does the loop stop, and how does the caller observe its result?", '
            b'"Why does the loop stop", "how does the caller observe its result"]',
            True,
        ),
    ],
)
def test_selective_neighbors_preserve_main_query_bytes(question, history, wire_queries, split):
    class Authority:
        def __init__(self):
            self.calls = []

        def read(self, scope, action, *, query, tutor_strategy):
            assert action == "TUTOR_SEARCH"
            self.calls.append((query, tutor_strategy))
            ids = [query]
            if tutor_strategy == "HYBRID_8_NEIGHBORS":
                ids.append(f"{query} neighbor")
            return {"evidence": [{"evidence_id": eid} for eid in ids]}

    main, all_queries, selective = Authority(), Authority(), Authority()
    main_context = retrieve_context(main, {}, question, history, simple="HYBRID_8")
    all_context = retrieve_context(all_queries, {}, question, history, complex_="HYBRID_8_NEIGHBORS")
    selective_context = retrieve_context(selective, {}, question, history)
    for arm in (main, all_queries, selective):
        assert json.dumps([query for query, _ in arm.calls], ensure_ascii=False).encode() == wire_queries
    assert {strategy for _, strategy in main.calls} == {"HYBRID_16" if split else "HYBRID_8"}
    assert {strategy for _, strategy in all_queries.calls} == {"HYBRID_8_NEIGHBORS"}
    assert {strategy for _, strategy in selective.calls} == {"HYBRID_16" if split else "HYBRID_8_NEIGHBORS"}
    if split:
        assert selective.calls == main.calls and selective_context == main_context
        assert all_context != selective_context
    else:
        assert selective.calls == all_queries.calls and selective_context == all_context
        assert main_context != selective_context


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
