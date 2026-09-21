import copy
import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_goals import goal_verdict

from lecturelens_agent.study.linear import LinearPracticeArgs, linear_practice
from lecturelens_agent.study.quality import (
    review_contract,
    review_messages,
    review_wire_messages,
    verified_application,
)
from lecturelens_agent.study.store import RunStopped
from lecturelens_agent.study.support_review import MethodCoverageVerdict

base_setup = test_study.setup


@pytest.fixture
def setup(base_setup):
    # Mechanism fixtures need course text compatible with their linear drafts;
    # semantic quality still requires the separately recorded real evaluations.
    authority = base_setup[1]
    original = authority.read

    def read(scope, action="CHECK", **arguments):
        result = original(scope, action, **arguments)
        for item in result["evidence"]:
            item["text"] = "A solution lies on both lines. Substitute the point into both equations to check."
        return result

    authority.read = read
    return base_setup


def arguments():
    return {
        "method_id": "m1",
        "language": "zh",
        "concept": {"skill": "system_solution", "evidence_ids": ["e1"]},
        "evidence_ids": ["e1"],
        "application": {
            "equations": [{"a": 2, "b": -1, "rhs": 0}, {"a": 1, "b": 1, "rhs": 3}],
            "points": [{"x": 1, "y": 2, "expected": "all"}, {"x": 2, "y": 1, "expected": "not_all"}],
            "task": "verify",
            "evidence_ids": ["e1"],
        },
    }


@pytest.mark.parametrize("language", ["zh", "en"])
def test_complete_point_checks_preserve_all_equations_after_a_failure(language):
    args = arguments()
    args["language"] = language
    draft, proof = linear_practice(args)
    assert [[c["holds"] for c in point] for point in proof["checks"]] == [[True, True], [False, True]]
    assert len(draft["questions"][1]["answer_points"]) == 2
    second = draft["questions"][1]["answer_points"][1]
    assert "3 ≠ 0" in second and "3 = 3" in second
    assert "expected" not in draft["questions"][1]["question"]
    assert draft["questions"][1]["answer"] == draft["questions"][1]["rubric"]


def test_design_mismatch_returns_actual_observations_and_no_artifact():
    args = arguments()
    args["application"]["points"][1]["expected"] = "none"
    draft, observation = linear_practice(args)
    assert draft is None and observation["status"] == "constraint_mismatch"
    assert observation["constraints_met"] == [True, False]
    assert observation["checks"][1][1] == {"lhs": 3, "rhs": 3, "holds": True}
    args["application"]["points"][1]["y"] = 2
    draft, observation = linear_practice(args)
    assert draft and observation["constraints_met"] == [True, True]
    assert not any(c["holds"] for c in observation["checks"][1])


def test_negative_coordinates_and_wrong_claim_are_computed_without_new_theory():
    args = arguments()
    args["application"].update(
        equations=[{"a": 3, "b": -2, "rhs": 6}], points=[{"x": -2, "y": -6}], task="correct"
    )
    draft, proof = linear_practice(args)
    question = draft["questions"][1]
    assert "P1 不满足" in question["question"]
    assert proof["checks"] == [[{"lhs": 6, "rhs": 6, "holds": True}]]
    assert "6 = 6" in question["answer"]


@pytest.mark.parametrize(
    "defect", ["zero_equation", "float", "boolean", "large", "duplicate", "many", "code"]
)
def test_point_tool_rejects_unbounded_or_ambiguous_inputs(defect):
    args = arguments()
    if defect == "zero_equation":
        args["application"]["equations"][0].update(a=0, b=0)
    elif defect == "duplicate":
        args["application"]["points"][1] = args["application"]["points"][0]
    elif defect == "many":
        args["application"]["equations"] *= 2
    else:
        args["application"]["points"][0]["x"] = {
            "float": 1.5,
            "boolean": True,
            "large": 1000000,
            "code": "__import__('os')",
        }[defect]
    with pytest.raises(ValidationError):
        LinearPracticeArgs.model_validate(args)


def test_computed_proof_reconstructs_exact_question_and_constraints_instead_of_trusting_flags():
    draft, proof = linear_practice(arguments())
    candidate = dict(draft, kind="practice")
    assert verified_application(candidate, [proof])
    forged = copy.deepcopy(proof)
    forged["checks"][0][0]["holds"] = False
    assert verified_application(candidate, [forged])  # Recomputed inputs, not this untrusted flag.
    forged["problem"]["points"][0]["x"] = 3
    assert not verified_application(candidate, [forged])
    forged = copy.deepcopy(proof)
    forged["problem"]["points"][0]["expected"] = "none"
    assert not verified_application(candidate, [forged])
    candidate["questions"][1]["answer_points"][0] = "Wrong answer"
    assert not verified_application(candidate, [proof])


def test_scoped_computation_hides_only_verified_answer_and_still_requires_course_checks():
    draft, proof = linear_practice(arguments())
    evidence = [{"evidence_id": "e1", "text": "Substitute coordinates into both equations."}]
    method = {
        "operation": "Check a point",
        "input": "Point",
        "output": "Checks",
        "evidence_id": "e1",
        "quote": evidence[0]["text"],
    }
    messages = review_messages(
        "check two points",
        dict(draft, kind="practice"),
        evidence,
        example_checks=[proof],
        structured_support=True,
        application_method=method,
        check_goal=True,
    )
    body = json.loads(messages[-1]["content"])
    assert body["review_mode"] == "field_support_scoped_computed_goals_v1"
    wire = json.loads(review_wire_messages(messages)[-1]["content"])
    assert wire["fields"][2]["calculation_verified"]
    assert "answer_points" not in wire["fields"][2]
    assert wire["fields"][2]["verified_results"] == draft["questions"][1]["answer_points"]
    assert "selected_method" in wire["fields"][2]
    data = goal_verdict(body)
    data["application_method_check"] = data["checks"][2].pop("method_alignment")
    data["explanation_checks"][0]["supported"] = False
    verdict = review_contract(review_mode=body["review_mode"]).model_validate(data, context=body).review()
    assert "unsupported_explanation" in verdict.issues  # Correct arithmetic is not support.


@pytest.mark.parametrize("foreign_source", [False, True])
def test_runtime_constraint_observation_replays_and_repairs_with_owned_sources(setup, foreign_source):
    store, _, runtime, _ = setup
    observations, reviews = [], []

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "point", "practice_kind": "linear_points"},
            }
        args = arguments()
        args.pop("evidence_ids")
        args["concept"]["evidence_ids"] = ["e2"]
        if body.get("example_check"):
            observations.append(body["example_check"])
        else:
            args["application"]["points"][1]["expected"] = "none"
        if foreign_source:
            args["application"]["evidence_ids"] = ["foreign"]
        return {"name": "create_linear_practice", "arguments": args}

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        reviews.append(body)
        if body["review_mode"] == "course_methods_v1":
            data = {
                "course_fact": "An observed check",
                "support": "demonstrated_method",
                "missing_goal_quote": "",
                "evidence_ids": ["e1"],
                "methods": [
                    {"operation": "Check a point", "input": "Point", "output": "Checks", "evidence_id": "e1"}
                ],
            }
            result = MethodCoverageVerdict.model_validate(data, context=body).review()
        else:
            data = goal_verdict(body)
            data["application_method_check"] = data["checks"][2].pop("method_alignment")
            result = (
                review_contract(review_mode=body["review_mode"]).model_validate(data, context=body).review()
            )
        return {"review": result.model_dump()}

    runtime.provider.decide, runtime.provider.review = decide, review
    save = store.save_tool

    def crash_after_constraint_result(*args, **kwargs):
        result = save(*args, **kwargs)
        if result.get("example_check", {}).get("status") == "constraint_mismatch":
            raise RunStopped()
        return result

    store.save_tool = crash_after_constraint_result
    run = test_study.start(setup)
    runtime.execute(run)
    if foreign_source:
        result = test_study.read(setup)
        assert result["run"]["error_code"] == "UNSUPPORTED_CITATION" and result["artifact"] is None
        return
    assert test_study.read(setup)["run"]["model_calls"] == 3
    store.save_tool = save
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded" and result["run"]["model_calls"] == 5
    assert set(reviews[-1]["candidate"]["evidence_ids"]) == {"e1", "e2"}
    assert set(reviews[-1]["candidate"]["questions"][0]["evidence_ids"]) == {"e1", "e2"}
    assert len(reviews) == 2 and len(observations) == 1
    assert observations[0]["constraints_met"] == [True, False]
    assert "constraints_met" not in json.dumps(result, default=str)
    assert all("answer_points" not in q and "answer" not in q for q in result["artifact"]["questions"])
    assert len(test_study.read(setup, "ANSWERS")["questions"]) == 2


def test_linear_schema_binds_explanation_and_computed_question_separately():
    from lecturelens_agent.study.quality import review_schema

    schema = review_schema(
        "practice", "answer_points_v1", "field_support_scoped_computed_goals_v1", method_scope=True
    )["function"]["parameters"]
    for field, forbidden in [
        ("explanation", "unsupported_question"),
        ("question_1", "unsupported_explanation"),
        ("question_2", "unsupported_explanation"),
    ]:
        definition = schema["$defs"][schema["properties"][field]["$ref"].split("/")[-1]]
        assert forbidden not in definition["properties"]["issue"]["enum"]
    assert schema["properties"]["explanation"] != schema["properties"]["question_2"]


def test_linear_selection_derives_explanation_sources_instead_of_accepting_an_independent_list():
    from lecturelens_agent.study.linear import LinearSelectionArgs

    args = arguments()
    with pytest.raises(ValidationError):
        LinearSelectionArgs.model_validate(args)
    args.pop("evidence_ids")
    assert LinearSelectionArgs.model_validate(args).concept.evidence_ids == ["e1"]


def test_novel_literal_is_replayable_and_avoids_observed_suggestions():
    from lecturelens_agent.study.strings import novel_string_input

    first = novel_string_input("seed", [])
    assert first == novel_string_input("seed", [])
    next_literal = novel_string_input("seed", [{"text": first}])
    assert next_literal and next_literal != first


@pytest.mark.parametrize("retain_source", [True, False])
def test_window_reuses_only_method_observations_whose_sources_remain_selected(setup, retain_source):
    store, authority, runtime, _ = setup
    original_read = authority.read
    coverage_calls = []

    def read(scope, action="CHECK", **kwargs):
        if action == "WINDOW" and not retain_source:
            kwargs["evidence_ids"] = [f"e{i}" for i in range(2, 10)]
        return original_read(scope, action, **kwargs)

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "point", "practice_kind": "linear_points"},
            }
        if not any(h["tool"] == "read_evidence_window" for h in body["history"]):
            return {"name": "read_evidence_window", "arguments": {"evidence_id": "e2"}}
        args = arguments()
        args.pop("evidence_ids")
        return {"name": "create_linear_practice", "arguments": args}

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if body["review_mode"] == "course_methods_v1":
            coverage_calls.append(body)
            value = {
                "course_fact": "A demonstrated check",
                "support": "direct",
                "missing_goal_quote": "",
                "evidence_ids": ["e1"],
                "methods": [{"operation": "Check", "input": "Point", "output": "Truth", "evidence_id": "e1"}],
            }
            verdict = MethodCoverageVerdict.model_validate(value, context=body).review()
        else:
            value = goal_verdict(body)
            value["application_method_check"] = value["checks"][2].pop("method_alignment")
            verdict = (
                review_contract(review_mode=body["review_mode"]).model_validate(value, context=body).review()
            )
        return {"review": verdict.model_dump()}

    authority.read = read
    runtime.provider.decide, runtime.provider.review = decide, review
    run = test_study.start(setup)
    runtime.execute(run)
    state = test_study.read(setup)
    assert state["run"]["status"] == "succeeded"
    assert len(coverage_calls) == (1 if retain_source else 2)
    assert state["run"]["model_calls"] == (5 if retain_source else 6)
    with store.connect() as conn:
        result = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='read_evidence_window'",
            (run["run_id"],),
        ).fetchone()["result"]
    assert result.get("reused_method_observation", False) == retain_source


def test_review_schema_binds_field_sources_without_asking_model_to_retype_them():
    from lecturelens_agent.study.quality import review_schema

    draft, proof = linear_practice(arguments())
    request = review_messages(
        "check",
        dict(draft, kind="practice"),
        [{"evidence_id": "e1", "text": "Check by substitution."}],
        example_checks=[proof],
        structured_support=True,
        check_goal=True,
    )
    body = json.loads(request[-1]["content"])
    schema = review_schema("practice", "answer_points_v1", body["review_mode"], context=body)["function"][
        "parameters"
    ]
    for name in ["explanation", "question_1", "question_2"]:
        definition = schema["$defs"][schema["properties"][name]["$ref"].split("/")[-1]]
        assert "evidence_ids" not in definition["properties"]
    assert "evidence_ids" not in schema["$defs"]["ClaimCheck"]["properties"]


def test_linear_retrieval_keeps_topic_and_worked_operation_within_evidence_bound(setup):
    store, authority, runtime, scope = setup
    original = authority.read
    queries = []

    def read(run, action="CHECK", **kwargs):
        assert all(run[k] == scope[k] for k in ["owner_id", "course_id", "revision"])
        if action == "SEARCH":
            queries.append(kwargs["query"])
            kind = "operation" if len(queries) == 2 else "topic"
            kwargs["evidence_ids"] = [f"{kind}{i}" for i in range(8)]
        result = original(run, action, **kwargs)
        for i, item in enumerate(result["evidence"]):
            item.update(text=item["evidence_id"] + " teaching.", start_ms=i * 1000, end_ms=(i + 1) * 1000)
        return result

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "concept topic", "practice_kind": "linear_points"},
            }
        texts = [item["text"] for item in body["evidence"]]
        assert any("topic" in t for t in texts) and any("operation" in t for t in texts)
        assert len(texts) <= 8
        raise RunStopped()

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        assert "verifies GIVEN coordinates" in messages[0]["content"]
        value = {
            "course_fact": "Check",
            "support": "direct",
            "missing_goal_quote": "",
            "evidence_ids": ["e1"],
            "methods": [{"operation": "Check", "input": "Point", "output": "Truth", "evidence_id": "e1"}],
        }
        return {"review": MethodCoverageVerdict.model_validate(value, context=body).review().model_dump()}

    authority.read = read
    runtime.provider.decide, runtime.provider.review = decide, review
    run = test_study.start(setup)
    runtime.execute(run)
    assert len(queries) == 2 and queries[0] == "concept topic"
    with store.connect() as conn:
        result = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='search_course_evidence'",
            (run["run_id"],),
        ).fetchone()["result"]
    assert result["retrieval_queries"] == queries
    assert len(result["evidence_ids"]) <= 8


def test_explicit_point_construction_meets_conditions_and_retains_requested_seeds():
    args = arguments()
    args["application"].update(
        construct_points=True,
        points=[{"x": 0, "y": 0, "expected": "all"}, {"x": 0, "y": 0, "expected": "none"}],
    )
    draft, proof = linear_practice(args)
    assert draft and proof["constraints_met"] == [True, True]
    assert [p["x"] for p in proof["requested_problem"]["points"]] == [0, 0]
    actual = proof["problem"]["points"]
    assert (actual[0]["x"], actual[0]["y"]) != (actual[1]["x"], actual[1]["y"])
    assert all(c["holds"] for c in proof["checks"][0])
    assert not any(c["holds"] for c in proof["checks"][1])
    assert linear_practice(args) == (draft, proof)
    assert verified_application(dict(draft, kind="practice"), [proof])


def test_point_construction_is_bounded_and_does_not_change_exact_mode():
    args = arguments()
    args["application"].update(
        equations=[{"a": 2, "b": 2, "rhs": 1}],
        points=[{"x": 0, "y": 0, "expected": "all"}],
        construct_points=True,
    )
    draft, proof = linear_practice(args)
    assert draft is None and proof["status"] == "constraint_mismatch"
    args["application"]["construct_points"] = False
    draft, proof = linear_practice(args)
    assert draft is None and proof["problem"]["points"][0]["x"] == 0
    args["application"]["points"][0]["expected"] = "any"
    draft, proof = linear_practice(args)
    assert draft and proof["problem"]["points"][0]["x"] == 0
    assert not proof["checks"][0][0]["holds"]


def test_search_for_missing_concept_retains_the_observed_operation_source(setup):
    store, authority, runtime, scope = setup
    original = authority.read
    query_log = []

    def read(run, action="CHECK", **kwargs):
        if action == "SEARCH":
            query_log.append(kwargs["query"])
            prefix = "operation" if kwargs["query"].startswith("check point") else kwargs["query"]
            kwargs["evidence_ids"] = [prefix + str(i) for i in range(6)]
        result = original(run, action, **kwargs)
        for item in result["evidence"]:
            item["text"] = item["evidence_id"] + " demonstrates a check."
        return result

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        searches = sum(h["tool"] == "search_course_evidence" for h in body["history"])
        if searches < 2:
            return {
                "name": "search_course_evidence",
                "arguments": {
                    "query": "first" if searches == 0 else "second",
                    "practice_kind": "linear_points",
                },
            }
        assert len(body["evidence"]) <= 8
        assert any("first0" in e["text"] for e in body["evidence"])
        assert any("second0" in e["text"] for e in body["evidence"])
        raise RunStopped()

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        value = {
            "course_fact": "Check",
            "support": "direct",
            "missing_goal_quote": "",
            "evidence_ids": ["e1"],
            "methods": [{"operation": "Check", "input": "Point", "output": "Truth", "evidence_id": "e1"}],
        }
        return {"review": MethodCoverageVerdict.model_validate(value, context=body).review().model_dump()}

    authority.read = read
    runtime.provider.decide, runtime.provider.review = decide, review
    runtime.execute(test_study.start(setup))
    assert query_log == [
        "first",
        "check point coordinates substitute equation",
        "second",
        "check point coordinates substitute equation",
    ]


def test_subject_tools_and_novel_literal_keep_computation_inside_creation():
    from lecturelens_agent.study.context import build_messages
    from lecturelens_agent.study.provider import decision_schemas

    evidence = [{"evidence_id": "e1", "text": 's = "hello"', "start_ms": 0, "end_ms": 1}]
    history = [
        {"tool": "search_course_evidence", "arguments": {}, "result": {"practice_kind": "python_strings"}}
    ]
    messages, _ = build_messages("system", "new string output", evidence, history, [])
    body = json.loads(messages[-1]["content"])
    assert body["new_input_option"] not in evidence[0]["text"]
    assert body["goal"] == "new string output"
    names = {s["function"]["name"] for s in decision_schemas(messages)}
    assert "create_python_practice" in names and "check_python_example" not in names
    history[0]["result"] = {
        "practice_kind": "linear_points",
        "course_coverage": {"methods": {"m1": {"evidence_id": "e1"}}},
    }
    messages, _ = build_messages("system", "new points", evidence, history, [])
    schema = next(
        s["function"]["parameters"]
        for s in decision_schemas(messages)
        if s["function"]["name"] == "create_linear_practice"
    )
    assert "construct_points" in schema["$defs"]["PointProblem"]["required"]


@pytest.mark.parametrize("conflict", [False, True])
@pytest.mark.parametrize("revise_count", [False, True])
def test_pre_retrieval_learner_plan_recovers_and_binds_actual_task_and_outcomes(
    setup, conflict, revise_count
):
    store, _, runtime, _ = setup
    plan = {"task": "correct", "equation_count": 2, "point_outcomes": ["none"], "coordinate_mode": "new"}
    calls = []

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "point", "practice_kind": "linear_points", "linear_request": plan},
            }
        assert body["linear_request"] == {**plan, "intent_version": 2}
        args = arguments()
        args.pop("evidence_ids")
        args["application"].pop("task")
        args["application"]["points"] = [{"x": 1, "y": 2}]
        if revise_count:
            args["application"]["points"].append({"x": 2, "y": 3})
            args["request_revision"] = {
                "goal_quote": "两个候选点",
                "point_count": 2,
                "point_outcomes": ["none", "none"],
            }
        if conflict:
            args["application"]["task"] = "verify"
        return {"name": "create_linear_practice", "arguments": args}

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        calls.append(body)
        if body["review_mode"] == "course_methods_v1":
            value = {
                "course_fact": "Check",
                "support": "direct",
                "missing_goal_quote": "",
                "evidence_ids": ["e1"],
                "methods": [{"operation": "Check", "input": "Point", "output": "Truth", "evidence_id": "e1"}],
            }
            verdict = MethodCoverageVerdict.model_validate(value, context=body).review()
        else:
            value = goal_verdict(body)
            value["application_method_check"] = value["checks"][2].pop("method_alignment")
            verdict = (
                review_contract(review_mode=body["review_mode"]).model_validate(value, context=body).review()
            )
        return {"review": verdict.model_dump()}

    runtime.provider.decide, runtime.provider.review = decide, review
    save = store.save_tool

    def crash(*args, **kwargs):
        save(*args, **kwargs)
        raise RunStopped()

    store.save_tool = crash
    from lecturelens_agent.study.contracts import StudyCommand

    run = store.command(
        StudyCommand(
            **setup[3],
            operation="START",
            request_key="replay-plan",
            goal="给两个候选点检验" if revise_count else "给一个候选点检验",
        ),
        "mock",
    )
    run = next(row for row in store.candidates() if row["run_id"] == run["run"]["run_id"])
    runtime.execute(run)
    assert test_study.read(setup)["run"]["model_calls"] == 2
    store.save_tool = save
    runtime.execute(run)
    result = test_study.read(setup)
    if conflict:
        assert result["run"]["error_code"] == "LEARNER_PLAN_CONFLICT" and result["artifact"] is None
    else:
        assert result["run"]["status"] == "succeeded" and result["run"]["model_calls"] == 4
        with store.connect() as conn:
            entry = conn.execute(
                "SELECT arguments,result FROM study_tool_result WHERE run_id=%s AND tool_name='create_linear_practice'",
                (run["run_id"],),
            ).fetchone()
        assert set(entry["arguments"]["concept"]["evidence_ids"]) == {"e1", "e2"}
        assert entry["arguments"]["application"]["task"] == "correct"
        assert entry["arguments"]["application"]["construct_points"] is True
        proof = entry["result"]["example_check"]
        assert proof["constraints_met"] == ([True, True] if revise_count else [True])
        assert not any(c["holds"] for c in proof["checks"][0])
        if revise_count:
            assert entry["result"]["linear_request"]["point_count"] == 2
            with store.connect() as conn:
                original_plan = conn.execute(
                    "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='search_course_evidence'",
                    (run["run_id"],),
                ).fetchone()["result"]["linear_request"]
            assert original_plan["point_outcomes"] == ["none"]
        assert "同学声称" in result["artifact"]["questions"][1]["question"]


def test_budget_policy_reserves_review_and_plan_schema_omits_already_bound_decisions():
    from lecturelens_agent.study.context import build_messages
    from lecturelens_agent.study.provider import decision_schemas

    evidence = [{"evidence_id": "e1", "text": "A check", "start_ms": 0, "end_ms": 1}]
    plan = {"task": "correct", "equation_count": 2, "point_outcomes": ["none"], "coordinate_mode": "new"}
    history = [
        {
            "tool": "search_course_evidence",
            "arguments": {},
            "result": {
                "practice_kind": "linear_points",
                "linear_request": plan,
                "course_coverage": {"methods": {"m1": {"evidence_id": "e1"}}},
            },
        }
    ]
    messages, _ = build_messages(
        "system", "goal", evidence, history, [], {"model_calls_left_after_response": 2}
    )
    schemas = decision_schemas(messages)
    assert {s["function"]["name"] for s in schemas} == {
        "create_linear_practice",
        "report_insufficient_evidence",
    }
    schema = next(
        s["function"]["parameters"] for s in schemas if s["function"]["name"] == "create_linear_practice"
    )
    app = schema["$defs"]["PointProblem"]
    assert "task" not in app["properties"] and "construct_points" not in app["properties"]
    assert app["properties"]["points"]["minItems"] == 1
    assert app["properties"]["points"]["maxItems"] == 3
    assert schema["properties"]["request_revision"]["type"] == "object"
    assert app["properties"]["equations"]["minItems"] == app["properties"]["equations"]["maxItems"] == 2


def test_only_declared_linear_plan_json_transport_slot_is_decoded_and_logged():
    from lecturelens_agent.study.provider import ChatProvider, ModelResponseError

    provider = ChatProvider("http://127.0.0.1:1", "qwen3-max", "")
    plan = {
        "task": "correct",
        "equation_count": 2,
        "point_outcomes": ["none"],
        "point_count": 1,
        "coordinate_mode": "new",
    }

    def response(value):
        return {
            "calls": [
                {
                    "name": "search_course_evidence",
                    "arguments": {
                        "query": "point",
                        "practice_kind": "linear_points",
                        "linear_request": value,
                    },
                }
            ],
            "usage": {},
        }

    provider._request = lambda *args: response(json.dumps(plan))
    result = provider.decide([{"role": "user", "content": json.dumps({"goal": "new point"})}], 1)
    assert result["calls"][0]["arguments"]["linear_request"] == {**plan, "intent_version": 2}
    assert result["protocol_repairs"] == ["linear_request_json_object"]
    for bad in ["[1]", "{broken", json.dumps({**plan, "equation_count": 100}), None]:
        provider._request = lambda *args, bad=bad: response(bad)
        with pytest.raises(ModelResponseError):
            provider.decide([{"role": "user", "content": json.dumps({"goal": "new point"})}], 1)


def test_request_plan_has_one_outcome_for_each_point_and_legacy_records_remain_readable():
    from lecturelens_agent.study.linear import LinearRequest

    plan = {
        "task": "verify",
        "equation_count": 2,
        "point_count": 2,
        "point_outcomes": ["all"],
        "coordinate_mode": "new",
    }
    with pytest.raises(ValidationError):
        LinearRequest.model_validate(plan)
    plan["point_outcomes"].append("not_all")
    assert len(LinearRequest.model_validate(plan).point_outcomes) == 2
    plan.pop("point_count")
    assert len(LinearRequest.model_validate(plan).point_outcomes) == 2


def test_new_system_without_integer_solution_reports_repair_without_changing_it():
    args = arguments()
    args["application"].update(
        construct_points=True, equations=[{"a": 1, "b": -2, "rhs": -3}, {"a": 2, "b": 1, "rhs": 8}]
    )
    draft, observation = linear_practice(args)
    assert draft is None and observation["status"] == "constraint_mismatch"
    assert observation["requested_problem"]["equations"] == args["application"]["equations"]
    assert [eq["rhs"] for eq in observation["suggested_new_equations"]] == [-3, 4]
    args["application"]["equations"] = observation["suggested_new_equations"]
    draft, observation = linear_practice(args)
    assert draft and all(observation["constraints_met"])


def test_explicit_correction_request_constrains_initial_plan_choice():
    from lecturelens_agent.study.provider import decision_schemas

    for goal, expected in [
        ("给一道纠正常见误解的应用题。", ["correct"]),
        ("无需纠错，给判断题。", ["verify", "correct"]),
    ]:
        schemas = decision_schemas([{"role": "user", "content": json.dumps({"goal": goal})}])
        task = schemas[0]["function"]["parameters"]["properties"]["linear_request"]["properties"]["task"]
        assert task["enum"] == expected


def test_completed_citation_context_is_reviewed_and_replayed_without_rereading(setup):
    store, authority, runtime, _ = setup
    original_read = authority.read
    windows, reviews = [], []

    def read(scope, action="CHECK", **kwargs):
        if action == "WINDOW":
            windows.append(kwargs["evidence_id"])
            return {
                "evidence": [
                    {
                        "evidence_id": "tail",
                        "text": "the point by substituting into both equations.",
                        "start_ms": 1000,
                        "end_ms": 2000,
                        "source_type": "SUBTITLE",
                    }
                ]
            }
        result = original_read(scope, action, **kwargs)
        for item in result["evidence"]:
            if item["evidence_id"] == "e1":
                item.update(text="The solution lies on both lines. Check", start_ms=0, end_ms=1000)
            else:
                item.update(text="Another complete passage.", start_ms=10000, end_ms=11000)
        return result

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "point", "practice_kind": "linear_points"},
            }
        args = arguments()
        args.pop("evidence_ids")
        return {"name": "create_linear_practice", "arguments": args}

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if body["review_mode"] == "course_methods_v1":
            value = {
                "course_fact": "Check",
                "support": "direct",
                "missing_goal_quote": "",
                "evidence_ids": ["e1"],
                "methods": [{"operation": "Check", "input": "Point", "output": "Truth", "evidence_id": "e1"}],
            }
            verdict = MethodCoverageVerdict.model_validate(value, context=body).review()
        else:
            reviews.append(body)
            assert any("substituting" in e["text"] for e in body["evidence"])
            value = goal_verdict(body)
            value["application_method_check"] = value["checks"][2].pop("method_alignment")
            verdict = (
                review_contract(review_mode=body["review_mode"]).model_validate(value, context=body).review()
            )
        return {"review": verdict.model_dump()}

    authority.read = read
    runtime.provider.decide, runtime.provider.review = decide, review
    save = store.save_tool

    def crash(*args, **kwargs):
        result = save(*args, **kwargs)
        if args[3] == "create_linear_practice":
            raise RunStopped()
        return result

    store.save_tool = crash
    run = test_study.start(setup)
    runtime.execute(run)
    before = len(windows)
    store.save_tool = save
    runtime.execute(run)
    state = test_study.read(setup)
    assert state["run"]["status"] == "succeeded"
    assert len(reviews) == 1 and len(windows) == before
    assert "tail" in state["artifact"]["questions"][1]["evidence_ids"]
    with store.connect() as conn:
        result = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='create_linear_practice'",
            (run["run_id"],),
        ).fetchone()["result"]
    assert result["citation_context"]["windows"] == ["e1"]


def test_linear_ready_context_preserves_decisions_for_review_and_repair():
    from lecturelens_agent.study.provider import decision_schemas

    context = {
        "practice_kind": "linear_points",
        "course_coverage": {"can_answer": True, "methods": {"m1": {"evidence_id": "e1"}}},
    }
    messages = [
        {"role": "user", "content": json.dumps({"goal": "check points"})},
        {"role": "tool", "content": json.dumps(context)},
    ]

    def names():
        return {s["function"]["name"] for s in decision_schemas(messages)}

    assert "create_linear_practice" in names() and "read_evidence_window" not in names()
    context["quality"] = {"accepted": False, "issues": ["unsupported_explanation"]}
    messages[-1]["content"] = json.dumps(context)
    assert "read_evidence_window" in names()


def test_fixed_input_v2_observes_truth_without_using_model_hypotheses():
    from lecturelens_agent.study.linear import bind_linear_request, effective_linear_request

    plan = {
        "intent_version": 2,
        "task": "verify",
        "point_count": 3,
        "equation_count": 1,
        "point_outcomes": ["all"],
        "coordinate_mode": "specified",
    }
    args = arguments()
    args["application"]["equations"] = [{"a": 2, "b": -1, "rhs": 0}]
    args["application"]["points"] = [{"x": -2, "y": -4}, {"x": 0, "y": 0}, {"x": 1, "y": 1}]
    bound = bind_linear_request(args, plan)
    artifact, observed = linear_practice(bound)
    assert artifact and observed["checks"][-1] == [{"lhs": 1, "rhs": 0, "holds": False}]
    assert bound["application"]["points"][-1] == {"x": 1, "y": 1, "expected": "any"}
    assert effective_linear_request(plan)["point_outcomes"] == []
    assert plan["point_outcomes"] == ["all"]
    assert bind_linear_request(args, {**plan, "point_outcomes": []}) == bound
    with pytest.raises(ValidationError):
        bind_linear_request(args, {**plan, "intent_version": 1})
    with pytest.raises(ValidationError):
        bind_linear_request(args, {**plan, "coordinate_mode": "new"})


def test_legacy_fixed_input_constraints_remain_replayable():
    from lecturelens_agent.study.linear import bind_linear_request

    plan = {
        "task": "verify",
        "point_count": 2,
        "equation_count": 2,
        "point_outcomes": ["all", "none"],
        "coordinate_mode": "specified",
    }
    args = arguments()
    for point in args["application"]["points"]:
        point.pop("expected")
    artifact, observation = linear_practice(bind_linear_request(args, plan))
    assert artifact is None and observation["status"] == "constraint_mismatch"


def test_point_count_protocol_repair_explains_the_constraint_without_guessing_values():
    from lecturelens_agent.study.provider import ChatProvider, ModelResponseError

    provider = ChatProvider("http://127.0.0.1:1", "qwen3-max", "")
    provider._request = lambda *args: {
        "calls": [
            {
                "name": "search_course_evidence",
                "arguments": {
                    "query": "points",
                    "practice_kind": "linear_points",
                    "linear_request": {
                        "task": "verify",
                        "equation_count": 2,
                        "point_count": 2,
                        "point_outcomes": ["not_all"],
                        "coordinate_mode": "new",
                    },
                },
            }
        ],
        "usage": {"prompt_tokens": 100},
    }
    with pytest.raises(ModelResponseError) as caught:
        provider.decide([{"role": "user", "content": json.dumps({"goal": "two candidate points"})}], 1)
    assert caught.value.diagnostics["reason"] == "linear_point_outcomes_count"
    assert "one outcome per candidate" in caught.value.diagnostics["repair"]
    assert caught.value.usage["prompt_tokens"] == 100


def test_search_plan_schema_is_optional_standard_object_for_non_linear_tasks():
    from lecturelens_agent.study.contracts import tool_schemas

    schema = next(
        t["function"]["parameters"]
        for t in tool_schemas()
        if t["function"]["name"] == "search_course_evidence"
    )
    assert "linear_request" not in schema["required"]
    assert schema["properties"]["linear_request"]["type"] == "object"
    assert "point_count" in schema["properties"]["linear_request"]["required"]


def test_explicit_plan_revision_preserves_original_and_requires_verbatim_goal():
    from lecturelens_agent.study.linear import bind_linear_request, revised_linear_request

    goal = "Use two candidate points, exactly one satisfies both equations."
    plan = {
        "intent_version": 2,
        "task": "verify",
        "point_count": 1,
        "point_outcomes": ["any"],
        "equation_count": 2,
        "coordinate_mode": "new",
    }
    args = arguments()
    for point in args["application"]["points"]:
        point.pop("expected")
    with pytest.raises(ValueError):
        bind_linear_request(args, plan, goal)
    args["request_revision"] = {
        "goal_quote": "two candidate points, exactly one satisfies both equations",
        "point_count": 2,
        "point_outcomes": ["all", "not_all"],
    }
    revised = revised_linear_request(args, plan, goal)
    assert revised["point_count"] == 2 and plan["point_count"] == 1
    bound = bind_linear_request(args, plan, goal)
    artifact, proof = linear_practice(bound)
    assert artifact and proof["constraints_met"] == [True, True]
    args["request_revision"]["goal_quote"] = "invented request"
    with pytest.raises(ValueError):
        bind_linear_request(args, plan, goal)
