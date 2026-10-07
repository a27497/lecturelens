"""Persistent review reservation and bounded stop, using no live provider."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from test_study import read, setup, start  # noqa: F401
from test_study_atomic import judgment, response
from test_study_delta import INITIAL, NARROWED, SOURCE, delta_verdict

from lecturelens_agent.study.provider import ChatProvider
from lecturelens_agent.study.review_budget import check_spend, priced, reservation, timeout
from lecturelens_agent.study.store import BudgetExceeded, StudyError

NOW = datetime(2026, 9, 30, tzinfo=timezone.utc)


def row(**kwargs):
    return dict(deadline=NOW + timedelta(seconds=90), model_calls=3, reserved_tokens=31791) | kwargs


@pytest.mark.parametrize("elapsed,calls,tokens", [(25, 3, 31000), (10, 4, 31000), (10, 3, 63800)])
def test_revision_is_not_started_without_the_full_review_allowance(elapsed, calls, tokens):
    with pytest.raises(StudyError, match="FINAL_REVIEW_BUDGET_UNAVAILABLE"):
        reservation(row(model_calls=calls, reserved_tokens=tokens), NOW + timedelta(seconds=elapsed))


def test_frozen_trace_preparation_and_final_call_have_separate_deadlines():
    r = row()
    r["final_review_reservation"] = reservation(r, NOW + timedelta(seconds=10.8))
    assert timeout(r, now=NOW + timedelta(seconds=10.8)) == pytest.approx(14.2)
    assert timeout(r, final_review=True, now=NOW + timedelta(seconds=12.658)) == 30
    with pytest.raises(StudyError):
        timeout(r, final_review=True, now=NOW + timedelta(seconds=26))
    r["final_review_reservation"]["pending"] = False
    assert timeout(r, final_review=True, now=NOW + timedelta(seconds=80)) == 5
    with pytest.raises(StudyError):
        timeout(r, now=NOW + timedelta(seconds=25))
    with pytest.raises(StudyError):
        timeout(r, final_review=True, now=NOW + timedelta(seconds=85))


def test_call_and_token_allowance_cannot_be_used_by_preparation():
    r = row(model_calls=4)
    r["final_review_reservation"] = priced(reservation(row(), NOW), {"cost": 5000})
    with pytest.raises(StudyError):
        check_spend(r, "model", 1, False)
    check_spend(r, "model", 11217, True)
    with pytest.raises(StudyError):
        check_spend(
            row(reserved_tokens=60000, final_review_reservation=r["final_review_reservation"]),
            "model",
            1001,
            False,
        )


def test_postgres_reservation_survives_recovery_and_charges_only_actual_calls(setup):  # noqa: F811
    store, _, _, _ = setup
    run = start(setup)
    store.claim(run["run_id"], "worker", 90)
    store.reserve_final_review(run["run_id"], "worker")
    before = store.plan_final_review(run["run_id"], "worker", {"cost": 5000}, 12000)
    store.reserve(run["run_id"], "worker", "model", 12000)
    store.claim(run["run_id"], "recovery", 90)
    assert timeout(store.guard(run["run_id"], "recovery"), final_review=True) == 30
    recovered = store.reserve_final_review(run["run_id"], "recovery")
    assert before["deadline"] == recovered["deadline"]
    assert before["final_review_reservation"] == recovered["final_review_reservation"]
    assert recovered["model_calls"] == 1 and recovered["reserved_tokens"] == 12000
    with store.connect() as conn:
        conn.execute("UPDATE study_run SET model_calls=4 WHERE run_id=%s", (run["run_id"],))
    with pytest.raises(StudyError, match="FINAL_REVIEW_BUDGET_UNAVAILABLE"):
        store.reserve(run["run_id"], "recovery", "model", 1)
    store.reserve(run["run_id"], "recovery", "model", 11217, final_review=True)
    current = store.guard(run["run_id"], "recovery")
    assert current["final_review_reservation"]["pending"] is False
    assert current["final_review_reservation"]["correction_pending"] is True
    store.reserve(run["run_id"], "recovery", "model", 11217, final_review=True)
    assert store.guard(run["run_id"], "recovery")["model_calls"] == 6
    with pytest.raises(StudyError, match="FINAL_REVIEW_BUDGET_UNAVAILABLE"):
        store.reserve(run["run_id"], "recovery", "model", 1, final_review=True)


@pytest.mark.parametrize("failure", [None, "prepare", "final", "late"])
def test_runtime_preserves_delta_review_or_stops_without_publishing(setup, monkeypatch, failure):  # noqa: F811
    store, authority, runtime, _ = setup
    original_read = authority.read
    requests, review_timeouts, revision_timeouts = [], [], []

    def course_read(scope, action="CHECK", **kw):
        result = original_read(scope, action, **kw)
        for e in result.get("evidence", []):
            e["text"] = SOURCE
        return result

    def decide(messages, limit):
        body = json.loads(messages[-1]["content"])
        if not body["history"]:
            return dict(
                name="search_course_evidence", arguments=dict(query=body["goal"], output_kind="explanation")
            )
        if body.get("revision_transaction"):
            revision_timeouts.append(limit)
            assert 0 < limit < 25
            if failure == "prepare":
                raise BudgetExceeded()
            return dict(
                name="create_explanation",
                arguments=dict(
                    revision_edits=[
                        dict(id=c["id"], replacement="") for c in body["revision_transaction"]["rejected"]
                    ]
                ),
            )
        return dict(
            name="create_explanation", arguments=dict(title="State", explanation=INITIAL, evidence_ids=["e1"])
        )

    def handle(request):
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        requests.append(body)
        if len(requests) == 2 and failure == "final":
            raise httpx.ReadTimeout("fixture", request=request)
        if len(requests) == 2 and failure == "late":
            with store.connect() as conn:
                conn.execute(
                    "UPDATE study_run SET deadline=now()+interval '4 seconds' WHERE run_id=%s",
                    (run["run_id"],),
                )
        return response(delta_verdict(body) if "review_claim_ids" in body else judgment(body))

    authority.read = course_read
    runtime.provider.decide = decide
    client = httpx.Client
    monkeypatch.setattr(httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handle), **kw))
    provider = ChatProvider("https://fixture.invalid/v1", "qwen3-max", "fixture")

    def review(messages, limit):
        review_timeouts.append(limit)
        return provider.review(messages, limit)

    runtime.provider.review = review
    run = start(setup)
    runtime.execute(run)
    result = read(setup)
    assert len(revision_timeouts) == 1
    if failure:
        assert result["run"]["status"] == "failed" and result["artifact"] is None
        assert result["run"]["error_code"] in {"FINAL_REVIEW_BUDGET_UNAVAILABLE", "FINAL_REVIEW_TIMEOUT"}
    else:
        assert result["run"]["status"] == "succeeded"
        assert result["artifact"]["explanation"] == NARROWED
        assert len(requests) == 2 and requests[1]["atomic_claims"] == []
        assert requests[1]["reused_claim_ids"] and requests[1]["review_claim_ids"] == []
        assert review_timeouts[1] == 30
    assert len(requests) == (1 if failure == "prepare" else 2)
    with store.connect() as conn:
        events = conn.execute(
            "SELECT payload FROM study_event WHERE run_id=%s AND event_type='final_review_reserved'",
            (run["run_id"],),
        ).fetchall()
    assert len(events) == 1
    assert events[0]["payload"]["model_calls"] == 2
    assert authority.reads.count("SEARCH") == 1


def test_preparation_requires_a_priced_plan():
    r = row(final_review_reservation=reservation(row(), NOW))
    with pytest.raises(StudyError, match="FINAL_REVIEW_ESTIMATE_REQUIRED"):
        check_spend(r, "model", 1, False)


def test_legacy_answer_protocol_does_not_invent_an_atomic_scope_retry():
    r = row(model_calls=4)
    r["final_review_reservation"] = priced(reservation(r, NOW, correction=False), {"cost": 5000})
    assert r["final_review_reservation"]["model_calls"] == 1
    assert r["final_review_reservation"]["correction_tokens"] == 0
    assert r["final_review_reservation"]["correction_pending"] is False
    check_spend(r, "model", 10000, False)


@pytest.mark.parametrize(
    "extra,used,accepted", [(100, 10000, True), (1000, 10000, True), (1000, 53000, False)]
)
def test_actual_request_is_repriced_or_stopped_before_any_review_call(setup, extra, used, accepted):  # noqa: F811
    store, _, _, _ = setup
    run = start(setup)
    store.claim(run["run_id"], "worker", 90)
    store.reserve_final_review(run["run_id"], "worker")
    planned = store.plan_final_review(run["run_id"], "worker", {"cost": 10000}, 900)
    with store.connect() as conn:
        conn.execute("UPDATE study_run SET reserved_tokens=%s WHERE run_id=%s", (used, run["run_id"]))
    actual = planned["final_review_reservation"]["estimated"] + extra
    if accepted:
        store.reserve(
            run["run_id"],
            "worker",
            "model",
            actual,
            final_review=True,
            review_estimate={"cost": actual, "correction_estimate": {"cost": actual + 293}},
        )
        r = store.guard(run["run_id"], "worker")
        assert r["model_calls"] == 1 and r["reserved_tokens"] == used + actual
        a = r["final_review_reservation"]
        assert a["estimated"] == actual and a["actual"] == actual
        assert a["correction_pending"] and a["correction_estimated"] == actual + 293
        assert a["reconciled_reserved"] > 2 * actual
    else:
        with pytest.raises(StudyError, match="FINAL_REVIEW_BUDGET_UNAVAILABLE"):
            store.reserve(run["run_id"], "worker", "model", actual, final_review=True)
        r = store.guard(run["run_id"], "worker")
        assert r["model_calls"] == 0 and r["reserved_tokens"] == used
        assert r["final_review_reservation"]["pending"] is True


@pytest.mark.parametrize(
    "url", ["https://dashscope.aliyuncs.com/compatible-mode/v1", "https://fixture.invalid/v1"]
)
def test_request_pricing_equals_actual_provider_encoding_without_altering_payload(monkeypatch, url):
    from lecturelens_agent.study.request_budget import request_cost

    provider = ChatProvider(url, "qwen3-max", "fixture")
    messages = [{"role": "user", "content": "比较规模减半"}]
    schemas = [
        {"type": "function", "function": {"name": "search_course_evidence", "parameters": {"type": "object"}}}
    ]
    cost = request_cost(provider, "decision", messages, schemas, 900)
    client = httpx.Client

    def handle(request):
        payload = json.loads(request.content)
        assert cost["request_bytes"] == len(request.content)
        assert cost["cost"] == len(request.content) + payload["max_tokens"]
        assert payload["model"] == "qwen3-max" and payload["max_tokens"] == 900
        assert payload["messages"] == messages and payload["tools"] == schemas
        assert payload["temperature"] == 0.2 and payload["parallel_tool_calls"] is False
        assert payload["tool_choice"] == (
            {"type": "function", "function": {"name": "search_course_evidence"}}
            if "dashscope" in url
            else "required"
        )
        return httpx.Response(
            200,
            json={
                "choices": [
                    {
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": "search_course_evidence",
                                        "arguments": '{"query":"x"}',
                                    },
                                }
                            ]
                        }
                    }
                ]
            },
        )

    monkeypatch.setattr(httpx, "Client", lambda **kw: client(transport=httpx.MockTransport(handle), **kw))
    assert provider._request(messages, schemas, 1, 900)["calls"][0]["name"] == "search_course_evidence"


@pytest.mark.parametrize("used,admitted", [(47000, True), (50000, False)])
def test_legacy_admitted_revision_recovery_prices_actual_without_resetting_budgets(setup, used, admitted):  # noqa: F811
    store, _, _, _ = setup
    run = start(setup)
    store.claim(run["run_id"], "old-worker", 90)
    before = store.reserve_final_review(run["run_id"], "old-worker")
    legacy = {
        k: before["final_review_reservation"][k]
        for k in ["review_seconds", "finish_seconds", "model_calls", "preparation_deadline", "pending"]
    } | {"tokens": 13000, "model_calls": 1}
    with store.connect() as conn:
        from psycopg.types.json import Jsonb

        conn.execute(
            "UPDATE study_run SET final_review_reservation=%s,model_calls=4,reserved_tokens=%s WHERE run_id=%s",
            (Jsonb(legacy), used, run["run_id"]),
        )
    store.claim(run["run_id"], "recovery", 90)
    if not admitted:
        with pytest.raises(StudyError, match="FINAL_REVIEW_BUDGET_UNAVAILABLE"):
            store.reserve(run["run_id"], "recovery", "model", 7000, final_review=True)
        r = store.guard(run["run_id"], "recovery")
        assert r["deadline"] == before["deadline"] and r["reserved_tokens"] == used and r["model_calls"] == 4
        return
    store.reserve(run["run_id"], "recovery", "model", 7000, final_review=True)
    r = store.guard(run["run_id"], "recovery")
    assert r["deadline"] == before["deadline"]
    assert r["model_calls"] == 5 and r["reserved_tokens"] == used + 7000
    assert r["final_review_reservation"]["estimated"] == 7000
    assert r["final_review_reservation"]["actual"] == 7000
    assert r["final_review_reservation"]["pending"] is False
    assert r["final_review_reservation"]["correction_pending"] is True


def test_case9_original_chain_stops_before_revision_instead_of_after_final_review(setup):  # noqa: F811
    store, _, _, _ = setup
    run = start(setup)
    store.claim(run["run_id"], "worker", 90)
    with store.connect() as conn:
        conn.execute(
            "UPDATE study_run SET model_calls=3,reserved_tokens=31698 WHERE run_id=%s", (run["run_id"],)
        )
    store.reserve_final_review(run["run_id"], "worker")
    estimate = {"cost": 13038, "correction_estimate": {"cost": 13534}}
    with pytest.raises(StudyError, match="FINAL_REVIEW_BUDGET_UNAVAILABLE"):
        store.plan_final_review(run["run_id"], "worker", estimate, 13951)
    r = store.guard(run["run_id"], "worker")
    assert r["model_calls"] == 3 and r["reserved_tokens"] == 31698


def test_full_correction_reserve_survives_restart_and_cannot_be_spent_by_preparation(setup):  # noqa: F811
    store, _, _, _ = setup
    run = start(setup)
    store.claim(run["run_id"], "worker", 90)
    with store.connect() as conn:
        conn.execute(
            "UPDATE study_run SET model_calls=3,reserved_tokens=31116 WHERE run_id=%s", (run["run_id"],)
        )
    estimate = {"cost": 10025, "correction_estimate": {"cost": 10318}}
    before = store.reserve_final_review(run["run_id"], "worker")
    planned = store.plan_final_review(run["run_id"], "worker", estimate, 11077)
    assert planned["reserved_tokens"] + 11077 + planned["final_review_reservation"]["tokens"] + 256 == 63806
    store.reserve(run["run_id"], "worker", "model", 11077)
    store.reserve(run["run_id"], "worker", "model", 10025, final_review=True, review_estimate=estimate)
    store.claim(run["run_id"], "recovery", 90)
    recovered = store.guard(run["run_id"], "recovery")
    assert recovered["deadline"] == before["deadline"]
    assert recovered["model_calls"] == 5 and recovered["final_review_reservation"]["correction_pending"]
    with pytest.raises(StudyError, match="FINAL_REVIEW_BUDGET_UNAVAILABLE"):
        store.reserve(run["run_id"], "recovery", "model", 1)
    store.reserve(run["run_id"], "recovery", "model", 10318, final_review=True)
    r = store.guard(run["run_id"], "recovery")
    assert r["model_calls"] == 6 and r["reserved_tokens"] == 62536
    assert not r["final_review_reservation"]["correction_pending"]


def test_old_scoped_forecast_is_upgraded_before_preparation_without_resetting_execution(setup):  # noqa: F811
    from psycopg.types.json import Jsonb

    store, _, _, _ = setup
    run = start(setup)
    store.claim(run["run_id"], "old-worker", 90)
    before = store.reserve_final_review(run["run_id"], "old-worker")
    old = {
        **before["final_review_reservation"],
        "version": "dynamic_final_review_v1",
        "model_calls": 1,
        "estimated": 5000,
        "tokens": 5250,
    }
    old.pop("correction_pending")
    with store.connect() as conn:
        conn.execute(
            "UPDATE study_run SET final_review_reservation=%s,model_calls=3,reserved_tokens=31116 WHERE run_id=%s",
            (Jsonb(old), run["run_id"]),
        )
    store.claim(run["run_id"], "recovery", 90)
    recovered = store.reserve_final_review(run["run_id"], "recovery")
    assert recovered["deadline"] == before["deadline"]
    assert recovered["model_calls"] == 3 and recovered["reserved_tokens"] == 31116
    allocation = recovered["final_review_reservation"]
    assert allocation["version"] == "dynamic_final_review_v2" and allocation["model_calls"] == 2
    assert allocation["correction_pending"] and allocation["tokens"] > 2 * 5000


def test_correction_is_priced_from_exact_wire_and_shares_the_original_deadline():
    from test_study_goal_scope import scoped_input

    from lecturelens_agent.study.quality import review_schema, review_wire_messages
    from lecturelens_agent.study.request_budget import request_cost
    from lecturelens_agent.study.runtime import price_review, review_correction

    messages, body, _ = scoped_input()
    provider = ChatProvider("https://dashscope.aliyuncs.com/compatible-mode/v1", "qwen3-max", "fixture")
    estimate = price_review(provider, messages)
    retry = review_correction(messages)
    schema = review_schema("explanation", review_mode=body["review_mode"], context=body)
    assert (
        request_cost(provider, "review", review_wire_messages(retry), [schema], 1600)
        == estimate["correction_estimate"]
    )
    assert json.loads(retry[-1]["content"])["candidate"] == body["candidate"]
    r = row(final_review_reservation=priced(reservation(row(), NOW), estimate))
    assert timeout(r, final_review=True, now=NOW + timedelta(seconds=25 - 0.001)) == 30
    # Even a first review using its whole slot leaves 30s before finish.
    r["final_review_reservation"]["pending"] = False
    assert timeout(r, final_review=True, now=NOW + timedelta(seconds=55)) == 30
    assert timeout(r, final_review=True, now=NOW + timedelta(seconds=70)) == 15
    with pytest.raises(StudyError):
        timeout(r, final_review=True, now=NOW + timedelta(seconds=85))
