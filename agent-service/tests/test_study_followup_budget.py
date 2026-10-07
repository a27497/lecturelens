"""Follow-up repair budget mechanics, using real PostgreSQL and fixture transport."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from test_study import read, setup  # noqa: F401
from test_study_atomic import judgment, response

from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.generation_budget import check_path, time_allocation
from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.request_budget import chat_payload, schema_transport
from lecturelens_agent.study.review_budget import reservation, timeout
from lecturelens_agent.study.store import BudgetExceeded, StudyError

SOURCE = (
    "每次递归将输入规模减半，直到达到基础情形，即子数组仅包含一个元素。此时该单一元素被直接返回作为峰值。"
)
GOOD = "每次递归将输入规模减半，直到子数组仅包含一个元素。此时返回该元素作为峰值。"
BAD = GOOD + "原始数组不会被修改。"


def test_followup_time_plan_covers_first_verification_and_bounded_final_correction():
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    row = dict(deadline=now + timedelta(seconds=90), model_calls=3, reserved_tokens=30000)
    plan = time_allocation(row, {"future_calls": 4}, now + timedelta(seconds=3))
    cutoff = datetime.fromisoformat(plan["preparation_deadline"])
    assert plan["final_review_seconds"] == pytest.approx(32.8)
    assert (cutoff - (now + timedelta(seconds=8))).total_seconds() == pytest.approx(44.2)
    # A first verification taking 30 seconds still leaves preparation for a
    # revision and two final requests. The absolute 90-second cutoff is intact.
    allocation = reservation(row, now + timedelta(seconds=38), review_seconds=plan["final_review_seconds"])
    assert allocation["preparation_deadline"] == plan["preparation_deadline"]
    row["final_review_reservation"] = allocation
    assert timeout(row, now=now + timedelta(seconds=38)) == pytest.approx(14.2)
    assert timeout(row, final_review=True, now=now + timedelta(seconds=45)) == pytest.approx(16.4)
    allocation["pending"] = False
    assert timeout(row, final_review=True, now=now + timedelta(seconds=70)) == 15
    with pytest.raises(StudyError):
        timeout(row, final_review=True, now=now + timedelta(seconds=85))
    assert row["deadline"] == now + timedelta(seconds=90)


@pytest.mark.parametrize("review_seconds", [0, -1, 61, float("inf"), float("nan")])
def test_followup_cannot_invent_a_larger_or_invalid_final_time_allowance(review_seconds):
    now = datetime(2026, 10, 2, tzinfo=timezone.utc)
    row = dict(deadline=now + timedelta(seconds=90), model_calls=3, reserved_tokens=30000)
    with pytest.raises(StudyError, match="FINAL_REVIEW_BUDGET_UNAVAILABLE"):
        reservation(row, now, review_seconds=review_seconds)


def test_schema_projection_retains_property_names_and_every_validation_constraint():
    schema = {
        "type": "function",
        "function": {
            "name": "x",
            "description": "binding",
            "parameters": {
                "title": "Annotation",
                "type": "object",
                "required": ["title"],
                "additionalProperties": False,
                "properties": {
                    "title": {"title": "Title", "type": "string", "maxLength": 40},
                    "explanation": {"description": "binding", "allOf": [{"not": {"pattern": "bad"}}]},
                },
            },
        },
    }
    projected = schema_transport([schema])[0]["function"]["parameters"]
    assert projected["properties"]["title"] == {"type": "string", "maxLength": 40}
    assert projected["required"] == ["title"] and projected["additionalProperties"] is False
    assert (
        projected["properties"]["explanation"]
        == schema["function"]["parameters"]["properties"]["explanation"]
    )
    # First-turn repairs need the same lossless projection as follow-ups;
    # otherwise annotation overhead can prevent the final review reservation.
    wire = chat_payload(
        "mock",
        [{"role": "user", "content": json.dumps({"revision_transaction": {"version": "v1"}})}],
        [schema],
        900,
    )
    assert wire["tools"][0]["function"]["parameters"] == projected
    assert schema["function"]["parameters"]["title"] == "Annotation"


@pytest.mark.parametrize("fault", ["tokens", "calls", "deadline", "review_size"])
def test_generation_is_stopped_before_external_call_when_complete_path_is_unavailable(fault):
    row = dict(model_calls=1, reserved_tokens=9000)
    path = dict(
        stage="generation",
        future_tokens=40000,
        future_calls=4,
        first_review=9000,
        preparation_deadline=(datetime.now(timezone.utc) + timedelta(seconds=20)).isoformat(),
    )
    if fault == "tokens":
        row["reserved_tokens"] = 40000
    elif fault == "calls":
        row["model_calls"] = 2
    elif fault == "deadline":
        path["preparation_deadline"] = (datetime.now(timezone.utc) - timedelta(seconds=1)).isoformat()
    else:
        path["stage"] = "first_review"
    with pytest.raises(StudyError):
        check_path(row, path, 10000)


def test_generation_reservation_survives_postgres_recovery_without_charging_forecasts(setup):  # noqa: F811
    store, _, _, scope = setup
    result = store.command(
        StudyCommand(**scope, operation="START", request_key="path", goal="Explain recursion"), "mock"
    )
    run = result["run"]["run_id"]
    store.claim(run, "first", 90)
    allocation = dict(
        generation_cost=8000,
        future_tokens=40000,
        future_calls=4,
        first_review=10000,
        max_chars=200,
        max_claims=8,
        max_citations=2,
        max_title=40,
        final_estimate={"cost": 7000},
    )
    before = store.plan_explanation_path(run, "first", allocation)
    store.claim(run, "recovery", 90)
    after = store.guard(run, "recovery")
    assert before["explanation_path_reservation"] == after["explanation_path_reservation"]
    assert before["explanation_path_reservation"]["version"] == "followup_path_v2"
    assert after["reserved_tokens"] == after["model_calls"] == 0
    assert after["deadline"] == before["deadline"]
    store.reserve(run, "recovery", "model", 8000)
    store.reserve(run, "recovery", "model", 9000)
    final = store.reserve_final_review(run, "recovery")
    assert (
        final["final_review_reservation"]["review_seconds"]
        == before["explanation_path_reservation"]["final_review_seconds"]
    )
    assert (
        final["final_review_reservation"]["preparation_deadline"]
        == before["explanation_path_reservation"]["preparation_deadline"]
    )
    assert final["final_review_reservation"]["generation_envelope"]["max_chars"] == 200
    assert final["reserved_tokens"] == 17000 and final["model_calls"] == 2
    assert store.guard(run, "recovery")["explanation_path_reservation"] is None


@pytest.mark.parametrize(
    "scope_protocol_retry,failure",
    [(False, None), (True, None), (False, "timeout"), (False, "decision_protocol")],
)
def test_followup_rejects_mutation_repairs_and_reviews_before_answer_and_clean_ledger(
    setup,  # noqa: F811 -- imported PostgreSQL fixture
    monkeypatch,
    scope_protocol_retry,
    failure,
):
    store, authority, runtime, scope = setup
    original_read = authority.read
    generations, reviews = [], []
    provider = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture")

    def course_read(s, action="CHECK", **kw):
        result = original_read(s, action, **kw)
        for item in result.get("evidence", []):
            item["text"] = SOURCE
        return result

    invalid_decision = False

    def decide(messages, timeout):
        nonlocal invalid_decision
        body = json.loads(messages[-1]["content"])
        generations.append(body)
        if body.get("revision_transaction"):
            assert body["generation_max_chars"] >= len(GOOD)
            return dict(
                name="create_explanation",
                arguments={
                    "revision_edits": [
                        {"id": c["id"], "replacement": ""} for c in body["revision_transaction"]["rejected"]
                    ]
                },
            )
        first = json.loads(messages[1]["content"])
        followup = bool(first.get("semantic_context", {}).get("previous_turns"))
        if failure == "decision_protocol" and followup and not invalid_decision:
            invalid_decision = True
            raise StudyError("MODEL_TOOL_CONTRACT")
        if (
            not body.get("evidence")
            or body.get("observe_before_generation")
            or (followup and not body["history"])
        ):
            return dict(
                name="search_course_evidence",
                arguments=dict(
                    query="递归停止条件",
                    output_kind="explanation",
                    **(
                        {"resolved_goal": "峰值算法一直递归下去，数组最后变成什么样？"}
                        if len(generations) > 2
                        else {}
                    ),
                ),
            )
        prior = json.loads(messages[1]["content"]).get("semantic_context", {}).get("previous_turns")
        return dict(
            name="create_explanation",
            arguments=dict(
                title="递归停止",
                explanation=BAD if prior else GOOD,
                evidence_ids=[body["evidence"][0]["evidence_id"]],
                **({"resolved_goal": "峰值算法一直递归下去，数组最后变成什么样？"} if prior else {}),
            ),
        )

    invalid_sent = False

    def handle(request):
        nonlocal invalid_sent
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        reviews.append(body)
        verdict = judgment(body)
        if scope_protocol_retry and body.get("goal_scope_binding") and not invalid_sent:
            invalid_sent = True
            verdict["goal_checks"][0]["id"] = "g9"
        return response(verdict)

    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handle), **kw))
    authority.read = course_read
    provider.decide = decide
    original_review = provider.review

    def review(messages, limit):
        body = json.loads(messages[-1]["content"])
        if failure == "timeout" and body.get("semantic_context", {}).get("previous_turns"):
            raise BudgetExceeded()
        return original_review(messages, limit)

    provider.review = review
    runtime.provider = provider

    def run(key, goal):
        created = store.command(StudyCommand(**scope, operation="START", request_key=key, goal=goal), "real")
        return next(r for r in store.candidates() if r["run_id"] == created["run"]["run_id"])

    runtime.execute(run("first", "解释峰值算法的递归停止条件"))
    assert read(setup)["run"]["status"] == "succeeded", read(setup)["run"]
    follow = run("follow", "那一直这样递归下去，数组最后变成什么样？")
    runtime.execute(follow)
    result = read(setup)
    if failure == "decision_protocol":
        assert result["run"]["status"] == "failed" and result["artifact"] is None
        assert result["run"]["error_code"] == "FINAL_REVIEW_BUDGET_UNAVAILABLE"
        assert any(b.get("tool_contract_feedback") for b in generations)
        assert result["run"]["model_calls"] <= 6
        return
    if failure == "timeout":
        assert result["run"]["status"] == "failed" and result["artifact"] is None
        assert result["run"]["error_code"] == "EXPLANATION_PATH_TIMEOUT"
        assert result["run"]["model_calls"] == 3 and result["run"]["reserved_tokens"] > 0
        with store.connect() as conn:
            failed = conn.execute(
                "SELECT payload FROM study_event WHERE run_id=%s AND event_type='model_failed'",
                (follow["run_id"],),
            ).fetchall()
        assert failed[-1]["payload"]["error_code"] == "EXPLANATION_PATH_TIMEOUT"
        return
    assert result["run"]["status"] == "succeeded", result["run"]
    assert result["artifact"]["explanation"] == GOOD
    assert result["run"]["model_calls"] == (6 if scope_protocol_retry else 5)
    assert result["run"]["reserved_tokens"] <= 64000
    assert any(b.get("revision_transaction") for b in generations)
    assert any(b.get("goal_scope_binding") for b in reviews)
    with store.connect() as conn:
        events = conn.execute(
            "SELECT event_type,payload FROM study_event WHERE run_id=%s ORDER BY sequence",
            (follow["run_id"],),
        ).fetchall()
        quality = conn.execute(
            "SELECT result FROM study_tool_result WHERE run_id=%s AND tool_name='create_explanation' ORDER BY call_id",
            (follow["run_id"],),
        ).fetchall()
    assert any(e["event_type"] == "explanation_path_reserved" for e in events)
    rejected = quality[0]["result"]["quality"]["atomic_assessments"]
    assert any(not c["supported"] and "input_mutation_policy" in c["strengthening_guards"] for c in rejected)
    facts = store.supported_facts(follow)
    assert facts and all("修改" not in f["text"] for f in facts)
    assert bool(any("protocol_feedback" in b for b in reviews)) == scope_protocol_retry
