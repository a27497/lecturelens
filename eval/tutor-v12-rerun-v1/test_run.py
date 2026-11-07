"""Frozen v12 entry, Mock execution and retained-response citation/budget checks."""

import copy
import hashlib
import json
import os
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rerun
from lecturelens_real_eval.tutor.runtime import MockTutor
from replay_support import RetainedTransport, frames, jsonl, read

C = rerun.contract
RAW = C.ROOT / ".data/tutor-fresh-live-20261107"


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    original = os.environ.get

    def get(key, *args):
        if key in {"AGENT_LLM_API_KEY", "DEEPSEEK_API_KEY", "OPENAI_API_KEY"}:
            pytest.fail("No credentials may be read in no-cost preflight")
        return original(key, *args)

    monkeypatch.setattr(os.environ, "get", get)
    monkeypatch.setattr(httpx, "HTTPTransport", lambda **kw: pytest.fail("Real transport forbidden"))


@pytest.fixture
def isolated():
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    schema = "v12_entry_" + uuid.uuid4().hex
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    yield make_conninfo(dsn, options=f"-csearch_path={schema},public")
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def options(tmp_path, *extra):
    return rerun.parser().parse_args(
        [
            "--agent",
            C.candidate.CANDIDATE,
            "--model",
            "deepseek-flash",
            "--output",
            str(tmp_path / "batch"),
            *extra,
        ]
    )


def mock_args(tmp_path, *extra):
    return options(tmp_path, "--mock", "--max-calls", "80", "--max-usd", "0.70", *extra)


def save(name, value):
    output = Path(os.environ["V12_ENTRY_CHECK_OUTPUT"])
    output.mkdir(parents=True, exist_ok=True)
    with (output / name).open("x") as f:
        json.dump(value, f, indent=2, default=str)
        f.write("\n")


def audit(output, dsn, expected_calls):
    rows = jsonl(output / "turns.jsonl")
    calls = jsonl(output / "calls.jsonl") if (output / "calls.jsonl").exists() else []
    events = jsonl(output / "ledger.jsonl")
    reserved = {e["call_id"]: e for e in events if e["state"] == "reserved"}
    wires = jsonl(output / "wire-events.jsonl") if (output / "wire-events.jsonl").exists() else []
    assert len(wires) == expected_calls
    assert len(rows) == 16 and len({r["turn_key"] for r in rows}) == 16
    with psycopg.connect(dsn) as conn:
        pg = [r[0] for r in conn.execute("SELECT record FROM p8_tutor_real_event ORDER BY sequence")]
        assert pg == events
        for r in rows:
            if r.get("turn_id"):
                stored = conn.execute(
                    "SELECT status,answer,model_calls,reserved_tokens,checkpoint FROM tutor_turn WHERE turn_id=%s",
                    (r["turn_id"],),
                ).fetchone()
                assert stored == (
                    r["status"],
                    r["answer"],
                    r["model_calls"],
                    r["reserved_tokens"],
                    r["checkpoint"],
                )
    for i, w in enumerate(wires, 1):
        raw = (output / f"wire/{i:03d}-request.json").read_bytes()
        h = hashlib.sha256(raw).hexdigest()
        assert h == w["wire_sha256"]
        call = next(c for c in calls if c.get("request_sha256") == h)
        assert h == reserved[call["ledger_call_id"]]["wire_sha256"]
        req = json.loads(raw)
        assert req["model"] == "deepseek-flash" and req["temperature"] == 0
        assert req["thinking"] == {"type": "disabled"} and req["max_tokens"] == 1200
        assert {s["function"]["name"] for s in req["tools"]} <= {"search_tutor_evidence", "finish_tutor_turn"}
        body = json.loads(req["messages"][-1]["content"])
        assert set(body) == {
            "learner_text",
            "socratic",
            "summary",
            "history",
            "evidence",
            "observations",
            "search_calls_remaining",
            "evaluation_required",
        }
    save(
        output.parent.name + "-" + output.name + "-reconciliation.json",
        dict(
            summary=read(output / "summary.json"),
            pg_events_equal=len(events),
            wire_hashes_equal=len(wires),
            rows=rows,
        ),
    )


def test_prepare_has_no_side_effects_or_fallback(tmp_path):
    with patch.object(rerun.bridge.legacy, "Ledger", side_effect=AssertionError("DB forbidden")):
        result = rerun.run(options(tmp_path))
    assert result["candidate"] == C.candidate.CANDIDATE and result["candidate_sha256"] == C.CANDIDATE_SHA
    assert result["normal_requests"] == 32 and result["maximum_requests"] == 80
    assert result["max_usd"] == "NEW_USER_AUTHORIZATION_REQUIRED" and not (tmp_path / "batch").exists()


@pytest.mark.parametrize(
    "field,value",
    [
        ("agent", "p8-tutor-grounded-v11-development"),
        ("model", "other"),
        ("reviewer", "on"),
        ("concurrency", 2),
        ("max_calls", 81),
        ("max_calls", True),
        ("max_usd", "10"),
        ("max_usd", "0"),
        ("max_usd", "NaN"),
        ("max_usd", "0.700000001"),
    ],
)
def test_rejects_settings_and_old_spending_amount_before_db(tmp_path, field, value):
    args = mock_args(tmp_path)
    setattr(args, field, value)
    with patch.object(rerun.bridge.legacy, "Ledger", side_effect=AssertionError("DB forbidden")):
        with pytest.raises((ValueError, rerun.bridge.legacy.EvalError)):
            rerun.run(args)
    assert not (tmp_path / "batch").exists()


@pytest.mark.parametrize("name", ["run-plan.json", "protocol.json", "adapter-lock.json", "rerun.py"])
def test_hash_or_missing_input_rejected_before_db(tmp_path, monkeypatch, name):
    folder = tmp_path / "contract"
    folder.mkdir()
    for p in C.HERE.iterdir():
        if p.is_file():
            (folder / p.name).write_bytes(p.read_bytes())
    (folder / name).write_text("{}")
    monkeypatch.setattr(C, "HERE", folder)
    with patch.object(rerun.bridge.legacy, "Ledger", side_effect=AssertionError("DB forbidden")):
        with pytest.raises((ValueError, KeyError)):
            rerun.run(mock_args(tmp_path))


def test_absent_data_and_wrong_candidate_fail_before_transport(tmp_path, monkeypatch):
    with patch.object(C.candidate, "verify_candidate", return_value=C.candidate.PARENT):
        with pytest.raises(ValueError, match="IDENTITY"):
            rerun.run(mock_args(tmp_path))
    real_digest = C.data.digest

    def absent(p):
        if str(p).endswith("/development.json"):
            raise FileNotFoundError("missing frozen data")
        return real_digest(p)

    monkeypatch.setattr(C.data, "digest", absent)
    with pytest.raises(FileNotFoundError):
        rerun.run(mock_args(tmp_path))


def test_live_fence_and_new_ack_required_without_credential_lookup(tmp_path, monkeypatch):
    a = options(tmp_path, "--live", "--max-calls", "80", "--max-usd", "0.70")
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    with pytest.raises(ValueError, match="OFFLINE_FENCE"):
        rerun.preflight(a)
    monkeypatch.delenv("LECTURELENS_PREFLIGHT_GUARDED")
    with pytest.raises(ValueError, match="NEW_AUTHORIZATION"):
        rerun.preflight(a)
    a.ack_new_batch_authorization = True
    a.ack_ledger_not_billing_cap = True
    price = copy.deepcopy(C.data.read(rerun.bridge.repair_run.PRICING))
    price["verified_on"] = datetime.now(timezone.utc).date().isoformat()
    p = tmp_path / "synthetic-pricing.json"
    p.write_text(json.dumps(price))
    a.pricing = str(p)
    with patch.object(rerun.bridge.legacy, "Ledger", side_effect=AssertionError("DB forbidden")):
        assert rerun.preflight(a)[-1].live is True  # Preflight only, no sender/transport/DB.
    price["verified_on"] = "2000-01-01"
    p.write_text(json.dumps(price))
    with pytest.raises(ValueError, match="PRICING"):
        rerun.preflight(a)


def test_full16_default_mock_and_zero_reviewer(isolated, tmp_path):
    a = mock_args(tmp_path)
    s = rerun.run(a, dsn=isolated)
    assert (s["completed"], s["failed"], s["skipped"], s["missing"]) == (16, 0, 0, 0)
    assert s["reviewer_calls"] == 0 and s["wire_requests"] == 32 and s["mechanics_status"] == "COMPLETE"
    assert s["quality_status"] == "NOT_RUN" and s["comparison"]["completed_answer_denominator"] == 16
    audit(Path(a.output), isolated, 32)
    with pytest.raises(FileExistsError):
        rerun.run(a, dsn=isolated)


def transport(fault=None):
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
            fault == "local"
            and "In the Slicing Strings exercise" in body["learner_text"]
            and body["observations"]
        ):
            decision = dict(
                name="finish_tutor_turn",
                arguments=dict(
                    outcome="answered", text="X" * 1601 + f" [{body['evidence'][0]['evidence_id']}]"
                ),
            )
        if fault == "foreign" and body["observations"]:
            decision = dict(
                name="finish_tutor_turn",
                arguments=dict(outcome="answered", text="Unknown source [" + "f" * 64 + "]"),
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
                                    name=decision["name"], arguments=json.dumps(decision["arguments"])
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
        if fault == "anomaly":
            response["usage"]["total_tokens"] = 999
        if fault == "auth":
            return httpx.Response(401, json={})
        if fault == "model_unavailable":
            return httpx.Response(404, json={})
        return httpx.Response(200, json=response)

    return httpx.MockTransport(send), seen


def test_local_failure_skips_dependencies_and_closes_session(isolated, tmp_path):
    t, seen = transport("local")
    a = mock_args(tmp_path)
    a.output = str(tmp_path / "local")
    s = rerun.run(a, dsn=isolated, transport=t)
    assert (s["completed"], s["failed"], s["skipped"], s["missing"]) == (11, 1, 4, 0)
    rows = jsonl(Path(a.output) / "turns.jsonl")
    assert (
        rows[1]["skip_code"] == rows[2]["skip_code"] == rows[3]["skip_code"] == "DEPENDENCY_FAILED_OR_SKIPPED"
    )
    assert rows[4]["skip_code"] == "SESSION_CLOSED_AFTER_LOCAL_FAILURE"
    assert (
        rows[2]["blocked_by"] == ["fresh-python-tail:2"] and rows[2]["root_failure"] == "fresh-python-tail:1"
    )
    firsts = [
        b
        for b in seen
        if not b["observations"] and b["learner_text"].startswith("Use only the supplied unit")
    ]
    assert len(firsts) == 4 and all(not b["history"] and not b["summary"] for b in firsts)
    assert (
        s["comparison"]["scheduled_task_denominator"] == 16
        and s["comparison"]["completed_answer_denominator"] == 11
    )
    audit(Path(a.output), isolated, len(seen))


@pytest.mark.parametrize(
    "fault,sends",
    [
        ("usage_missing", 1),
        ("protocol", 1),
        ("timeout", 1),
        ("auth", 1),
        ("model_unavailable", 1),
        ("anomaly", 1),
        ("foreign", 2),
    ],
)
def test_safety_failure_stops_all_with_no_retry(isolated, tmp_path, fault, sends):
    t, seen = transport(fault)
    a = mock_args(tmp_path)
    a.output = str(tmp_path / fault)
    s = rerun.run(a, dsn=isolated, transport=t)
    assert len(seen) == sends and s["wire_requests"] == sends
    assert (s["completed"], s["failed"], s["skipped"], s["missing"]) == (0, 1, 0, 15)
    assert s["stops"][0]["action"] == "STOP_ALL"
    if fault == "anomaly":
        assert s["ledger"]["blocked"] == "RERUN_USAGE_METADATA_INCONSISTENT"
    audit(Path(a.output), isolated, sends)


@pytest.mark.parametrize(
    "cap,money,sends,completed", [(1, "0.70", 1, 0), (80, "0.000000001", 0, 0), (32, "0.70", 32, 16)]
)
def test_global_caps_include_exact_last_response(isolated, tmp_path, cap, money, sends, completed):
    a = mock_args(tmp_path)
    a.max_calls = cap
    a.max_usd = money
    s = rerun.run(a, dsn=isolated)
    assert s["wire_requests"] == sends and s["ledger"]["calls"] == sends and s["completed"] == completed
    assert s["missing"] == (0 if completed else 15)
    assert s["mechanics_status"] == ("COMPLETE" if completed else "INCOMPLETE")
    audit(Path(a.output), isolated, sends)


@pytest.mark.parametrize(
    "change", [dict(pending=1), dict(blocked=""), dict(blocked="BUDGET"), dict(nano_usd=-1), dict(calls=None)]
)
def test_accounting_dominates_local_failure(change):
    state = dict(calls=1, nano_usd=10, pending=0, blocked=None)
    state.update(change)
    protocol = C.verify()[-1]
    policy = rerun.bridge.legacy.TutorPolicy(max_calls=80)
    turn = dict(status="failed", error_code="TUTOR_REPAIR_BUDGET_UNAVAILABLE", calls=[])
    assert rerun.classify(turn, state, policy, protocol)[0] == "STOP_ALL"
    turn["calls"] = [dict(status="FAILED", anomalies=[])]
    assert (
        rerun.classify(turn, dict(calls=1, nano_usd=10, pending=0, blocked=None), policy, protocol)[0]
        == "STOP_ALL"
    )


def test_unknown_runtime_and_authority_failures_are_global():
    protocol = C.verify()[-1]
    policy = rerun.bridge.legacy.TutorPolicy(max_calls=80)
    state = dict(calls=1, nano_usd=10, pending=0, blocked=None)
    for code in (
        "NEW_ERROR",
        "TUTOR_CITATION_MISMATCH",
        "TUTOR_UNKNOWN_MODEL_OUTCOME",
        "TUTOR_CANCELLED",
        "COURSE_UNAVAILABLE_OR_CHANGED",
        "REAL_EVAL_BUDGET_EXHAUSTED",
    ):
        assert (
            rerun.classify(dict(status="failed", error_code=code, calls=[]), state, policy, protocol)[0]
            == "STOP_ALL"
        )


def test_original_prefix_then_repair_keeps_citation_identity(isolated, tmp_path):
    prefix = RetainedTransport(frames(RAW))
    repairs = []

    def send(request):
        if len(prefix.sent) < 17:
            return prefix.send_retained(request)
        assert not repairs
        payload = json.loads(request.content)
        body = json.loads(payload["messages"][-1]["content"])
        repairs.append(payload)
        keep = body["observations"][-1]["keep_ids"]
        assert [e["evidence_id"] for e in body["evidence"]] == keep and len(keep) == 4
        return httpx.Response(
            200,
            json=dict(
                usage=dict(prompt_tokens=10, completion_tokens=10),
                choices=[
                    dict(
                        finish_reason="tool_calls",
                        message=dict(
                            tool_calls=[
                                dict(
                                    type="function",
                                    function=dict(
                                        name="finish_tutor_turn",
                                        arguments=json.dumps(
                                            dict(
                                                outcome="answered",
                                                text=f"Separate comments field [{keep[0]}]",
                                            )
                                        ),
                                    ),
                                )
                            ]
                        ),
                    )
                ],
            ),
        )

    a = mock_args(tmp_path)
    a.max_calls = 18
    a.output = str(tmp_path / "prefix")
    s = rerun.run(a, dsn=isolated, transport=httpx.MockTransport(send))
    assert (s["completed"], s["failed"], s["skipped"], s["missing"]) == (7, 0, 0, 9)
    rows = jsonl(Path(a.output) / "turns.jsonl")
    old = jsonl(RAW / "fresh-real16/turns.jsonl")
    assert len(prefix.sent) == 17 and all(rows[i]["answer"] == old[i]["answer"] for i in range(6))
    r = rows[6]
    assert r["reserved_tokens"] == 61475 and len(r["checkpoint"]["selected"]) == 12
    original_pg = next(iter(read(RAW / "postgres-run-snapshot.json").values()))
    original_failed = next(t for t in original_pg["turns"] if t["status"] == "failed")
    assert r["checkpoint"]["selected"] == original_failed["checkpoint"]["selected"]
    body = json.loads(repairs[0]["messages"][-1]["content"])
    scope = r["stored_scope"]
    authority = rerun.PassageAuthority(C.verify()[2])
    authority.register(scope, "carpentries-spreadsheets")
    sources = {e["evidence_id"]: e for e in authority.rows(scope)}
    for e in body["evidence"]:
        assert all(sources[e["evidence_id"]][k] == v for k, v in e.items())
    for e in r["citations"]:
        assert e == sources[e["evidence_id"]]
    assert r["citations"][0]["evidence_id"] == body["evidence"][0]["evidence_id"]
    audit(Path(a.output), isolated, 18)
    save(
        "repair-citation-mapping.json",
        dict(
            original_failure="TUTOR_REPAIR_BUDGET_UNAVAILABLE",
            new_total_byte_proxy=61475,
            repair_byte_proxy=16422,
            selected_ids=r["checkpoint"]["selected"],
            repair_evidence=body["evidence"],
            published_citations=r["citations"],
            real_quality="NOT_RUN",
        ),
    )


def test_adapter_identity_metadata_cannot_disagree(tmp_path, monkeypatch):
    folder = tmp_path / "wrong-lock"
    folder.mkdir()
    for p in C.HERE.iterdir():
        if p.is_file():
            (folder / p.name).write_bytes(p.read_bytes())
    lock = read(folder / "adapter-lock.json")
    lock["candidate_manifest_sha256"] = C.candidate.PARENT
    (folder / "adapter-lock.json").write_text(json.dumps(lock))
    monkeypatch.setattr(C, "HERE", folder)
    with pytest.raises(ValueError, match="ADAPTER_CHANGED"):
        rerun.run(mock_args(tmp_path))


@pytest.mark.parametrize(
    "code",
    [
        "TUTOR_REPAIR_BUDGET_UNAVAILABLE",
        "TUTOR_BUDGET_EXHAUSTED",
        "TUTOR_FINISH_FORMAT_INVALID",
        "TUTOR_SOCRATIC_CONTRACT",
        "TUTOR_DEADLINE",
    ],
)
def test_only_enumerated_local_errors_continue_independent_sessions(code):
    protocol = C.verify()[-1]
    state = dict(calls=2, nano_usd=100, pending=0, blocked=None)
    policy = rerun.bridge.legacy.TutorPolicy(max_calls=80)
    action, reason = rerun.classify(dict(status="failed", error_code=code, calls=[]), state, policy, protocol)
    assert action == "STOP_SESSION" and reason == code


def test_divergence_stops_without_resetting_or_repairing_ledger(isolated, tmp_path):
    inner, seen = transport()
    original = inner.handler
    a = mock_args(tmp_path)
    a.output = str(tmp_path / "divergent")

    def tamper(request):
        response = original(request)
        with (Path(a.output) / "ledger.jsonl").open("a") as output:
            output.write('{"synthetic":"mismatched ledger"}\n')
        return response

    inner.handler = tamper
    s = rerun.run(a, dsn=isolated, transport=inner)
    assert len(seen) == 1 and s["ledger"] is None
    assert (s["completed"], s["failed"], s["skipped"], s["missing"]) == (0, 1, 0, 15)
    assert any(e["reason"] == "ACCOUNTING_UNKNOWN" for e in s["stops"])
    assert jsonl(Path(a.output) / "ledger.jsonl")[-1] == {"synthetic": "mismatched ledger"}
    save("divergent-stop.json", s)


def test_reviewer_is_rejected_before_reservation(isolated, tmp_path):
    policy = rerun.bridge.legacy.TutorPolicy(candidate_sha256=C.CANDIDATE_SHA)
    ledger = rerun.bridge.legacy.Ledger(isolated, tmp_path / "review-ledger.jsonl", "review-disabled", policy)
    channel = rerun.RerunChannel(
        ledger,
        records=tmp_path / "review-calls.jsonl",
        transport=rerun.DecodedMetadataTransport(
            httpx.MockTransport(lambda request: pytest.fail("reviewer send forbidden"))
        ),
    )
    with pytest.raises(rerun.bridge.legacy.EvalError, match="REVIEWER_DISABLED"):
        channel.request([], [], purpose="review")
    assert not (tmp_path / "review-ledger.jsonl").exists()
    assert not (tmp_path / "review-calls.jsonl").exists()


def test_wire_persistence_failure_is_not_reported_as_dispatch(tmp_path):
    seen = []
    inner = httpx.MockTransport(lambda request: seen.append(request) or httpx.Response(200))
    wire = rerun.WireEvidence(inner, tmp_path, 1)
    with pytest.raises(FileNotFoundError):
        wire.handle_request(httpx.Request("POST", "https://api.deepseek.com/chat/completions", content=b"{}"))
    assert wire.count == 0 and not seen
