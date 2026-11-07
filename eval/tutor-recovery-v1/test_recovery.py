"""No-cost retained-response, PG recovery, budget and independent-session regressions."""

import copy
import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import contract
import httpx
import psycopg
import pytest
import session_driver as driver
from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor.contracts import Command
from lecturelens_real_eval.tutor.grounded_runtime import (
    GroundedTutorRuntime,
    PassageAuthority,
)
from lecturelens_real_eval.tutor.repair_context_runtime import RepairContextTutorRuntime
from lecturelens_real_eval.tutor.runtime import MockTutor
from lecturelens_real_eval.tutor.store import TutorStore
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.types.json import Jsonb
from replay_support import RetainedTransport, frames, jsonl, read

RAW = contract.ROOT / ".data/tutor-fresh-live-20261107"
ARTIFACTS = contract.ROOT / ".data/tutor-recovery-v1-20261107"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = os.environ.get

    def get(key, *args):
        if key in {"AGENT_LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"}:
            pytest.fail("credential lookup forbidden in offline validation")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", get)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kw: pytest.fail("real transport forbidden"))
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"


@pytest.fixture
def isolated():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "recovery_test_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    yield make_conninfo(dsn, options=f"-csearch_path={schema},public")
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


class FinishFixture:
    """Synthetic short finish tests protocol only; it is not a model quality label."""

    def __init__(self, *, invalid=False):
        self.messages, self.invalid = [], invalid

    def decide(self, messages, schemas, timeout):
        self.messages.append(copy.deepcopy(messages))
        body = json.loads(messages[-1]["content"])
        eid = body["evidence"][0]["evidence_id"]
        return dict(
            name="finish_tutor_turn",
            arguments=dict(
                outcome="answered",
                text=("X" * 1601 if self.invalid else "Place comments in a separate column.") + f" [{eid}]",
            ),
            usage={"prompt_tokens": 10, "completion_tokens": 10},
        )


def seed(dsn, runtime_class=RepairContextTutorRuntime, provider=None):
    """Copy only the known received checkpoint/counters into a new synthetic scope."""
    ex = next(iter(read(RAW / "postgres-run-snapshot.json").values()))
    original = next(t for t in ex["turns"] if t["status"] == "failed")
    previous = next(t for t in ex["turns"] if t["session_id"] == original["session_id"] and t["ordinal"] == 1)
    _, _, snapshot = contract.data.load()
    authority = PassageAuthority(snapshot)
    scope = dict(owner_id=811012, course_id="seed-" + uuid.uuid4().hex, revision=1)
    authority.register(scope, "carpentries-spreadsheets")
    store = TutorStore(dsn)
    runtime = runtime_class(store, authority, provider or FinishFixture())
    runtime.initialize()
    scope["session_id"] = runtime.command(Command(**scope, operation="CREATE", request_key="session"))[
        "session"
    ]["session_id"]
    runtime.command(
        Command(
            **scope,
            operation="TURN",
            client_turn_id="prior",
            text=previous["learner_text"],
        )
    )
    with store.connect() as conn:
        conn.execute(
            "UPDATE tutor_turn SET status='completed',outcome='answered',answer=%s,evaluation='' WHERE session_id=%s",
            (previous["answer"], scope["session_id"]),
        )
    runtime.command(
        Command(
            **scope,
            operation="TURN",
            client_turn_id="failed",
            text=original["learner_text"],
        )
    )
    candidate = store.candidates()[0]
    with store.connect() as conn:
        conn.execute(
            "UPDATE tutor_turn SET checkpoint=%s,model_calls=3,tool_calls=2,reserved_tokens=45053,usage=%s WHERE turn_id=%s",
            (
                Jsonb(original["checkpoint"]),
                Jsonb(original["usage"]),
                candidate["turn_id"],
            ),
        )
        conn.execute(
            "UPDATE tutor_session SET model_calls=5,reserved_tokens=66864 WHERE session_id=%s",
            (scope["session_id"],),
        )
    return runtime, candidate, scope, original


def get(runtime, candidate):
    with runtime.store.connect() as conn:
        return runtime.store.rows(conn, candidate["turn_id"])


def save_result(name, value):
    # Run with a new evidence directory per supervised validation, never overwrite.
    folder = Path(os.environ["RECOVERY_CHECK_OUTPUT"])
    folder.mkdir(parents=True, exist_ok=True)
    with (folder / name).open("x") as output:
        json.dump(value, output, indent=2, default=str)
        output.write("\n")


def test_additive_identity_and_frozen_parents():
    assert contract.verify_candidate() != contract.PARENT
    assert contract.bridge.verify_candidate() == contract.PARENT
    assert contract.CANDIDATE != contract.bridge.repair_check.CANDIDATE
    assert contract.data.load()[0]["counts"]["turns"] == 16


def test_v11_exact_retained_replay_and_stop_propagation(isolated, tmp_path):
    retained = frames(RAW)
    transport = RetainedTransport(retained)
    result = driver.run(tmp_path / "v11", isolated, transport, legacy=True)
    assert len(transport.sent) == 17
    assert (
        result["completed_turns"],
        result["failed_turns"],
        result["missing_result_turns"],
    ) == (6, 1, 9)
    rows = jsonl(tmp_path / "v11/turns.jsonl")
    assert rows[6]["error_code"] == "TUTOR_REPAIR_BUDGET_UNAVAILABLE"
    old = jsonl(RAW / "fresh-real16/turns.jsonl")
    assert all(rows[i]["answer"] == old[i]["answer"] for i in range(6))
    assert result["ledger"]["nano_usd"] == 22_652_400
    save_result(
        "v11-retained-replay.json",
        dict(result=result, matched_wire_requests=17, matched_original_answers=6),
    )


@pytest.mark.parametrize(
    "runtime_class,expected,number",
    [
        (GroundedTutorRuntime, "TUTOR_REPAIR_BUDGET_UNAVAILABLE", 0),
        (RepairContextTutorRuntime, None, 1),
    ],
)
def test_original_received_checkpoint_repairs_without_larger_caps(isolated, runtime_class, expected, number):
    provider = FinishFixture()
    runtime, candidate, _, source = seed(isolated, runtime_class, provider)
    runtime.execute(candidate)
    session, turn = get(runtime, candidate)
    assert turn["error_code"] == expected and len(provider.messages) == number
    assert session["max_calls"] == 60 and session["max_tokens"] == 640000
    assert turn["checkpoint"]["selected"] == source["checkpoint"]["selected"]
    if expected:
        assert turn["reserved_tokens"] == 45053 and turn["status"] == "failed"
        assert not any(o.get("error") for o in turn["checkpoint"]["observations"])
    else:
        assert turn["reserved_tokens"] == 61475 and turn["model_calls"] == 4
        body = json.loads(provider.messages[0][-1]["content"])
        repair = next(o for o in body["observations"] if o.get("error"))
        assert [e["evidence_id"] for e in body["evidence"]] == repair["keep_ids"]
        assert len(body["history"]) == 1
        assert (
            body["history"][0]["answer"]
            == json.loads(frames(RAW)[16]["request"]["messages"][-1]["content"])["history"][0]["answer"]
        )
        assert turn["status"] == "completed"
        save_result(
            "v12-checkpoint-synthetic-repair.json",
            dict(
                turn=turn,
                session=session,
                repair_request=provider.messages[0],
                real_quality="NOT_RUN",
            ),
        )
    runtime.close()


def test_normal_requests_are_identical_to_v11_and_repair_keeps_authority(isolated):
    runtime, candidate, _, _ = seed(isolated)
    session, turn = get(runtime, candidate)
    state = turn["checkpoint"]
    with runtime.store.connect() as conn:
        history = runtime.context(conn, session, turn)
    parent = GroundedTutorRuntime(runtime.store, runtime.authority)
    assert parent.request(session, turn, state, history) == runtime.request(session, turn, state, history)
    # Publication validates all five IDs before context can be projected to four.
    removed = state["response"]["arguments"]["text"].split("[")[-1].split("]")[0]
    original_read = runtime.authority.read
    reads = []

    def deleted(scope, action="CHECK", **kw):
        if action == "READ":
            reads.extend(kw["evidence_ids"])
            if removed in kw["evidence_ids"]:
                raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED")
        return original_read(scope, action, **kw)

    with patch.object(runtime.authority, "read", side_effect=deleted):
        runtime.execute(candidate)
    assert removed in reads
    assert get(runtime, candidate)[1]["error_code"] == "COURSE_UNAVAILABLE_OR_CHANGED"
    assert not runtime.provider.messages


@pytest.mark.parametrize(
    "dimension,extra",
    [(d, e) for d in ("turn_tokens", "session_tokens", "turn_calls", "session_calls") for e in (0, 1)],
)
def test_repair_budget_exact_boundary_and_one_unit_over(isolated, dimension, extra):
    runtime, candidate, _, _ = seed(isolated)
    with runtime.store.connect() as conn:
        if dimension == "turn_tokens":
            conn.execute(
                "UPDATE tutor_turn SET reserved_tokens=%s WHERE turn_id=%s",
                (64000 - 16422 + extra, candidate["turn_id"]),
            )
        if dimension == "session_tokens":
            conn.execute(
                "UPDATE tutor_session SET reserved_tokens=%s WHERE session_id=%s",
                (640000 - 16422 + extra, candidate["session_id"]),
            )
        if dimension == "turn_calls":
            conn.execute(
                "UPDATE tutor_turn SET model_calls=%s WHERE turn_id=%s",
                (4 + extra, candidate["turn_id"]),
            )
        if dimension == "session_calls":
            conn.execute(
                "UPDATE tutor_session SET model_calls=%s WHERE session_id=%s",
                (59 + extra, candidate["session_id"]),
            )
    runtime.execute(candidate)
    _, turn = get(runtime, candidate)
    assert turn["status"] == ("failed" if extra else "completed")
    assert len(runtime.provider.messages) == (0 if extra else 1)
    if extra:
        assert turn["error_code"] == "TUTOR_REPAIR_BUDGET_UNAVAILABLE"
        assert not any(o.get("error") for o in turn["checkpoint"]["observations"])


def test_second_format_violation_does_not_buy_another_repair(isolated):
    runtime, candidate, _, _ = seed(isolated, provider=FinishFixture(invalid=True))
    runtime.execute(candidate)
    turn = get(runtime, candidate)[1]
    assert turn["status"] == "failed" and turn["error_code"] == "TUTOR_FINISH_FORMAT_INVALID"
    assert len(runtime.provider.messages) == 1 and turn["model_calls"] == 4
    assert (
        sum(o.get("error") == "TUTOR_FINISH_REPAIR_REQUIRED" for o in turn["checkpoint"]["observations"]) == 1
    )


@pytest.mark.parametrize("stop", ["restart", "cancel", "authority", "unknown"])
def test_prepaid_repair_keeps_recovery_cancel_authority_and_unknown_fences(isolated, stop):
    runtime, candidate, scope, _ = seed(isolated)
    session, turn = get(runtime, candidate)
    with runtime.store.connect() as conn:
        history = runtime.context(conn, session, turn)
    assert runtime.act(candidate["turn_id"], turn["checkpoint"], history) is False
    prepaid = get(runtime, candidate)[1]
    assert prepaid["reserved_tokens"] == 61475 and prepaid["model_calls"] == 4
    assert "repair_request" in prepaid["checkpoint"]
    if stop == "cancel":
        runtime.command(Command(**scope, operation="CANCEL", client_turn_id="failed"))
    elif stop == "authority":
        runtime.authority.scopes[scope["course_id"]][0]["revision"] = 2
    elif stop == "unknown":
        checkpoint = {**prepaid["checkpoint"], "phase": "reserved"}
        with runtime.store.connect() as conn:
            conn.execute(
                "UPDATE tutor_turn SET checkpoint=%s WHERE turn_id=%s",
                (Jsonb(checkpoint), candidate["turn_id"]),
            )
    provider = FinishFixture()
    restarted = RepairContextTutorRuntime(runtime.store, runtime.authority, provider)
    restarted.execute(candidate)
    after = get(restarted, candidate)[1]
    assert after["model_calls"] == 4 and after["reserved_tokens"] == 61475
    assert len(provider.messages) == (1 if stop == "restart" else 0)
    if stop == "unknown":
        assert after["error_code"] == "TUTOR_UNKNOWN_MODEL_OUTCOME"
    if stop == "cancel":
        assert after["status"] == "cancelled"


@pytest.mark.parametrize("keep", [[], ["e1"], ["foreign"], None, ["e1"] * 5, ["e1", "e1"], [{}]])
def test_repair_projection_validation(keep):
    runtime = RepairContextTutorRuntime(None, None)
    state = dict(
        selected=["e1", "e2"],
        observations=[
            dict(
                tool="finish_tutor_turn",
                error="TUTOR_FINISH_REPAIR_REQUIRED",
                keep_ids=keep,
            )
        ],
    )
    with patch.object(
        runtime,
        "read_evidence",
        return_value=[
            dict(evidence_id="e1", text="one"),
            dict(evidence_id="e2", text="two"),
        ],
    ):
        if keep in ([], ["e1"]):
            messages, schemas, amount = runtime.request(
                dict(summary=""), dict(learner_text="Q", socratic=False), state, []
            )
            assert len(json.loads(messages[-1]["content"])["evidence"]) == len(keep)
            assert amount == len(json.dumps([messages, schemas], ensure_ascii=False).encode()) + 1200
        else:
            with pytest.raises(StudyError, match="TUTOR_PROTOCOL_FAILURE"):
                runtime.request(dict(summary=""), dict(learner_text="Q", socratic=False), state, [])


def mechanical_transport(*, local_failure=False, fault=None):
    model = MockTutor()
    seen = []

    def send(request):
        payload = json.loads(request.content)
        body = json.loads(payload["messages"][-1]["content"])
        seen.append(body)
        if fault == "timeout":
            raise httpx.ReadTimeout("synthetic")
        decision = model.decide(payload["messages"], payload["tools"], 20)
        if (
            local_failure
            and "In the Slicing Strings exercise" in body["learner_text"]
            and body["observations"]
        ):
            decision = dict(
                name="finish_tutor_turn",
                arguments=dict(
                    outcome="answered",
                    text="X" * 1601 + f" [{body['evidence'][0]['evidence_id']}]",
                ),
            )
        response = dict(
            usage=dict(prompt_tokens=100, completion_tokens=60),
            choices=[
                dict(
                    finish_reason="tool_calls",
                    message=dict(
                        tool_calls=[
                            dict(
                                type="function",
                                function=dict(
                                    name=decision["name"],
                                    arguments=json.dumps(decision["arguments"]),
                                ),
                            )
                        ]
                    ),
                )
            ],
        )
        if fault == "usage_missing":
            response.pop("usage")
        if fault == "protocol":
            response["choices"] = []
        if fault == "usage_over_reservation":
            response["usage"]["prompt_tokens"] = 1000000
        if fault == "auth":
            return httpx.Response(401, json={"error": "synthetic"})
        return httpx.Response(200, json=response)

    return httpx.MockTransport(send), seen


def test_local_failure_skips_conversation_and_continues_independent_sessions(isolated, tmp_path):
    transport, seen = mechanical_transport(local_failure=True)
    result = driver.run(tmp_path / "independent", isolated, transport)
    assert (
        result["completed_turns"],
        result["failed_turns"],
        result["missing_result_turns"],
    ) == (11, 1, 4)
    assert (
        result["stops"][0]["action"] == "STOP_SESSION"
        and result["stops"][0]["error_code"] == "TUTOR_FINISH_FORMAT_INVALID"
    )
    rows = jsonl(tmp_path / "independent/turns.jsonl")
    assert all(r["status"] == "MISSING" for r in rows[1:5])
    firsts = [b for b in seen if not b["observations"] and "Use only the supplied unit" in b["learner_text"]]
    assert len(firsts) == 4 and all(not b["history"] and not b["summary"] for b in firsts)
    assert not result["ledger"]["pending"] and not result["ledger"]["blocked"]
    save_result(
        "independent-sessions.json",
        dict(result=result, rows=rows, first_session_contexts=firsts),
    )


@pytest.mark.parametrize("fault", ["usage_missing", "protocol", "timeout", "auth", "usage_over_reservation"])
def test_global_failure_never_continues_or_retries(isolated, tmp_path, fault):
    transport, seen = mechanical_transport(fault=fault)
    result = driver.run(tmp_path / "global", isolated, transport)
    assert len(seen) == 1
    assert (
        result["completed_turns"],
        result["failed_turns"],
        result["missing_result_turns"],
    ) == (0, 1, 15)
    assert result["stops"][0]["action"] == "STOP_ALL"
    events = jsonl(tmp_path / "global/ledger.jsonl")
    assert len(events) == 2 and events[-1]["charged_nano_usd"] >= events[0]["reserved_nano_usd"]
    if fault == "usage_missing":
        assert events[-1]["usage"] is None
    save_result(f"global-{fault}.json", dict(result=result, events=events))


@pytest.mark.parametrize("cap,money,expected_sends", [(1, 700000000, 1), (80, 1, 0)])
def test_call_and_money_caps_stop_before_extra_send(isolated, tmp_path, cap, money, expected_sends):
    transport, seen = mechanical_transport()
    result = driver.run(tmp_path / "cap", isolated, transport, max_calls=cap, max_nano_usd=money)
    assert len(seen) == expected_sends and result["ledger"]["calls"] == expected_sends
    assert result["failed_turns"] == 1 and result["missing_result_turns"] == 15
    assert result["ledger"]["blocked"] == "REAL_EVAL_BUDGET_EXHAUSTED"


@pytest.mark.parametrize(
    "change",
    [
        dict(blocked="DIVERGENT"),
        dict(pending=1),
        dict(calls=80),
        dict(nano_usd=700000000),
        dict(calls=None),
    ],
)
def test_unsafe_accounting_overrides_local_failure(change):
    state = dict(blocked=None, pending=0, calls=1, nano_usd=100)
    state.update(change)
    turn = dict(status="failed", error_code="TUTOR_REPAIR_BUDGET_UNAVAILABLE")
    assert driver.disposition(turn, state, contract.bridge.legacy.TutorPolicy(max_calls=80)) == "STOP_ALL"
    assert driver.disposition(turn, None, contract.bridge.legacy.TutorPolicy(max_calls=80)) == "STOP_ALL"


def test_divergent_ledger_is_preserved_and_marks_unknown_not_zero(isolated, tmp_path):
    transport, seen = mechanical_transport()
    original = transport.handler

    def tamper(request):
        response = original(request)
        with (tmp_path / "divergent/ledger.jsonl").open("a") as output:
            output.write('{"synthetic":"divergence"}\n')
        return response

    transport.handler = tamper
    result = driver.run(tmp_path / "divergent", isolated, transport)
    assert len(seen) == 1 and result["ledger"] is None
    assert result["failed_turns"] == 1 and result["missing_result_turns"] == 15
    assert any(s["error_code"] == "OFFLINE_ACCOUNTING_UNKNOWN" for s in result["stops"])


def test_driver_rejects_non_mock_before_any_state(tmp_path):
    with pytest.raises(ValueError, match="MOCK_TRANSPORT"):
        driver.run(tmp_path / "not-created", "unused", object())
    assert not (tmp_path / "not-created").exists()


def test_v12_retained_prefix_and_one_explicit_synthetic_repair(isolated, tmp_path):
    retained = frames(RAW)
    prefix = RetainedTransport(retained)
    repairs = []

    def send(request):
        if len(prefix.sent) < 17:
            return prefix.send_retained(request)
        assert not repairs
        payload = json.loads(request.content)
        body = json.loads(payload["messages"][-1]["content"])
        assert len(body["evidence"]) == 4 and body["search_calls_remaining"] == 0
        assert [s["function"]["name"] for s in payload["tools"]] == ["finish_tutor_turn"]
        repairs.append(payload)
        fixture = FinishFixture().decide(payload["messages"], payload["tools"], 20)
        return httpx.Response(
            200,
            json={
                "usage": fixture["usage"],
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": fixture["name"],
                                        "arguments": json.dumps(fixture["arguments"]),
                                    },
                                }
                            ]
                        },
                    }
                ],
            },
        )

    result = driver.run(tmp_path / "prefix", isolated, httpx.MockTransport(send), max_calls=18)
    assert len(prefix.sent) == 17 and len(repairs) == 1
    assert (result["completed_turns"], result["failed_turns"], result["missing_result_turns"]) == (7, 0, 9)
    assert result["stops"][-1]["action"] == "STOP_ALL"  # Explicit Mock-only cap, no paid continuation.
    rows = jsonl(tmp_path / "prefix/turns.jsonl")
    old = jsonl(RAW / "fresh-real16/turns.jsonl")
    assert all(rows[i]["answer"] == old[i]["answer"] for i in range(6))
    with psycopg.connect(isolated) as conn:
        stored = conn.execute(
            "SELECT reserved_tokens,model_calls FROM tutor_turn WHERE turn_id=%s", (rows[6]["turn_id"],)
        ).fetchone()
        assert stored == (61475, 4)
    save_result(
        "v12-prefix-and-synthetic-repair.json",
        dict(
            result=result,
            strict_original_wire_matches=17,
            original_completed_answers_unchanged=6,
            synthetic_repair_requests=1,
            repaired_turn_reservation_byte_proxy=61475,
            real_quality="NOT_RUN",
            actual_supplier_cost="NOT_RUN",
            repair_request=repairs[0],
        ),
    )


def test_exact_global_cap_on_last_planned_response_is_complete(isolated, tmp_path):
    transport, seen = mechanical_transport()
    result = driver.run(tmp_path / "exact-final-cap", isolated, transport, max_calls=32)
    assert len(seen) == result["ledger"]["calls"] == 32
    assert result["completed_turns"] == 16
    assert result["failed_turns"] == result["missing_result_turns"] == 0
    assert result["mechanics_status"] == "COMPLETE"
    assert result["real_quality"] == "NOT_RUN"
