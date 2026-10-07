import json

import pytest
from pydantic import ValidationError
from test_study import read, setup, start  # noqa: F401 -- isolated PostgreSQL fixture

from lecturelens_agent.study.contracts import GrowthScaleArgs, StudyCommand
from lecturelens_agent.study.growth import compare_scales


def test_exact_hypothetical_scales_are_not_comparisons_or_timings():
    result = compare_scales([8, 16])
    assert result["status"] == "computed"
    assert result["rows"] == [
        {"input_size": 8, "linear_scale": 8, "log2_scale": 3, "halving_sizes": [8, 4, 2, 1]},
        {"input_size": 16, "linear_scale": 16, "log2_scale": 4, "halving_sizes": [16, 8, 4, 2, 1]},
    ]
    assert "not exact comparisons" in result["interpretation"]
    assert result == compare_scales([8, 16])
    assert result["class_substitution"] == {
        "input_relation": "n=2^k",
        "linear_class": "Theta(2^k)",
        "logarithmic_class": "Theta(k)",
    }


def test_mathematical_observation_survives_minimal_repair_only_with_visible_owned_sources():
    from lecturelens_agent.study.context import build_messages
    from lecturelens_agent.study.provider import decision_schemas

    evidence = [
        dict(
            evidence_id="owned",
            text="Linear work is Θ(n); halving work is Θ(log n).",
            start_ms=0,
            end_ms=1000,
        )
    ]
    computed = dict(
        tool="compare_growth_scales",
        arguments={},
        result=dict(example_check={**compare_scales([8]), "evidence_ids": ["owned"]}),
    )
    quality = dict(
        atomic_basis={"version": "atomic_basis_v2"}, atomic_assessments=[], issues=["unsupported_explanation"]
    )
    history = [computed, dict(tool="create_explanation", arguments={}, result=dict(quality=quality))]
    messages, _ = build_messages("Teach", "Explain the growth relationship.", evidence, history, [])
    body = json.loads(messages[-1]["content"])
    assert body["example_check"]["rows"][0]["log2_scale"] == 3
    field = next(t for t in decision_schemas(messages) if t["function"]["name"] == "create_explanation")[
        "function"
    ]["parameters"]["properties"]["explanation"]
    assert "BOTH sides" in field["description"]
    messages, _ = build_messages("Teach", "Explain the growth relationship.", [], history, [])
    assert "example_check" not in json.loads(messages[-1]["content"])


def test_direct_followup_computation_keeps_explanation_tools_without_repeat_search():
    from lecturelens_agent.study.context import build_messages
    from lecturelens_agent.study.provider import decision_schemas

    evidence = [
        dict(
            evidence_id="owned",
            text="Linear work is Θ(n); halving work is Θ(log n).",
            start_ms=0,
            end_ms=1000,
        )
    ]
    history = [
        dict(
            tool="compare_growth_scales",
            arguments=dict(input_sizes=[8], evidence_ids=["owned"]),
            result=dict(example_check={**compare_scales([8]), "evidence_ids": ["owned"]}),
        )
    ]
    messages, _ = build_messages(
        "Teach from Evidence.",
        "Give a simpler growth example.",
        evidence,
        history,
        [{"question": "Explain growth.", "explanation": "Linear versus logarithmic."}],
    )
    context = json.loads(messages[-1]["content"])
    assert context["output_kind"] == "explanation" and context["example_check"]["rows"][0]["log2_scale"] == 3
    names = {tool["function"]["name"] for tool in decision_schemas(messages)}
    assert "create_explanation" in names
    assert not names & {"create_practice_set", "create_python_practice", "create_interval_practice"}


def test_chosen_explanation_search_omits_exercise_plan_but_new_request_can_choose_it():
    from lecturelens_agent.study.provider import decision_schemas

    first = [{"role": "user", "content": json.dumps({"goal": "Explain a mathematical relationship."})}]
    original = decision_schemas(first)[0]["function"]["parameters"]
    assert "linear_request" in original["properties"]
    chosen = [
        *first,
        {"role": "tool", "content": json.dumps({"output_kind": "explanation", "practice_kind": "general"})},
    ]
    schemas = decision_schemas(chosen)
    narrowed = next(
        t["function"]["parameters"] for t in schemas if t["function"]["name"] == "search_course_evidence"
    )
    assert "linear_request" not in narrowed["properties"]
    assert narrowed["properties"]["output_kind"]["const"] == "explanation"
    assert len(json.dumps(narrowed)) < len(json.dumps(original)) / 2
    assert {t["function"]["name"] for t in schemas} >= {
        "read_evidence_window",
        "create_explanation",
        "report_insufficient_evidence",
    }
    exercises = [
        *first,
        {"role": "tool", "content": json.dumps({"output_kind": "practice", "practice_kind": "general"})},
    ]
    search = next(
        t["function"]["parameters"]
        for t in decision_schemas(exercises)
        if t["function"]["name"] == "search_course_evidence"
    )
    assert "linear_request" in search["properties"]


def test_growth_request_requires_observation_before_free_explanation_without_changing_other_flows():
    from lecturelens_agent.study.context import build_messages
    from lecturelens_agent.study.explanation_intent import growth_scales_needed
    from lecturelens_agent.study.provider import decision_schemas

    assert growth_scales_needed("Explain the exponential difference between Θ(n) and Θ(log n).")
    assert growth_scales_needed("Give a simpler example.", [{"explanation": "Linear n versus log n."}])
    assert not growth_scales_needed("Why does the recurrence give log n?")
    assert not growth_scales_needed("Explain the next teacher statement.")
    assert not growth_scales_needed("Explain the growth relationship between Θ(n²) and Θ(log n).")
    assert not growth_scales_needed("Give a simpler example.", [{"explanation": "Θ(n^2) versus Θ(log n)."}])
    evidence = [dict(evidence_id="owned", text="Linear n versus log n.", start_ms=0, end_ms=1000)]
    search = dict(
        tool="search_course_evidence",
        arguments=dict(query="growth", practice_kind="general", output_kind="explanation"),
        result=dict(output_kind="explanation", practice_kind="general"),
    )
    goal = "Explain the exponential difference between Θ(n) and Θ(log n)."
    messages, _ = build_messages("Teach", goal, evidence, [search], [])
    names = {t["function"]["name"] for t in decision_schemas(messages)}
    assert "compare_growth_scales" in names and "create_explanation" not in names
    assert not names & {"report_insufficient_evidence", "search_course_evidence", "read_evidence_window"}
    missing, _ = build_messages(
        "Teach", goal, [{**evidence[0], "text": "Unrelated course content."}], [search], []
    )
    assert "report_insufficient_evidence" in {t["function"]["name"] for t in decision_schemas(missing)}
    computed = dict(
        tool="compare_growth_scales",
        arguments=dict(input_sizes=[8], evidence_ids=["owned"]),
        result=dict(example_check=compare_scales([8])),
    )
    messages, _ = build_messages("Teach", goal, evidence, [search, computed], [])
    assert "create_explanation" in {t["function"]["name"] for t in decision_schemas(messages)}


@pytest.mark.parametrize(
    "goal",
    [
        "Compare the approaches described in the lesson.",
        "Explain what the second method does step by step.",
        "Explain the recurrence and its stopping condition.",
    ],
)
def test_ordinary_explanation_does_not_offer_unrequested_numerical_expansion(goal):
    from lecturelens_agent.study.provider import decision_schemas

    messages = [
        {"role": "user", "content": json.dumps({"goal": goal})},
        {"role": "tool", "content": json.dumps({"output_kind": "explanation", "practice_kind": "general"})},
    ]
    names = {s["function"]["name"] for s in decision_schemas(messages)}
    assert "create_explanation" in names
    assert "compare_growth_scales" not in names
    messages[0]["content"] = json.dumps(
        {"goal": "Explain the growth relationship between Θ(m) and Θ(log m)."}
    )
    assert "compare_growth_scales" in {s["function"]["name"] for s in decision_schemas(messages)}


def test_math_context_prefers_original_without_copying_translated_hit_identity():
    from lecturelens_agent.study.context import build_messages

    source = dict(
        evidence_id="original",
        text="Linear n versus log n. ORIGINAL_HIT",
        source_type="SUBTITLE",
        start_ms=0,
        end_ms=1000,
        match_start=23,
        match_end=35,
        match_hash="original-hash",
    )
    translated = dict(
        evidence_id="translation",
        text="线性 n 与 log n。翻译命中",
        source_type="SUBTITLE_TRANSLATION",
        start_ms=0,
        end_ms=1000,
        match_start=13,
        match_end=17,
        match_hash="translated-hash",
    )
    args = (
        "Teach",
        "Explain the growth relationship between Θ(m) and Θ(log m).",
        [translated, source],
        [],
        [],
    )
    messages, aliases = build_messages(*args)
    # First ordinary request still searches; inspect its observed context.
    history = [
        dict(
            tool="search_course_evidence",
            arguments={},
            result=dict(output_kind="explanation", practice_kind="general"),
        )
    ]
    messages, aliases = build_messages(*args[:3], history, [])
    body = json.loads(messages[-1]["content"])
    assert [e["text"] for e in body["evidence"]] == [source["text"]]
    assert list(aliases.values()) == ["original"]
    assert source["match_hash"] == "original-hash" and translated["match_hash"] == "translated-hash"
    messages, aliases = build_messages(
        "Teach", "Explain the course topic.", [translated, source], history, []
    )
    assert len(json.loads(messages[-1]["content"])["evidence"]) == 2
    history[0]["result"]["output_kind"] = "practice"
    messages, aliases = build_messages(
        "Teach", "Practice the course topic.", [translated, source], history, []
    )
    assert len(json.loads(messages[-1]["content"])["evidence"]) == 2


def test_procedural_followup_keeps_owned_translation_when_original_excerpt_is_incomplete():
    from lecturelens_agent.study.context import build_messages

    evidence = [
        dict(
            evidence_id="original",
            text="Compare neighbours and recur with half the input.",
            source_type="SUBTITLE",
            start_ms=0,
            end_ms=1000,
        ),
        dict(
            evidence_id="translation",
            text="比较邻居，递归到一半规模；单元素时返回元素。",
            source_type="SUBTITLE_TRANSLATION",
            start_ms=0,
            end_ms=1000,
        ),
    ]
    messages, aliases = build_messages(
        "Teach",
        "Describe the stopping input.",
        evidence,
        [],
        [{"kind": "explanation", "explanation": "Recursion reduces the input."}],
    )
    assert set(aliases.values()) == {"original", "translation"}
    assert "单元素" in messages[-1]["content"]


def test_explanation_clarification_keeps_fresh_read_window_without_losing_canonical_hit_data():
    from lecturelens_agent.study.context import build_messages

    sources = [
        dict(
            evidence_id=key,
            text=text,
            start_ms=start,
            end_ms=start + 1000,
            source_type=kind,
            match_start=0,
            match_end=len(text),
            match_hash=key + "-hit",
        )
        for key, text, start, kind in [
            ("original", "Compare neighbouring values.", 0, "SUBTITLE"),
            ("translated", "比较左右邻居。", 0, "SUBTITLE_TRANSLATION"),
            ("old", "An old benchmark.", 2000, "SUBTITLE"),
        ]
    ]
    previous = [dict(kind="explanation", explanation="Compare approaches.")]
    messages, aliases = build_messages("Teach", "Explain concrete steps.", sources, [], previous)
    assert set(aliases.values()) == {"original", "translated", "old"}
    history = [
        dict(
            tool="read_evidence_window",
            arguments=dict(evidence_id="translated"),
            result=dict(evidence_ids=["translated"], output_kind="explanation"),
        )
    ]
    messages, aliases = build_messages("Teach", "Explain concrete steps.", sources, history, previous)
    assert list(aliases.values()) == ["translated"]
    assert [e["text"] for e in json.loads(messages[-1]["content"])["evidence"]] == ["比较左右邻居。"]
    _, aliases = build_messages(
        "Teach", "Explain the growth relationship between Θ(m) and Θ(log m).", sources, history, previous
    )
    assert list(aliases.values()) == ["translated"]
    assert [s["match_hash"] for s in sources] == ["original-hit", "translated-hit", "old-hit"]
    history.append(
        dict(tool="create_explanation", arguments={}, result=dict(quality=dict(issues=["goal_mismatch"])))
    )
    _, aliases = build_messages("Teach", "Explain concrete steps.", sources, history, previous)
    assert list(aliases.values()) == ["translated"]
    history.append(
        dict(
            tool="search_course_evidence",
            arguments={},
            result=dict(output_kind="explanation", practice_kind="general"),
        )
    )
    _, aliases = build_messages("Teach", "Explain another topic.", sources, history, previous)
    assert set(aliases.values()) == {"original", "translated", "old"}
    assert [s["match_hash"] for s in sources] == ["original-hit", "translated-hit", "old-hit"]


def test_optional_read_reserves_full_source_review_and_one_repair():
    from lecturelens_agent.study.provider import decision_schemas

    first = {"role": "user", "content": json.dumps({"goal": "Explain the course comparison."})}
    body = {
        "output_kind": "explanation",
        "practice_kind": "general",
        "budget": {"reserved_bytes_and_output_left": 42000, "candidates_left": 2},
        "review_source_bytes": 0,
    }

    def names():
        return {
            t["function"]["name"]
            for t in decision_schemas([first, {"role": "tool", "content": json.dumps(body)}])
        }

    assert "read_evidence_window" in names()
    body["review_source_bytes"] = 12000
    assert "read_evidence_window" not in names()
    assert {"create_explanation", "report_insufficient_evidence"} <= names()


def test_repair_citation_contract_keeps_positive_sources_and_read_releases_it():
    from jsonschema import Draft202012Validator

    from lecturelens_agent.study.context import repair_observation
    from lecturelens_agent.study.provider import decision_schemas

    quality = repair_observation(
        {
            "atomic_basis": {"version": "atomic_basis_v2"},
            "goal_assessments": [{"matches": True}],
            "atomic_assessments": [
                {
                    "id": "a1",
                    "supported": True,
                    "model_supported": True,
                    "evidence_ids": ["e1"],
                    "strengthening_guards": [],
                },
                {
                    "id": "a2",
                    "supported": False,
                    "model_supported": False,
                    "evidence_ids": ["e2"],
                    "strengthening_guards": [],
                },
                {
                    "id": "a3",
                    "supported": False,
                    "model_supported": True,
                    "evidence_ids": ["e3"],
                    "strengthening_guards": ["universal_scope"],
                },
            ],
        }
    )
    assert quality["verified_source_ids"] == ["e1"]
    first = {"role": "user", "content": json.dumps({"goal": "Explain the course comparison."})}
    body = {
        "output_kind": "explanation",
        "practice_kind": "general",
        "quality": quality,
        "evidence": [{"evidence_id": "e1", "text": "Constant work and half-size recursion."}],
    }
    schemas = decision_schemas([first, {"role": "tool", "content": json.dumps(body)}])
    fields = next(
        t["function"]["parameters"]["properties"]
        for t in schemas
        if t["function"]["name"] == "create_explanation"
    )
    Draft202012Validator(fields["evidence_ids"]).validate(["e1"])
    assert list(Draft202012Validator(fields["evidence_ids"]).iter_errors(["e2"]))
    assert list(Draft202012Validator(fields["explanation"]).iter_errors("Check every element."))
    body.pop("quality")
    schemas = decision_schemas([first, {"role": "tool", "content": json.dumps(body)}])
    field = next(
        t["function"]["parameters"]["properties"]["evidence_ids"]
        for t in schemas
        if t["function"]["name"] == "create_explanation"
    )
    assert "allOf" not in field


def test_repair_wire_highlights_rejected_specialization_and_new_read_releases_it():
    from jsonschema import Draft202012Validator

    from lecturelens_agent.study.provider import decision_schemas

    first = {"role": "user", "content": json.dumps({"goal": "Explain concrete steps."})}
    context = {
        "output_kind": "explanation",
        "practice_kind": "general",
        "quality": {
            "atomic_assessments": [{"supported": False, "strengthening_guards": ["position_specialization"]}]
        },
    }
    schemas = decision_schemas([first, {"role": "tool", "content": json.dumps(context)}])
    field = next(
        t["function"]["parameters"]["properties"]["explanation"]
        for t in schemas
        if t["function"]["name"] == "create_explanation"
    )
    assert list(Draft202012Validator(field).iter_errors("Compare the middle element with its neighbour."))
    Draft202012Validator(field).validate("Compare the chosen element with its left and right neighbours.")
    reread = decision_schemas(
        [
            first,
            {
                "role": "tool",
                "content": json.dumps({"output_kind": "explanation", "practice_kind": "general"}),
            },
        ]
    )
    field = next(
        t["function"]["parameters"]["properties"]["explanation"]
        for t in reread
        if t["function"]["name"] == "create_explanation"
    )
    assert "allOf" not in field


def test_procedural_repair_contract_preserves_operands_while_removing_unsupported_position():
    from jsonschema import Draft202012Validator

    from lecturelens_agent.study.provider import decision_schemas

    messages = [
        {"role": "user", "content": json.dumps({"goal": "Explain concrete steps."})},
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "output_kind": "explanation",
                    "practice_kind": "general",
                    "evidence": [{"text": "Compare the left and right neighbours and halve the input."}],
                    "quality": {
                        "atomic_assessments": [
                            {"supported": False, "strengthening_guards": ["position_specialization"]}
                        ]
                    },
                }
            ),
        },
    ]
    field = next(
        t["function"]["parameters"]["properties"]["explanation"]
        for t in decision_schemas(messages)
        if t["function"]["name"] == "create_explanation"
    )
    validator = Draft202012Validator(field)
    assert list(validator.iter_errors("Perform constant comparisons and halve the input."))
    assert list(validator.iter_errors("Compare the middle element with its neighbours."))
    validator.validate("Compare the selected element with left and right neighbours, then halve the input.")


def test_first_draft_schema_exposes_only_negative_specialization_constraints_from_current_sources():
    from jsonschema import Draft202012Validator

    from lecturelens_agent.study.provider import decision_schemas

    messages = [
        {"role": "user", "content": json.dumps({"goal": "Explain concrete steps."})},
        {
            "role": "tool",
            "content": json.dumps(
                {
                    "output_kind": "explanation",
                    "practice_kind": "general",
                    "evidence": [{"text": "Compare neighbouring values and recur on one half-size problem."}],
                }
            ),
        },
    ]

    def field():
        return next(
            t["function"]["parameters"]["properties"]["explanation"]
            for t in decision_schemas(messages)
            if t["function"]["name"] == "create_explanation"
        )

    validator = Draft202012Validator(field())
    assert list(
        validator.iter_errors(
            "Compare the middle element with neighbours; recursively solve both subproblems and merge their solutions."
        )
    )
    validator.validate("Compare neighbouring values and recur on one half-size problem.")
    messages[-1]["content"] = json.dumps(
        {
            "output_kind": "explanation",
            "practice_kind": "general",
            "evidence": [
                {
                    "text": "Compare the middle element with neighbouring values, recursively solve both subproblems and merge their solutions."
                }
            ],
        }
    )
    Draft202012Validator(field()).validate(
        "Compare the middle element with neighbours; recursively solve both subproblems and merge their solutions."
    )


def test_detailed_followup_observes_taught_actions_before_drafting_and_preserves_goal_constraints():
    from jsonschema import Draft202012Validator

    from lecturelens_agent.study.provider import decision_schemas

    question = "How does the second method work in concrete steps?"
    body = {
        "goal": question,
        "semantic_context": {
            "previous_turns": [
                {"kind": "explanation", "explanation": "One method scans; the other halves its input."}
            ]
        },
        "evidence": [
            {"evidence_id": "e1", "text": "Compare the left and right neighbours and halve the input."}
        ],
    }
    schemas = decision_schemas([{"role": "user", "content": json.dumps(body)}])
    assert "create_explanation" not in {t["function"]["name"] for t in schemas}
    fields = next(
        t["function"]["parameters"]["properties"]
        for t in schemas
        if t["function"]["name"] == "read_evidence_window"
    )
    assert list(Draft202012Validator(fields["resolved_goal"]).iter_errors(question))
    Draft202012Validator(fields["resolved_goal"]).validate(
        "Describe the halving method and its neighbour comparisons."
    )
    assert {t["function"]["name"] for t in schemas} == {"read_evidence_window"}
    # A new exercise request still selects its original search/practice flow.
    exercise = {**body, "goal": "Create practice for the previous method with concrete steps."}
    search = next(
        t
        for t in decision_schemas([{"role": "user", "content": json.dumps(exercise)}])
        if t["function"]["name"] == "search_course_evidence"
    )
    assert "practice" in search["function"]["parameters"]["properties"]["output_kind"]["enum"]
    context = {
        "output_kind": "explanation",
        "history": [{"tool": "read_evidence_window"}],
        "evidence": body["evidence"],
    }
    observed = decision_schemas(
        [{"role": "user", "content": json.dumps(body)}, {"role": "tool", "content": json.dumps(context)}]
    )
    assert "search_course_evidence" in {t["function"]["name"] for t in observed}
    answer = next(
        t["function"]["parameters"]["properties"]["explanation"]
        for t in observed
        if t["function"]["name"] == "create_explanation"
    )
    assert list(Draft202012Validator(answer).iter_errors("Compare the middle element with neighbours."))
    assert list(Draft202012Validator(answer).iter_errors("Perform constant comparisons."))
    Draft202012Validator(answer).validate("Compare the left and right neighbours and halve the input.")


def test_direct_read_does_not_offer_refusal_before_runtime_search_fence_is_met():
    from lecturelens_agent.study.provider import decision_schemas

    first = {
        "role": "user",
        "content": json.dumps(
            {
                "goal": "Explain the previous method.",
                "semantic_context": {"previous_turns": [{"kind": "explanation"}]},
            }
        ),
    }
    context = {
        "output_kind": "explanation",
        "history": [{"tool": "read_evidence_window"}],
        "evidence": [{"text": "Compare neighbours."}],
    }
    messages = [first, {"role": "tool", "content": json.dumps(context)}]
    assert "report_insufficient_evidence" not in {t["function"]["name"] for t in decision_schemas(messages)}
    context["history"].append({"tool": "search_course_evidence"})
    messages[-1]["content"] = json.dumps(context)
    assert "report_insufficient_evidence" in {t["function"]["name"] for t in decision_schemas(messages)}


@pytest.mark.parametrize("sizes", [[], [True], [1.0], [3], [0], [-2], [2**21], [8, 8], [1, 2, 4, 8, 16]])
def test_unsupported_sizes_never_receive_computed_status(sizes):
    assert compare_scales(sizes)["status"] == "unsupported"


@pytest.mark.parametrize("sizes", [[], [True], [1.0], [0], [2**21], [8, 8], [1, 2, 4, 8, 16]])
def test_tool_contract_bounds_before_runtime(sizes):
    with pytest.raises(ValidationError):
        GrowthScaleArgs(input_sizes=sizes, evidence_ids=["owned"])


def test_boundary_size_has_twenty_finite_halving_steps():
    row = compare_scales([2**20])["rows"][0]
    assert row["log2_scale"] == 20 and len(row["halving_sizes"]) == 21
    assert row["halving_sizes"][-1] == 1


@pytest.mark.parametrize("crash", [False, True])
def test_authorized_computation_observation_and_checkpoint_recovery(setup, crash):  # noqa: F811
    store, authority, runtime, scope = setup
    original_read = authority.read

    def sources(scope, action="CHECK", **arguments):
        result = original_read(scope, action, **arguments)
        for item in result["evidence"]:
            item["text"] = (
                "The input is halved at each step until size one. Linear work is Θ(n); halving levels are Θ(log n)."
            )
        return result

    authority.read = sources

    def decide(messages, timeout):
        tools = [m for m in messages if m["role"] == "tool"]
        if not tools:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "growth", "practice_kind": "general", "output_kind": "explanation"},
            }
        if len(tools) == 1:
            return {
                "name": "compare_growth_scales",
                "arguments": {"input_sizes": [8, 16], "evidence_ids": ["e1"]},
            }
        example = json.loads(tools[-1]["content"])["example_check"]
        assert example["rows"][0]["halving_sizes"] == [8, 4, 2, 1]
        return {
            "name": "create_explanation",
            "arguments": {
                "title": "Scales",
                "explanation": "For a hypothetical size of eight, halving reaches one in three levels.",
                "evidence_ids": ["e1"],
            },
        }

    reviews = []
    original_review = runtime.provider.review

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        reviews.append(body)
        assert body["example_checks"][0]["semantics"] == "growth_scales_v1"
        return original_review(messages, timeout)

    runtime.provider.decide, runtime.provider.review = decide, review
    response = store.command(
        StudyCommand(
            **scope, operation="START", request_key="scales", goal="Explain hypothetical workload scales."
        ),
        "mock",
    )
    run = next(r for r in store.candidates() if r["run_id"] == response["run"]["run_id"])
    save = store.save_tool
    if crash:

        def save_crash(*args, **kwargs):
            value = save(*args, **kwargs)
            if args[3] == "compare_growth_scales":
                store.save_tool = save
                raise SystemExit("after durable calculation")
            return value

        store.save_tool = save_crash
        with pytest.raises(SystemExit):
            runtime.execute(run)
    runtime.execute(run)
    result = read(setup)
    assert result["run"]["status"] == "succeeded" and result["run"]["model_calls"] == 4
    assert len(reviews) == 1
    with store.connect() as conn:
        assert (
            conn.execute(
                "SELECT count(*) FROM study_tool_result WHERE run_id=%s AND tool_name='compare_growth_scales'",
                (run["run_id"],),
            ).fetchone()["count"]
            == 1
        )


def test_computation_cannot_read_an_unselected_foreign_evidence_id(setup):  # noqa: F811
    _, _, runtime, _ = setup
    original_decide = runtime.provider.decide

    def decide(messages, timeout):
        if any(m["role"] == "tool" for m in messages):
            return {
                "name": "compare_growth_scales",
                "arguments": {"input_sizes": [8], "evidence_ids": ["foreign"]},
            }
        result = original_decide(messages, timeout)
        result["arguments"]["output_kind"] = "explanation"
        return result

    runtime.provider.decide = decide
    runtime.execute(start(setup))
    result = read(setup)
    assert result["run"]["error_code"] == "UNSUPPORTED_CITATION" and result["artifact"] is None
