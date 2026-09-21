import json

from lecturelens_agent.study.context import aliases_in, build_messages, has_time_request


def test_compact_context_deduplicates_timeline_and_round_trips_canonical_ids():
    evidence = [
        {
            "evidence_id": "source-" + str(i) * 40,
            "text": "reference " * 200,
            "start_ms": i // 2 * 1000,
            "end_ms": (i // 2 + 1) * 1000,
        }
        for i in range(8)
    ]
    history = [
        {
            "tool": "search_course_evidence",
            "call_id": "long-run-identifier:0",
            "arguments": {"query": "why"},
            "result": {"evidence_ids": [item["evidence_id"] for item in evidence]},
        }
    ]
    messages, reverse = build_messages("system", "goal", evidence, history, [])
    context = json.loads(messages[-1]["content"])
    assert len(context["evidence"]) == 4
    assert all(len(item["text"]) == 600 for item in context["evidence"])
    assert all(item["evidence_id"] in reverse for item in context["evidence"])
    restored = aliases_in(
        {"evidence_ids": ["e1"], "questions": [{"evidence_ids": ["e3"]}], "reason": "e1"}, reverse
    )
    assert restored["evidence_ids"] == [evidence[0]["evidence_id"]]
    assert restored["questions"][0]["evidence_ids"] == [evidence[2]["evidence_id"]]
    assert restored["reason"] == "e1"  # Free text is not rewritten.
    assert "e2" not in reverse  # A duplicate with no visible text cannot be cited.
    assert "reference" not in json.dumps(history)


def test_context_of_new_turn_keeps_goal_and_empty_tool_state_with_prior_summary():
    messages, reverse = build_messages("system", "new goal", [], [], [{"title": "previous"}])
    context = json.loads(messages[-1]["content"])
    assert context["goal"] == "new goal" and context["evidence"] == [] and context["history"] == []
    assert context["previous_turns"] == [{"title": "previous"}] and reverse == {}


def test_visual_evidence_is_not_dropped_as_duplicate_speech():
    evidence = [
        {"evidence_id": kind, "source_type": kind, "text": kind, "start_ms": 1000, "end_ms": 2000}
        for kind in ["SUBTITLE", "SUBTITLE_TRANSLATION", "OCR"]
    ]
    history = [{"tool": "search_course_evidence", "arguments": {"query": "diagram"}, "result": {}}]
    messages, reverse = build_messages("system", "goal", evidence, history, [])
    assert set(reverse.values()) == {"SUBTITLE", "OCR"}
    assert all(item["start_ms"] == 1000 for item in json.loads(messages[-1]["content"])["evidence"])


def test_time_filter_requires_explicit_time_in_learner_goal():
    assert has_time_request("Explain the passage at 01:30")
    assert has_time_request("解释第十分钟附近的片段")
    assert not has_time_request("从 0 到 100 取中点，解释 O(1) amortized time")


def test_citation_context_keeps_immediate_selected_continuations_without_crossing_gaps_or_types():
    from lecturelens_agent.study.context import include_citation_neighbors

    evidence = [
        {"evidence_id": str(i), "source_type": "SUBTITLE", "start_ms": i * 1000, "end_ms": (i + 1) * 1000}
        for i in range(4)
    ] + [
        {"evidence_id": "distant", "source_type": "SUBTITLE", "start_ms": 20000, "end_ms": 21000},
        {"evidence_id": "visual", "source_type": "OCR", "start_ms": 2000, "end_ms": 3000},
    ]
    draft = {"evidence_ids": ["1"], "questions": [{"evidence_ids": ["1"]}, {"evidence_ids": ["visual"]}]}
    result = include_citation_neighbors(draft, evidence)
    assert result["questions"][0]["evidence_ids"] == ["1", "0", "2"]
    assert result["questions"][1]["evidence_ids"] == ["visual"]
    assert "3" not in result["questions"][0]["evidence_ids"]  # No recursive expansion.
    assert draft["evidence_ids"] == ["1"]


def test_review_quotes_keep_canonical_provenance_across_changed_decision_aliases():
    canonical = "evidence-" + "x" * 100
    review = {"grounds": {"explanation": [{"source": "e1", "quote": "literal e1 remains unchanged"}]}}
    stored = aliases_in(review, {"e1": canonical})
    assert stored["grounds"]["explanation"][0]["source"] == canonical
    assert review["grounds"]["explanation"][0]["source"] == "e1"
    from lecturelens_agent.study.quality import QualityReview

    QualityReview.model_validate({"issues": ["unsupported_explanation"], "feedback": "Fix claim", **stored})
    evidence = [
        {"evidence_id": "other", "text": "different", "start_ms": 0, "end_ms": 1},
        {"evidence_id": canonical, "text": "quoted text", "start_ms": 1, "end_ms": 2},
    ]
    history = [{"tool": "create_practice_set", "arguments": {}, "result": {"quality": stored}}]
    messages, _ = build_messages("system", "goal", evidence, history, [])
    quoted = json.loads(messages[-1]["content"])["quality"]["grounds"]["explanation"][0]
    assert quoted["source"] == "e2"
    assert quoted["quote"] == "literal e1 remains unchanged"
    assert stored["grounds"]["explanation"][0]["source"] == canonical


def test_rereading_window_refreshes_existing_ids_before_evicting_older_context():
    from lecturelens_agent.study.context import retain_evidence

    selected = [str(i) for i in range(8)]
    refreshed = retain_evidence(selected, ["0", "1", "8"])
    assert refreshed == ["3", "4", "5", "6", "7", "0", "1", "8"]
    assert selected == [str(i) for i in range(8)]
    assert retain_evidence(refreshed, []) == refreshed
    assert retain_evidence(selected, ["0", "1", "1", "8"]) == refreshed


def test_gap_completion_is_bounded_and_does_not_cross_modality_or_long_silence():
    from lecturelens_agent.study.context import evidence_gaps

    evidence = [
        {"evidence_id": str(i), "source_type": "SUBTITLE", "start_ms": i * 2000, "end_ms": i * 2000 + 1000}
        for i in range(5)
    ]
    assert len(evidence_gaps(evidence)) == 2
    assert evidence_gaps(evidence * 2) == []
    assert evidence_gaps([evidence[0], {**evidence[1], "source_type": "OCR"}]) == []
    assert evidence_gaps([evidence[0], {**evidence[1], "start_ms": 100000, "end_ms": 101000}]) == []


def test_latest_search_choice_survives_intermediate_observations_and_can_change():
    history = [
        {
            "tool": "search_course_evidence",
            "arguments": {"query": "method", "practice_kind": "interval_halving"},
            "result": {"practice_kind": "interval_halving"},
        },
        {"tool": "read_evidence_window", "arguments": {"evidence_id": "e1"}, "result": {}},
    ]
    messages, _ = build_messages("system", "goal", [], history, [])
    assert json.loads(messages[-1]["content"])["practice_kind"] == "interval_halving"
    history.append(
        {
            "tool": "search_course_evidence",
            "arguments": {"query": "new method", "practice_kind": "general"},
            "result": {"practice_kind": "general"},
        }
    )
    messages, _ = build_messages("system", "goal", [], history, [])
    assert json.loads(messages[-1]["content"])["practice_kind"] == "general"


def test_unfinished_speech_requests_a_bounded_tail_and_citations_follow_only_its_sentence():
    from lecturelens_agent.study.context import evidence_gaps, include_citation_neighbors

    def speech(key, text, start):
        return dict(evidence_id=key, text=text, start_ms=start, end_ms=start + 1000, source_type="SUBTITLE")

    hits = [speech("a", "Begin here.", 0), speech("b", "Concatenate all elements", 1000)]
    assert evidence_gaps(hits) == [(60000, "b", 2000, 62000, "SUBTITLE", "continuation")]
    evidence = hits + [
        speech("c", "starting at index one and", 2000),
        speech("d", "create another object.", 3000),
        speech("e", "Another unrelated sentence.", 4000),
    ]
    draft = dict(evidence_ids=["a"], questions=[dict(evidence_ids=["a"]), dict(evidence_ids=["b"])])
    cited = include_citation_neighbors(draft, evidence)
    assert set(cited["questions"][0]["evidence_ids"]) == {"a", "b", "c", "d"}
    assert "e" not in cited["questions"][1]["evidence_ids"]
    assert draft["questions"][0]["evidence_ids"] == ["a"]
    assert evidence_gaps([speech("a", "Finished.", 0)]) == []
    assert evidence_gaps([{**hits[-1], "source_type": "OCR"}]) == []


def test_evicted_observation_references_cannot_leak_as_current_citations():
    import copy

    from lecturelens_agent.study.context import visible_references

    value = {
        "evidence_ids": ["old", "current"],
        "course_coverage": {
            "evidence_ids": ["old"],
            "methods": {"m1": {"evidence_id": "current"}, "m2": {"evidence_id": "old"}},
        },
    }
    original = copy.deepcopy(value)
    projected = visible_references(value, {"current"})
    assert projected["evidence_ids"] == ["current"]
    assert projected["course_coverage"]["evidence_ids"] == []
    assert list(projected["course_coverage"]["methods"]) == ["m1"]
    assert value == original


def test_citation_completion_reads_only_bounded_contiguous_speech_and_preserves_sources():
    from lecturelens_agent.study.context import complete_citation_context, include_citation_neighbors

    draft = {
        "evidence_ids": ["definition"],
        "questions": [{"evidence_ids": ["definition"]}, {"evidence_ids": ["check"]}],
    }

    def source(key, text, start, end):
        return {"evidence_id": key, "text": text, "start_ms": start, "end_ms": end, "source_type": "SUBTITLE"}

    evidence = [
        source("definition", "The solution is on both lines.", 0, 1000),
        source("check", "We check the point and it", 10000, 20000),
    ]
    calls = []

    def read(anchor):
        calls.append(anchor)
        return [
            source("tail", "solves both equations: substitute x and y.", 20000, 30000),
            source("unrelated", "Another theorem.", 90000, 100000),
        ]

    completed, windows = complete_citation_context(draft, evidence, read)
    assert calls == windows == ["check"]
    assert {e["evidence_id"] for e in completed} == {"definition", "check", "tail"}
    assert include_citation_neighbors(draft, completed)["questions"][1]["evidence_ids"] == ["check", "tail"]
    full = evidence + [source(str(i), "Complete.", 110000 + i * 1000, 111000 + i * 1000) for i in range(6)]
    draft["evidence_ids"] = [e["evidence_id"] for e in full]
    calls.clear()
    assert len(complete_citation_context(draft, full, read)[0]) == 8
    assert not calls


def test_anchor_context_prioritizes_immediate_neighbors_without_eviction_or_scope_widening():
    from lecturelens_agent.study.context import adjacent_anchor_context

    def item(name, start, end, kind="SUBTITLE"):
        return {"evidence_id": name, "start_ms": start, "end_ms": end, "source_type": kind, "text": name}

    anchor = item("joint", 20000, 30000)
    existing = [anchor, *[item(str(i), i * 1000, (i + 1) * 1000) for i in range(5)]]
    before, after = item("before", 10000, 20000), item("after", 30000, 40000)
    window = [item("far", 50000, 60000), after, item("other-track", 10000, 20000, "VISION"), before, anchor]
    result = adjacent_anchor_context(existing, anchor, window, {})
    assert result == [*existing, before, after]
    assert adjacent_anchor_context(existing, anchor, window, {"start_ms": 21000, "end_ms": 35000}) == [
        *existing,
        after,
    ]
    assert adjacent_anchor_context(result, anchor, window, {}) == result
    assert len(existing) == 6


def test_course_order_preserves_source_identity_and_legacy_untimed_order():
    from lecturelens_agent.study.context import course_order

    late = {"evidence_id": "late", "start_ms": 20, "end_ms": 30}
    early = {"evidence_id": "early", "start_ms": 10, "end_ms": 20}
    ranked = [late, early]
    assert course_order(ranked) == [early, late]
    assert ranked == [late, early]
    untimed = [{"evidence_id": "z"}, {"evidence_id": "a"}]
    assert course_order(untimed) == untimed


def test_review_orders_passages_without_renumbering_canonical_aliases_or_borrowing_sources():
    from test_study_answer_points import draft

    from lecturelens_agent.study.contracts import materialize_practice
    from lecturelens_agent.study.quality import review_messages, review_wire_messages

    evidence = [
        {"evidence_id": "late", "text": "solves both equations.", "start_ms": 20, "end_ms": 30},
        {"evidence_id": "early", "text": "The point on both lines", "start_ms": 10, "end_ms": 20},
    ]
    coverage = review_messages(
        "check points",
        {"kind": "insufficient_evidence", "reason": ""},
        evidence,
        structured_support=True,
        observe_methods=True,
    )
    body = json.loads(coverage[-1]["content"])
    assert [(e["evidence_id"], e["text"]) for e in body["evidence"]] == [
        ("e2", "The point on both lines"),
        ("e1", "solves both equations."),
    ]
    data = draft()
    data["evidence_ids"] = ["late", "early"]
    data["questions"][0]["evidence_ids"] = ["late", "early"]
    data["questions"][1]["evidence_ids"] = ["late"]
    messages = review_messages(
        "check points",
        dict(materialize_practice(data), kind="practice"),
        evidence,
        structured_support=True,
        check_goal=True,
    )
    wire = json.loads(review_wire_messages(messages)[-1]["content"])
    assert [p["text"] for p in wire["passages"]] == ["The point on both lines", "solves both equations."]
    assert wire["fields"][2]["own_evidence"] == [{"evidence_id": "field2_source2", "text_ref": "p2"}]
