import copy
import json

import pytest
import test_study
from pydantic import ValidationError
from test_study_method_scope import observation
from test_study_support_review import accepted, messages

from lecturelens_agent.study.goals import explanation_claims, goal_constraints, refusal_text
from lecturelens_agent.study.quality import review_contract, review_schema, review_wire_messages
from lecturelens_agent.study.support_review import GoalFieldSupportVerdict, MethodCoverageVerdict, field_view

setup = test_study.setup


def goal_body():
    body = json.loads(messages()[-1]["content"])
    body.update(review_mode="field_support_goals_v1", goal="给两个候选点。只有一个同时满足两个方程。")
    return body


def goal_verdict(body):
    return {
        **accepted(body),
        "explanation_checks": [
            {
                "id": c["id"],
                "course_fact": field_view(body)["fields"][0]["own_evidence"][0]["text"][:120],
                "evidence_ids": [field_view(body)["fields"][0]["own_evidence"][0]["evidence_id"]],
                "supported": True,
            }
            for c in explanation_claims(field_view(body)["fields"][0]["text"])
        ],
        "goal_checks": [
            {"id": c["id"], "observation": "Observed quantities satisfy this clause", "matches": True}
            for c in goal_constraints(body["goal"])
        ],
    }


def test_goal_clauses_preserve_all_text_and_bound_addresses():
    for goal in ["甲。乙；丙\n丁;戊。己。庚。辛。", "  a\nb\n ", "no punctuation", ";\n;"]:
        clauses = goal_constraints(goal)
        assert "".join(c["text"] for c in clauses) == goal
        assert len(clauses) <= 6


@pytest.mark.parametrize("defect", ["missing", "duplicate", "invented"])
def test_cannot_accept_when_goal_clause_is_missing_or_replaced(defect):
    body = goal_body()
    data = goal_verdict(body)
    if defect == "missing":
        data["goal_checks"].pop()
    elif defect == "duplicate":
        data["goal_checks"][1] = data["goal_checks"][0]
    else:
        data["goal_checks"][1]["id"] = "g6"
    with pytest.raises(ValidationError):
        GoalFieldSupportVerdict.model_validate(data, context=body)


def test_correct_answer_and_field_support_cannot_override_unmet_goal():
    body = goal_body()
    data = goal_verdict(body)
    data["goal_checks"][1].update(observation="Both supplied points satisfy both equations", matches=False)
    result = GoalFieldSupportVerdict.model_validate(data, context=body).review()
    assert result.issues == ["goal_mismatch"]
    assert body["goal"].split("。")[1] in result.feedback
    assert result.goal_assessments[1].observation == "Both supplied points satisfy both equations"
    assert all(answer.matches_reference for answer in result.answer_observations)


def test_wrong_answer_is_derived_from_comparison_without_a_second_conflicting_label():
    body = goal_body()
    data = goal_verdict(body)
    data["checks"][1]["answer_check"].update(matches=False, answer="The actual course-based answer")
    result = GoalFieldSupportVerdict.model_validate(data, context=body).review()
    assert result.issues == ["incorrect_answer"]
    assert "actual course-based answer" in result.feedback
    data["checks"][1]["answer_check"]["matches"] = True
    data["checks"][1].update(issue="incorrect_answer", correction="A contradictory label")
    with pytest.raises(ValidationError):
        GoalFieldSupportVerdict.model_validate(data, context=body)


def test_early_goal_rejection_may_stop_solving_but_cannot_publish_unchecked_answers():
    body = goal_body()
    data = goal_verdict(body)
    data["checks"][2]["answer_check"] = None
    with pytest.raises(ValidationError):
        GoalFieldSupportVerdict.model_validate(data, context=body)
    data["goal_checks"][1].update(matches=False, observation="Only one candidate point supplied")
    result = GoalFieldSupportVerdict.model_validate(data, context=body).review()
    assert result.issues == ["goal_mismatch"]
    assert len(result.answer_observations) == 1


def test_shared_passage_text_does_not_share_field_citation_permissions():
    body = goal_body()
    body["candidate"]["questions"][1]["evidence_ids"] = ["e1"]
    wire = json.loads(review_wire_messages([{"role": "user", "content": json.dumps(body)}])[-1]["content"])
    fields = wire["fields"]
    assert fields[0]["own_evidence"][0]["text_ref"] == fields[2]["own_evidence"][0]["text_ref"]
    assert fields[0]["own_evidence"][0]["evidence_id"] != fields[2]["own_evidence"][0]["evidence_id"]
    assert len(wire["passages"]) == 1
    assert wire["passages"][0]["text"] == body["evidence"][0]["text"]
    data = goal_verdict(body)
    data["checks"][2]["evidence_ids"] = data["checks"][0]["evidence_ids"]
    with pytest.raises(ValidationError):
        GoalFieldSupportVerdict.model_validate(data, context=body)

    data["checks"][2]["evidence_ids"] = ["p1"]
    with pytest.raises(ValidationError):
        GoalFieldSupportVerdict.model_validate(data, context=body)


def test_explanation_sentences_cannot_hide_one_unsupported_claim_behind_other_facts():
    body = goal_body()
    body["candidate"]["explanation"] = "默认返回 None。任意方程组恰好一个解。"
    data = goal_verdict(body)
    assert len(data["explanation_checks"]) == 2
    data["explanation_checks"][1].update(course_fact="只讲了默认返回值", supported=False)
    result = GoalFieldSupportVerdict.model_validate(data, context=body).review()
    assert result.issues == ["unsupported_explanation"]
    assert "任意方程组恰好一个解" in result.feedback
    assert result.explanation_assessments[1].evidence_ids == ["e1"]
    for checks in [data["explanation_checks"][:1], [data["explanation_checks"][0]] * 2]:
        with pytest.raises(ValidationError):
            GoalFieldSupportVerdict.model_validate({**data, "explanation_checks": checks}, context=body)
    data["explanation_checks"][1]["evidence_ids"] = ["field1_source1"]
    with pytest.raises(ValidationError):
        GoalFieldSupportVerdict.model_validate(data, context=body)


def test_scoped_goal_wire_requires_both_independent_checks_and_keeps_sources_scoped():
    body = goal_body()
    body.update(review_mode="field_support_scoped_goals_v1", application_method=observation())
    original = copy.deepcopy(body)
    wire = json.loads(review_wire_messages([{"role": "user", "content": json.dumps(body)}])[-1]["content"])
    assert wire["goal_constraints"] == goal_constraints(body["goal"])
    assert "evidence" not in wire and "candidate" not in wire
    data = goal_verdict(body)
    data["application_method_check"] = data["checks"][2].pop("method_alignment")
    contract = review_contract(review_mode=body["review_mode"])
    assert contract.model_validate(data, context=body).review().issues == []
    schema = review_schema(review_mode=body["review_mode"])["function"]["parameters"]
    assert {"goal_checks", "application_method_check"} <= set(schema["required"])
    assert "checks" not in schema["properties"]
    assert "answer_check" not in schema["$defs"]["GoalExplanationReview"]["properties"]
    assert "answer_check" in schema["$defs"]["GoalQuestionReview"]["required"]
    named = copy.deepcopy(data)
    for check in named.pop("checks"):
        name = check.pop("field")
        if name == "explanation":
            check.pop("answer_check")
        named[name] = check
    result = contract.model_validate(named, context=body).review()
    assert result.issues == [] and result.method_assessment.matches
    assert body == original


def test_related_methods_survive_absent_coverage_without_overriding_it():
    body = {
        "review_mode": "course_methods_v1",
        "goal": "Explain least squares",
        "evidence": [{"evidence_id": "e1", "text": "Substitute the point and check both equations."}],
    }
    result = MethodCoverageVerdict.model_validate(
        {
            "course_fact": "Point checking",
            "evidence_ids": ["e1"],
            "support": "absent",
            "missing_goal_quote": "least squares",
            "methods": [
                {
                    "operation": "Substitute a point",
                    "input": "Point and equations",
                    "output": "Checks",
                    "evidence_id": "e1",
                }
            ],
        },
        context=body,
    ).review()
    assert result.issues == []  # Still supports abstention, not the requested missing topic.
    assert result.method_observations[0].quote == body["evidence"][0]["text"]


def test_refusal_keeps_model_teaching_private_and_replays_without_calls(setup):
    store, _, runtime, _ = setup
    reason = "平行无解，重合无穷多解；MODEL_TEXT_MUST_STAY_PRIVATE"
    original = runtime.provider.decide

    def decide(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return original(messages, timeout)
        return {"name": "report_insufficient_evidence", "arguments": {"reason": reason}}

    runtime.provider.decide = decide
    runtime.provider.review = lambda messages, timeout: {"review": {"issues": [], "feedback": "OK"}}
    run = test_study.start(setup)
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["artifact"]["explanation"] == refusal_text(run["goal"])
    assert reason not in json.dumps(result, ensure_ascii=False, default=str)
    assert reason not in json.dumps(test_study.read(setup, "EVENTS"), ensure_ascii=False, default=str)
    with store.connect() as conn:
        row = conn.execute(
            "SELECT arguments FROM study_tool_result WHERE run_id=%s AND tool_name=%s",
            (run["run_id"], "report_insufficient_evidence"),
        ).fetchone()
    assert row["arguments"]["reason"] == reason
    runtime.provider.decide = lambda *_: pytest.fail("Completed recovery must not call the model")
    runtime.provider.review = runtime.provider.decide
    runtime.execute(run)
    assert test_study.read(setup)["artifact"] == result["artifact"]


def test_goal_failure_is_replayed_into_repair_with_original_budget(setup):
    from lecturelens_agent.study.store import RunStopped

    store, _, runtime, _ = setup
    decide, save = runtime.provider.decide, store.save_tool
    reviews, observations = [], []

    def choose(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if body.get("quality"):
            observations.append(body["quality"])
        candidate = decide(messages, timeout)
        if observations:
            candidate["arguments"]["title"] = "Goal-corrected draft"
        return candidate

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        reviews.append(body)
        data = goal_verdict(body)
        if len(reviews) == 1:
            data["goal_checks"][0].update(matches=False, observation="A requested condition is missing")
        return {"review": GoalFieldSupportVerdict.model_validate(data, context=body).review().model_dump()}

    def interrupt_after_commit(*args, **kwargs):
        result = save(*args, **kwargs)
        if "quality" in result:
            raise RunStopped()
        return result

    runtime.provider.decide, runtime.provider.review = choose, review
    store.save_tool = interrupt_after_commit
    run = test_study.start(setup)
    runtime.execute(run)
    assert test_study.read(setup)["artifact"] is None
    assert test_study.read(setup)["run"]["model_calls"] == 4
    store.save_tool = save
    runtime.execute(run)
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded"
    assert result["run"]["model_calls"] == 6 and len(reviews) == 2
    assert observations[0]["goal_assessments"][0]["matches"] is False
    assert observations[0]["issues"] == ["goal_mismatch"]
    assert "goal_assessments" not in json.dumps(result, default=str)


def test_pre_draft_protocol_retry_is_charged_and_preserves_observed_sources(setup):
    from test_study_answer_points import draft

    from lecturelens_agent.study.store import StudyError

    _, _, runtime, _ = setup
    calls = []

    def choose(messages, timeout):
        body = json.loads(messages[-1]["content"])
        if not body["evidence"]:
            return {
                "name": "search_course_evidence",
                "arguments": {"query": "stop", "practice_kind": "general"},
            }
        value = draft()
        for field in [value, *value["questions"]]:
            field["evidence_ids"] = ["e1"]
        return {
            "name": "create_practice_set",
            "arguments": {
                **{k: value[k] for k in ("title", "explanation", "evidence_ids")},
                "concept": value["questions"][0],
                "application": value["questions"][1],
                "method_id": "m1",
            },
        }

    def review(messages, timeout):
        body = json.loads(messages[-1]["content"])
        calls.append(body)
        if len(calls) == 1:
            raise StudyError("MODEL_REVIEW_CONTRACT")
        if body["review_mode"] == "course_methods_v1":
            assert body["protocol_feedback"]["error"] == "MODEL_REVIEW_CONTRACT"
            data = {
                "course_fact": "Stopping",
                "support": "direct",
                "missing_goal_quote": "",
                "evidence_ids": ["e1"],
                "methods": [
                    {
                        "operation": "Check stopping",
                        "input": "Algorithm",
                        "output": "Stops or not",
                        "evidence_id": "e1",
                    }
                ],
            }
            result = MethodCoverageVerdict.model_validate(data, context=body).review()
        else:
            assert body["application_method"]["quote"] == "An algorithm needs a stopping condition."
            data = goal_verdict(body)
            data["application_method_check"] = data["checks"][2].pop("method_alignment")
            result = (
                review_contract(review_mode=body["review_mode"]).model_validate(data, context=body).review()
            )
        return {"review": result.model_dump()}

    runtime.provider.decide, runtime.provider.review = choose, review
    runtime.execute(test_study.start(setup))
    result = test_study.read(setup)
    assert result["run"]["status"] == "succeeded" and result["run"]["model_calls"] == 5
    events = test_study.read(setup, "EVENTS")["events"]
    assert sum(e["event_type"] == "protocol_retry_scheduled" for e in events) == 1


def test_goal_passage_addresses_keep_global_source_numbers_across_fields():
    body = goal_body()
    body["candidate"]["evidence_ids"] = ["e2", "e1"]
    body["candidate"]["questions"][0]["evidence_ids"] = ["e2"]
    wire = json.loads(review_wire_messages([{"role": "user", "content": json.dumps(body)}])[-1]["content"])
    own = wire["fields"][0]["own_evidence"]
    assert [item["text_ref"] for item in own] == ["p2", "p1"]
    assert [item["evidence_id"] for item in own] == ["field0_source2", "field0_source1"]
    assert wire["fields"][1]["own_evidence"][0]["evidence_id"] == "field1_source2"
    assert wire["fields"][1]["own_evidence"][0]["text_ref"] == "p2"
    assert {item["id"]: item["text"] for item in wire["passages"]}["p2"] == body["evidence"][1]["text"]


def test_negative_source_guard_preserves_raw_model_false_accept():
    body = goal_body()
    body["candidate"]["explanation"] = "方程组的解是两条直线的公共点。"
    body["evidence"][0]["text"] = "A single equation describes a line."
    data = goal_verdict(body)
    result = GoalFieldSupportVerdict.model_validate(data, context=body).review()
    assert result.issues == ["unsupported_explanation"]
    assert result.explanation_assessments[0].supported is True
    assert result.rule_observations
    body["evidence"][0]["text"] += " The solution must lie on both lines."
    result = GoalFieldSupportVerdict.model_validate(goal_verdict(body), context=body).review()
    assert not result.issues
    data = goal_verdict(body)
    data["explanation_checks"][0]["supported"] = False
    assert GoalFieldSupportVerdict.model_validate(data, context=body).review().issues == [
        "unsupported_explanation"
    ]


def test_correction_shape_guard_cannot_overwrite_raw_goal_assessment():
    body = goal_body()
    body["goal"] = "给一道公共点纠错题。"
    body["candidate"]["questions"][1]["question"] = "判断点 (1, 2) 是否满足两个方程。"
    result = GoalFieldSupportVerdict.model_validate(goal_verdict(body), context=body).review()
    assert result.issues == ["goal_mismatch"]
    assert all(check.matches for check in result.goal_assessments)
    assert result.rule_observations
    body["candidate"]["questions"][1]["question"] = "同学声称这个点不满足方程，请纠正错误。"
    assert not GoalFieldSupportVerdict.model_validate(goal_verdict(body), context=body).review().issues
    body["goal"] = "不需要纠错题。"
    body["candidate"]["questions"][1]["question"] = "判断点是否满足方程。"
    assert not GoalFieldSupportVerdict.model_validate(goal_verdict(body), context=body).review().issues


def test_named_review_binds_only_original_field_sources_and_preserves_legacy_validation():
    body = goal_body()
    data = goal_verdict(body)
    for check in data.pop("checks"):
        name = check.pop("field")
        check.pop("evidence_ids")
        data[name] = check
    for claim in data["explanation_checks"]:
        claim.pop("evidence_ids")
    result = GoalFieldSupportVerdict.model_validate(data, context=body).review()
    for index, field in enumerate(["explanation", "question_1", "question_2"]):
        expected = [body["candidate"], *body["candidate"]["questions"]][index]["evidence_ids"]
        assert [ground.source for ground in result.grounds[field]] == expected
    assert result.explanation_assessments[0].evidence_ids == body["candidate"]["evidence_ids"]
    data["question_2"]["evidence_ids"] = ["field0_source1"]
    with pytest.raises(ValidationError):
        GoalFieldSupportVerdict.model_validate(data, context=body)


def test_rejected_unsupported_question_need_not_invent_an_answer():
    body = goal_body()
    data = goal_verdict(body)
    data["checks"][1].update(
        issue="unsupported_question", correction="Use a taught concept", answer_check=None
    )
    result = GoalFieldSupportVerdict.model_validate(data, context=body).review()
    assert result.issues == ["unsupported_question"]
    assert all(answer.field != "question_1" for answer in result.answer_observations)
