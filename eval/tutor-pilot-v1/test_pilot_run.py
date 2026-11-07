"""Bounded PG/Mock checks for the exact development pilot; never use real egress."""

import copy
import json
import os
import uuid
from pathlib import Path
from unittest.mock import patch

import httpx
import pilot_run as pilot
import psycopg
import pytest
from lecturelens_real_eval.tutor.python_runtime import SYSTEM
from psycopg import sql
from psycopg.conninfo import make_conninfo

PLAN = pilot.ROOT / "eval/tutor-python-contract-v1/development-pilot-v1.json"


class IsolatedDatabase(tuple):
    def __repr__(self):
        return "<isolated synthetic database fixture; connection details redacted>"


def args(tmp_path, *extra):
    return pilot.parser().parse_args(
        [
            "--plan",
            str(PLAN),
            "--agent",
            pilot.contract.CANDIDATE,
            "--model",
            pilot.MODEL,
            "--output",
            str(tmp_path / ("pilot-" + uuid.uuid4().hex[:12])),
            *extra,
        ]
    )


def forbid_credentials(monkeypatch):
    original = os.environ.get

    def guarded(key, *rest):
        if key in {"AGENT_LLM_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_API_KEY"}:
            pytest.fail("offline preparation/Mock must not read provider credentials")
        return original(key, *rest)

    monkeypatch.setattr(os.environ, "get", guarded)


def test_default_preparation_never_constructs_db_or_transport(tmp_path, monkeypatch):
    forbid_credentials(monkeypatch)
    with (
        patch.object(pilot.legacy, "Ledger", side_effect=AssertionError("DB forbidden")),
        patch.object(httpx, "HTTPTransport", side_effect=AssertionError("real transport forbidden")),
    ):
        result = pilot.run(args(tmp_path))
    assert result["mode"] == "PREPARE_ONLY_NO_EGRESS"
    assert result["maximum_requests"] == 40 and result["normal_requests"] == 16
    assert result["agent"] == pilot.contract.CANDIDATE
    assert result["reviewer"] == "DISABLED_NOT_RUN"
    assert result["counts"] == dict(courses=2, sessions=2, turns=8)
    assert result["real_quality"] == result["real_calls"] == result["real_cost"] == "NOT_RUN"


@pytest.mark.parametrize(
    "field,value",
    [
        ("agent", "v9"),
        ("model", "deepseek-v4-pro"),
        ("concurrency", 2),
        ("reviewer", "on"),
        ("max_calls", 0),
        ("max_calls", 41),
        ("max_usd", "0"),
        ("max_usd", "NaN"),
        ("max_usd", "0.700000001"),
        ("max_calls", None),
        ("max_usd", None),
    ],
)
def test_wrong_identity_or_unconfirmed_caps_never_start(tmp_path, monkeypatch, field, value):
    options = args(tmp_path, "--mock", "--max-calls", "40", "--max-usd", "0.70")
    setattr(options, field, value)
    forbid_credentials(monkeypatch)
    with (
        patch.object(pilot.legacy, "Ledger", side_effect=AssertionError("must reject first")),
        pytest.raises((ValueError, pilot.legacy.EvalError)),
    ):
        pilot.run(options)


def test_live_requires_explicit_flags_caps_and_current_pricing_without_key_lookup(tmp_path, monkeypatch):
    forbid_credentials(monkeypatch)
    monkeypatch.delenv("LECTURELENS_REAL_EVAL", raising=False)
    options = args(tmp_path, "--live", "--max-calls", "40", "--max-usd", "0.70")
    with pytest.raises(ValueError, match="PRICING_AND_CAP"):
        pilot.preflight(options)
    options.ack_ledger_not_billing_cap, options.pricing = True, str(pilot.PRICING)
    with pytest.raises(pilot.legacy.EvalError, match="SWITCH_REQUIRED"):
        pilot.preflight(options)
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    assert pilot.preflight(options)[-1].live  # Preflight only, never run()/send.
    for field, value in [
        ("verified_on", "2000-01-01"),
        ("currency", "CNY"),
        ("input_cache_miss_peak", "0.31"),
        ("requested_model", "unknown"),
    ]:
        pricing = copy.deepcopy(pilot.read(pilot.PRICING))
        pricing[field] = value
        changed = tmp_path / "pricing.json"
        changed.write_text(json.dumps(pricing))
        with pytest.raises(ValueError, match="PRICING_STALE_OR_INCOMPATIBLE"):
            pilot.check_pricing(changed)


def test_plan_and_adapter_drift_reject_before_db(tmp_path):
    options = args(tmp_path)
    changed = tmp_path / "plan.json"
    plan = pilot.read(PLAN)
    plan["sessions"][0]["dialogue_id"] = "sql-01"
    changed.write_text(json.dumps(plan))
    options.plan = str(changed)
    with pytest.raises(ValueError, match="MANIFEST_HASH_MISMATCH"):
        pilot.preflight(options)
    with (
        patch.object(pilot, "digest", return_value="0" * 64),
        pytest.raises(ValueError, match="ADAPTER_CHANGED"),
    ):
        pilot.verify_adapter()


@pytest.fixture
def isolated(tmp_path):
    dsn = make_conninfo(os.environ["AGENT_TEST_DATABASE_URL"], dbname="lecturelens_agent_acceptance")
    schema = "pilot_prep_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    yield IsolatedDatabase((make_conninfo(dsn, options=f"-csearch_path={schema},public"), tmp_path))
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def mock_run(isolated, monkeypatch, *, max_calls="40", max_usd="0.70", fault=None):
    dsn, folder = isolated
    options = args(folder, "--mock", "--max-calls", max_calls, "--max-usd", max_usd)
    _, scripts, _ = pilot.contract.load_plan(PLAN)
    inner = pilot.legacy.mock_transport(scripts, fault)
    sends = []

    def send(request):
        data = json.loads(request.content)
        assert data["model"] == pilot.MODEL and data["messages"][0]["content"] == SYSTEM
        assert all(t["function"]["name"] != "review_tutor_turn" for t in data["tools"])
        assert data["thinking"] == {"type": "disabled"} and data["max_tokens"] == 1200
        assert data["parallel_tool_calls"] is False and "Authorization" not in request.headers
        sends.append(data)
        return inner.handle_request(request)

    forbid_credentials(monkeypatch)
    with (
        patch.object(httpx, "HTTPTransport", side_effect=AssertionError("real transport forbidden")),
        patch.object(pilot.legacy, "review_turn", side_effect=AssertionError("reviewer forbidden")),
    ):
        result = pilot.run(options, dsn=dsn, transport=httpx.MockTransport(send))
    rows = [json.loads(line) for line in (Path(options.output) / "turns.jsonl").read_text().splitlines()]
    return result, sends, rows, options


def test_exact_scope_new_identity_sequential_global_budget_and_zero_reviewers(isolated, monkeypatch):
    result, sends, rows, options = mock_run(isolated, monkeypatch)
    assert result["mechanics_status"] == "COMPLETE" and len(sends) == 16
    assert [r["turn_key"] for r in rows] == pilot.read(PLAN)["turn_keys"]
    assert {r["course_id"] for r in rows} == {"carpentries-python", "carpentries-spreadsheets"}
    assert result["completed_turns"] == 8 and result["ledger_accounting"]["calls"] == 16
    assert result["reviewer_calls"] == 0 and result["reviewer"] == "DISABLED_NOT_RUN"
    assert all(r["review"] is None for r in rows)
    assert (
        result["quality_status"]
        == result["human_agreement_status"]
        == result["real_cost_status"]
        == "NOT_RUN"
    )
    with pytest.raises(FileExistsError):
        pilot.run(options, dsn=isolated[0])  # No restart/replay into an existing output.


@pytest.mark.parametrize("cap", [1, 8])
def test_global_call_cap_stops_without_review_or_continuing_other_session(isolated, monkeypatch, cap):
    result, sends, rows, _ = mock_run(isolated, monkeypatch, max_calls=str(cap))
    assert len(sends) == cap and result["ledger_accounting"]["calls"] == cap
    assert result["mechanics_status"] == "INCOMPLETE" and result["expected_turns"] == 8
    assert result["ledger_accounting"]["blocked"] == "REAL_EVAL_BUDGET_EXHAUSTED"
    assert result["missing_result_turns"] > 0
    later = [r for r in rows if r["course_id"] == "carpentries-spreadsheets"]
    assert not any(r["status"] == "completed" for r in later)
    # With cap=8 the next local turn records its pre-egress rejection; it is not a ninth send.
    assert [r["status"] for r in later] == (
        ["failed", "MISSING", "MISSING", "MISSING"] if cap == 8 else ["MISSING"] * 4
    )


def test_money_reservation_rejects_before_send_and_preserves_all_expected_turns(isolated, monkeypatch):
    result, sends, rows, _ = mock_run(isolated, monkeypatch, max_usd="0.000000001")
    assert sends == [] and result["ledger_accounting"]["calls"] == 0
    assert result["failed_turns"] == 1 and result["missing_result_turns"] == 7
    assert len(rows) == 8 and result["quality_status"] == "NOT_RUN"


@pytest.mark.parametrize("fault", ["timeout", "malformed"])
def test_transport_failure_or_missing_usage_is_not_retried_or_refunded(isolated, monkeypatch, fault):
    result, sends, rows, _ = mock_run(isolated, monkeypatch, fault=fault)
    assert len(sends) == 1 and result["ledger_accounting"]["calls"] == 1
    assert result["ledger_accounting"]["nano_usd"] > 0
    assert result["failed_turns"] == 1 and result["missing_result_turns"] == 7
    assert rows[0]["calls"][0]["status"] == "FAILED"


def test_disabled_review_route_and_pending_reservation_never_send(isolated):
    dsn, folder = isolated
    policy = pilot.legacy.TutorPolicy(max_calls=40)
    ledger = pilot.legacy.Ledger(dsn, folder / "guard.jsonl", "guard", policy)
    ledger.install()
    sends = []
    channel = pilot.TutorOnlyChannel(
        ledger,
        records=folder / "calls.jsonl",
        transport=pilot.legacy.MetadataTransport(httpx.MockTransport(lambda r: sends.append(r))),
    )
    with pytest.raises(pilot.legacy.EvalError, match="REVIEWER_DISABLED"):
        channel.request([], [], purpose="review")
    assert ledger.check()["calls"] == 0 and sends == []
    schemas = [{"type": "function", "function": {"name": "search_tutor_evidence", "parameters": {}}}]
    from lecturelens_real_eval.tutor_channel import encode

    raw = encode(dict(model=pilot.MODEL, tools=schemas))
    ledger.reserve(raw, 1200)  # Simulates crash after durable pre-egress reservation.
    with pytest.raises(pilot.legacy.EvalError, match="UNKNOWN_OUTCOME"):
        channel.request([{"role": "user", "content": "synthetic"}], schemas)
    assert ledger.check()["pending"] == 1 and sends == []


def test_five_call_per_turn_bound_includes_both_finish_repairs(isolated, monkeypatch):
    dsn, folder = isolated
    options = args(folder, "--mock", "--max-calls", "40", "--max-usd", "0.70")
    sends = []

    def send(request):
        body = json.loads(json.loads(request.content)["messages"][-1]["content"])
        n = len(body["observations"])
        if n < 2:
            name, arguments = "search_tutor_evidence", {"query": "the"}
        else:
            eid = body["evidence"][0]["evidence_id"]
            name = "finish_tutor_turn"
            arguments = dict(
                outcome="socratic_prompt" if n == 3 else "answered",
                text=("T" * 1601 if n == 2 else "A fixed fixture statement?") + f" [{eid}]",
            )
        sends.append(name)
        return httpx.Response(
            200,
            json={
                "model": "MOCK_NOT_A_VERSION",
                "usage": {"prompt_tokens": 120, "completion_tokens": 80},
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {"name": name, "arguments": json.dumps(arguments)},
                                }
                            ]
                        },
                    }
                ],
            },
        )

    forbid_credentials(monkeypatch)
    result = pilot.run(options, dsn=dsn, transport=httpx.MockTransport(send))
    assert result["mechanics_status"] == "COMPLETE", result
    assert len(sends) == result["ledger_accounting"]["calls"] == 40
    assert result["reviewer_calls"] == 0 and result["quality_status"] == "NOT_RUN"
