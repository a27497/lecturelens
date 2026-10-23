"""Budget compaction retains sources, method provenance and current observations."""

import json
from copy import deepcopy

import httpx
import pytest

from lecturelens_agent.study.context import build_messages, decision_texts
from lecturelens_agent.study.method_scope import observation_scope, reusable_coverage
from lecturelens_agent.study.provider import request_reservation


def sources():
    return [
        {
            "evidence_id": f"source-{i}",
            "text": f"片段{i}。" + "判断计数是否达到上限。" * 80,
            "start_ms": i * 1000,
            "end_ms": i * 1000 + 1000,
        }
        for i in range(8)
    ]


def coverage():
    return {
        "can_answer": True,
        "evidence_ids": ["source-0"],
        "course_fact": "Check a count",
        "methods": {"m1": {"evidence_id": "source-0", "quote": sources()[0]["text"][:1200]}},
    }


@pytest.mark.parametrize(
    "change,reuse",
    [
        ("overlap", True),
        ("reorder", True),
        ("new_unrelated_hit", True),
        ("source_changed", False),
        ("source_evicted", False),
        ("coverage_source_changed", False),
        ("kind_changed", False),
        ("absent", False),
        ("no_methods", False),
        ("legacy", False),
    ],
)
def test_reuse_requires_positive_observation_and_unchanged_authorized_support(change, reuse):
    evidence = sources()[:6]
    observed = coverage()
    if change == "coverage_source_changed":
        observed["evidence_ids"].append("source-1")
    result = {"course_coverage": observed, "method_observation_scope": observation_scope(evidence, "general")}
    current = deepcopy(evidence)
    kind = "general"
    if change in {"overlap", "new_unrelated_hit"}:
        current[-1] = sources()[6]
    if change == "reorder":
        current.reverse()
    if change == "source_changed":
        current[0]["text"] += "Changed within the observer's input."
    if change == "source_evicted":
        current.pop(0)
    if change == "coverage_source_changed":
        current[1]["text"] = "Different course fact."
    if change == "kind_changed":
        kind = "linear_points"
    if change == "absent":
        observed["can_answer"] = False
    if change == "no_methods":
        observed["methods"] = {}
    if change == "legacy":
        del result["method_observation_scope"]
    history = [{"tool": "search_course_evidence", "result": result}]
    snapshot = deepcopy(history)
    assert (reusable_coverage(history, current, kind) is not None) is reuse
    assert history == snapshot
    # A different mode's intervening search clears the previous observations.
    history.append({"tool": "search_course_evidence", "result": {"practice_kind": "python_strings"}})
    assert reusable_coverage(history, current, kind) is None


def test_context_has_utf8_byte_bound_keeps_method_text_aliases_and_journal():
    evidence = sources()
    observed = coverage()
    history = [
        {
            "tool": "search_course_evidence",
            "arguments": {"query": "first"},
            "result": {
                "practice_kind": "general",
                "course_coverage": observed,
                "method_observation_scope": observation_scope(evidence, "general"),
            },
        },
        {
            "tool": "read_evidence_window",
            "arguments": {"evidence_id": "source-0"},
            "result": {
                "course_coverage": observed,
                "method_observation_scope": observation_scope(evidence, "general"),
            },
        },
    ]
    snapshot = deepcopy(history)
    messages, reverse = build_messages("system", "goal", evidence, history, [])
    body = json.loads(messages[-1]["content"])
    assert sum(len(item["text"].encode()) for item in body["evidence"]) <= 6000
    assert body["evidence"][0]["text"] == evidence[0]["text"][:600]
    assert all(item["text_truncated"] for item in body["evidence"])
    assert set(reverse.values()) == {item["evidence_id"] for item in evidence}
    assert body["evidence_text_policy"]
    assert "course_coverage" not in json.loads(messages[3]["content"])
    assert "method_observation_scope" not in str(messages)
    assert history == snapshot


def test_short_sources_return_unused_share_to_longer_sources_without_unnecessary_truncation():
    evidence = [{"evidence_id": "long", "text": "文" * 600}, {"evidence_id": "short", "text": "Short."}]
    assert decision_texts(evidence, None, byte_limit=2000) == {
        item["evidence_id"]: item["text"] for item in evidence
    }


def test_reservation_uses_httpx_wire_encoding_without_treating_usage_as_reservations():
    messages = [{"role": "user", "content": '解释 "停止条件"。'}]
    schemas = [{"type": "function", "function": {"description": "引用必须属于课程", "parameters": {}}}]
    request = httpx.Request("POST", "https://invalid.test", json={"messages": messages, "tools": schemas})
    estimate = request_reservation(messages, schemas, 900)
    assert estimate["message_bytes"] + estimate["schema_bytes"] == len(request.content) - len(
        b'{"messages":,"tools":}'
    )
    assert estimate["output_tokens"] == 900
    assert estimate["estimator"] == "compact_utf8_bytes_plus_output_tokens_v1"


def test_explicit_reread_expands_a_preview_without_exceeding_the_text_budget():
    evidence = sources()
    observed = coverage()
    observed["methods"]["m2"] = {"evidence_id": "source-1"}
    before = decision_texts(evidence, observed)
    after = decision_texts(evidence, observed, focus="source-7")
    assert len(before["source-7"]) < 600
    assert after["source-7"] == evidence[7]["text"][:600]
    assert after["source-0"] == evidence[0]["text"][:600]
    assert after["source-1"] == evidence[1]["text"][:600]
    assert sum(len(text.encode()) for text in after.values()) <= 6000


def test_four_byte_unicode_preserves_methods_and_nonempty_previews_under_the_hard_byte_bound():
    evidence = [{"evidence_id": f"source-{i}", "text": "🧮" * 650} for i in range(8)]
    observed = {"methods": {f"m{i}": {"evidence_id": f"source-{i}"} for i in range(2)}}
    texts = decision_texts(evidence, observed, focus="source-7")
    assert texts["source-0"] == texts["source-1"] == "🧮" * 600
    assert sum(len(text.encode()) for text in texts.values()) <= 6000
    assert all(texts.values())
    assert len(texts["source-7"]) > len(texts["source-2"])
