"""Real isolated PostgreSQL plus Fake Provider; no paid request is made."""

import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
import test_models
from acceptance_database import ledger_database
from acceptance_fixtures import Course, Wire, execute
from psycopg import sql
from psycopg.conninfo import conninfo_to_dict, make_conninfo

from lecturelens_agent.study.acceptance_cost import (
    DEVELOPMENT_AGENT,
    FROZEN_AGENT,
    INPUT_TOKEN_CEILING,
    MAX_BODY,
    MODEL,
    P7_AGENT,
    P9_AGENT,
    UPSTREAM,
    CostDenied,
    CostLedger,
    CostPolicy,
    verify_development_agent,
    verify_frozen_agent,
    verify_p7_agent,
    verify_p9_agent,
    worker_snapshot,
)
from lecturelens_agent.study.acceptance_egress import (
    AcceptanceProvider,
    CostGateway,
    serve_gateway,
)
from lecturelens_agent.study.call_journal import begin, complete
from lecturelens_agent.study.contracts import StudyCommand
from lecturelens_agent.study.provider import MockProvider
from lecturelens_agent.study.runtime import StudyRuntime
from lecturelens_agent.study.store import StudyStore

registry = test_models.registry


@pytest.fixture(scope="module")
def isolated_cost_database():
    if not os.environ.get("AGENT_TEST_DATABASE_URL"):
        pytest.skip("Real PostgreSQL required")
    with ledger_database() as dsn:
        yield dsn


@pytest.fixture(autouse=True)
def cost_database_environment(monkeypatch, isolated_cost_database):
    monkeypatch.setenv("AGENT_TEST_DATABASE_URL", isolated_cost_database)


@pytest.mark.parametrize("override", [{"hostaddr": "203.0.113.1"}, {"service": "untrusted-service"}])
def test_libpq_address_overrides_are_rejected_without_connecting(override):
    dsn = make_conninfo(host="127.0.0.1", port="25479", dbname="lecturelens_agent_test", **override)
    with pytest.raises(CostDenied, match="ISOLATED_DATABASE_REQUIRED"):
        CostLedger(dsn)


def test_inherited_pg_address_cannot_escape_the_isolated_database(monkeypatch):
    monkeypatch.setenv("PGHOSTADDR", "203.0.113.1")
    ledger = CostLedger(os.environ["AGENT_TEST_DATABASE_URL"])
    assert conninfo_to_dict(ledger.store.dsn)["hostaddr"] == "127.0.0.1"
    with ledger.store.connect() as conn:
        # Docker forwards the loopback listener to a bridge address. Verify
        # libpq's actual client destination, not the server-side NAT address.
        assert conn.info.hostaddr == "127.0.0.1"
        assert (
            conn.execute("SELECT current_database() AS name").fetchone()["name"] == "lecturelens_agent_test"
        )


@pytest.fixture
def gate(registry, request):
    reg, owner = registry
    store = StudyStore(reg.store.dsn, worker_snapshot)
    course = Course()
    runtime = StudyRuntime(store, course, MockProvider())
    runtime.initialize()
    scope = {"owner_id": owner, "course_id": "cost-" + uuid.uuid4().hex, "revision": 1}
    scope["session_id"] = store.command(
        StudyCommand(**scope, operation="CREATE_SESSION", request_key="session"), "real"
    )["session_id"]
    schema = "cost_" + uuid.uuid4().hex
    with store.connect() as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    dsn = make_conninfo(reg.store.dsn, options=f"-csearch_path={schema},public")
    now = datetime.now(timezone.utc)
    policy = CostPolicy(scope["session_id"], now.isoformat(), (now + timedelta(hours=1)).isoformat())
    policy = replace(policy, **getattr(request, "param", {}))
    ledger = CostLedger(dsn)
    ledger.install(policy)
    wire = Wire(store, scope)
    yield SimpleNamespace(
        store=store,
        course=course,
        runtime=runtime,
        scope=scope,
        wire=wire,
        ledger=ledger,
        policy=policy,
        dsn=dsn,
    )
    with store.connect() as conn:
        conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))


def started(gate):
    response = gate.wire.command("START", request_key="practice", goal="解释停止条件并出两道题")
    run_id = response["run"]["run_id"]
    gate.store.claim(run_id, "test-worker", 90)
    return gate.store.guard(run_id, "test-worker")


def journal(gate, run, key="first", *, purpose="decision", max_tokens=900, text="offline-private-input"):
    messages = [{"role": "user", "content": text}]
    schemas = [
        {"type": "function", "function": {"name": "search_course_evidence", "parameters": {"type": "object"}}}
    ]
    metadata = {"purpose": purpose}
    if purpose == "review":
        metadata["review_stage"] = "field_support_goals_v1" if max_tokens == 1200 else "field_support_v1"
    tokens = (
        len(json.dumps(messages, ensure_ascii=False).encode())
        + len(json.dumps(schemas).encode())
        + max_tokens
    )
    begin(
        gate.store,
        run["run_id"],
        "test-worker",
        key,
        tokens,
        metadata,
        {"messages": messages, "schemas": schemas},
    )
    body = {
        "model": MODEL,
        "messages": messages,
        "tools": schemas,
        "tool_choice": "required",
        "parallel_tool_calls": False,
        "temperature": 0.2,
        "max_tokens": max_tokens,
    }
    return json.dumps(body, ensure_ascii=False).encode()


def response(**changes):
    return {
        "model": MODEL,
        "usage": {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150,
            "prompt_cache_hit_tokens": 10,
            "prompt_cache_miss_tokens": 90,
        },
        **changes,
    }


def finish_journal(gate, run, key):
    complete(gate.store, run["run_id"], "test-worker", key, {}, {}, response={"usage": {}})


def wire_sender(gate):
    def send(packed, timeout):
        assert 0 < timeout <= 90
        assert json.loads(packed)["model"] == MODEL
        request = httpx.Request(
            "POST",
            UPSTREAM,
            content=packed,
            headers={"Authorization": "Bearer offline-only-key"},
            extensions={"timeout": {"read": timeout}},
        )
        return httpx.Response(200, json=gate.wire(request).json() | {"model": MODEL})

    return send


def test_frozen_module_manifest_detects_source_drift(tmp_path):
    import lecturelens_agent

    package = Path(lecturelens_agent.__file__).parent
    copied = tmp_path / "package"
    shutil.copytree(package, copied, ignore=shutil.ignore_patterns("__pycache__"))
    assert verify_development_agent(copied) == 63
    with pytest.raises(CostDenied, match="AGENT_IDENTITY_CHANGED"):
        verify_frozen_agent(copied)
    altered = copied / "study/provider.py"
    # Frozen artifacts are read-only. Only the disposable tampering sample may
    # become writable; the source being certified keeps its original mode.
    altered.chmod(altered.stat().st_mode | 0o200)
    with altered.open("a") as output:
        output.write("\n# different candidate\n")
    with pytest.raises(CostDenied, match="AGENT_IDENTITY_CHANGED"):
        verify_development_agent(copied)


def test_worker_can_only_hold_the_unspendable_placeholder(gate):
    run = started(gate)
    provider = AcceptanceProvider("http://127.0.0.1:39001", "only-a-local-capability").for_run(run)
    assert all(client.key == "only-a-local-capability" for client in provider.clients.values())
    run["model_config"]["review"]["credential"] = "unverified-provider-credential"
    with pytest.raises(CostDenied, match="WORKER_CREDENTIAL_NOT_ISOLATED"):
        AcceptanceProvider("http://127.0.0.1:39001", "local").for_run(run)


def test_cli_plan_is_read_only_and_fake_policy_cannot_activate(gate, tmp_path):
    from dataclasses import asdict

    root = Path(__file__).resolve().parents[2]
    command = [sys.executable, str(root / "scripts/eval/acceptance-cost-egress.py")]
    result = subprocess.run([*command, "plan"], capture_output=True, text=True, check=True, timeout=10)
    plan = json.loads(result.stdout)
    assert plan["provider_requests"] == 0 and plan["money_limit_implies_max_admitted_calls"] == 9
    assert plan["verified_development_modules"] == 63
    assert plan["historical_agent_candidate"] == FROZEN_AGENT
    assert plan["agent_candidate"] == DEVELOPMENT_AGENT
    policy_file = tmp_path / "fake-policy.json"
    policy_file.write_text(json.dumps(asdict(gate.policy)))
    endpoint = tmp_path / "must-not-exist.json"
    result = subprocess.run(
        [
            *command,
            "serve",
            "--policy-file",
            str(policy_file),
            "--credential-fd",
            "99",
            "--endpoint-file",
            str(endpoint),
        ],
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode != 0 and not endpoint.exists()
    assert gate.ledger.snapshot()["envelope"]["calls"] == 0


@pytest.mark.parametrize("gate", [{"max_calls": 1}], indirect=True)
def test_explicit_call_cap_is_enforced_independently_of_money(gate):
    run = started(gate)
    raw = journal(gate, run)
    gateway = CostGateway(gate.ledger, lambda *_: httpx.Response(200, json=response()))
    gateway.forward(run["run_id"], "decision", raw)
    finish_journal(gate, run, "first")
    raw = journal(gate, run, "second")
    with pytest.raises(CostDenied, match="COST_CALL_LIMIT"):
        gateway.forward(run["run_id"], "decision", raw)
    assert gate.ledger.snapshot()["envelope"]["calls"] == 1


@pytest.mark.parametrize("fault", ["cancel", "quality", "citation", "version", "budget"])
def test_cost_egress_keeps_existing_runtime_failure_fences(gate, fault):
    gate.wire.fault = fault
    local_key = secrets.token_urlsafe(32)
    with serve_gateway(CostGateway(gate.ledger, wire_sender(gate)), local_key) as url:
        gate.runtime.provider = AcceptanceProvider(url, local_key)
        response_start = gate.wire.command("START", request_key="practice", goal="解释停止条件并出两道题")
        if fault == "version":
            gate.course.valid = False
        if fault == "budget":
            with gate.store.connect() as conn:
                conn.execute(
                    "UPDATE study_run SET reserved_tokens=64000 WHERE run_id=%s",
                    (response_start["run"]["run_id"],),
                )
        execute(gate.runtime, gate.store, response_start)
    result = gate.wire.command("READ")
    assert result["artifact"] is None
    assert result["run"]["status"] in {"cancelled", "budget_exceeded", "failed"}
    assert gate.ledger.snapshot()["envelope"]["calls"] == len(gate.wire.requests)
    if fault in {"version", "budget"}:
        assert len(gate.wire.requests) == 0


@pytest.mark.parametrize("status", [200, 302, 429, 500])
def test_fake_http_failures_do_not_retry_or_follow_redirect(gate, status):
    sent = []

    def fake(packed, timeout):
        sent.append(packed)
        return httpx.Response(status, json=response(), headers={"Location": "https://other.invalid"})

    run = started(gate)
    raw = journal(gate, run)
    gateway = CostGateway(gate.ledger, fake)
    if status == 200:
        gateway.forward(run["run_id"], "decision", raw)
    else:
        with pytest.raises(CostDenied, match="UPSTREAM_OUTCOME_UNKNOWN"):
            gateway.forward(run["run_id"], "decision", raw)
        with pytest.raises(CostDenied, match="CAMPAIGN_STOPPED"):
            gateway.forward(run["run_id"], "decision", raw)
    assert len(sent) == 1


def test_local_auth_and_path_are_closed_without_any_charge(gate):
    run = started(gate)
    raw = journal(gate, run)
    token = secrets.token_urlsafe(32)
    with serve_gateway(CostGateway(gate.ledger, lambda *_: pytest.fail("no send")), token) as url:
        with httpx.Client(trust_env=False) as client:
            for path, auth in [
                (f"/runs/{run['run_id']}/decision/chat/completions", "invalid"),
                ("/models", token),
                ("/chat/completions", token),
            ]:
                result = client.post(url + path, content=raw, headers={"Authorization": "Bearer " + auth})
                assert result.status_code == 403
    assert gate.ledger.snapshot()["envelope"]["calls"] == 0


def test_campaign_cancellation_is_persistent_even_with_another_proxy(gate):
    run = started(gate)
    raw = journal(gate, run)
    gate.ledger.cancel()
    with pytest.raises(CostDenied, match="CAMPAIGN_STOPPED"):
        CostLedger(gate.dsn).admit(run["run_id"], "decision", raw)
    assert gate.ledger.snapshot()["envelope"]["calls"] == 0


def test_unknown_cost_record_blocks_another_journal_identity(gate):
    run = started(gate)
    raw = journal(gate, run)
    claim, _ = gate.ledger.admit(run["run_id"], "decision", raw)
    gate.ledger.dispatch(claim)
    # A disagreement with a different journal must not grant a new paid send.
    finish_journal(gate, run, "first")
    raw = journal(gate, run, "another")
    with pytest.raises(CostDenied, match="OUTCOME_PENDING_OR_UNKNOWN"):
        CostLedger(gate.dsn).admit(run["run_id"], "decision", raw)
    assert gate.ledger.snapshot()["envelope"]["calls"] == 1


@pytest.mark.parametrize("scope_fault", ["deadline", "other_session", "no_journal"])
def test_egress_requires_the_allowed_active_journal(gate, scope_fault):
    run = started(gate)
    raw = journal(gate, run)
    with gate.store.connect() as conn:
        if scope_fault == "deadline":
            conn.execute(
                "UPDATE study_run SET deadline=now()-interval '1 second' WHERE run_id=%s", (run["run_id"],)
            )
        elif scope_fault == "other_session":
            other = gate.store.command(
                StudyCommand(
                    owner_id=gate.scope["owner_id"],
                    course_id=gate.scope["course_id"],
                    revision=1,
                    operation="CREATE_SESSION",
                    request_key="another",
                ),
                "real",
            )["session_id"]
            conn.execute("UPDATE study_run SET session_id=%s WHERE run_id=%s", (other, run["run_id"]))
        else:
            conn.execute("DELETE FROM study_model_call WHERE run_id=%s", (run["run_id"],))
    with pytest.raises(CostDenied):
        CostGateway(gate.ledger, lambda *_: pytest.fail("no upstream send")).forward(
            run["run_id"], "decision", raw
        )
    assert gate.ledger.snapshot()["envelope"]["calls"] == 0


def test_exact_currency_boundary_and_independent_usage_journals(gate):
    run = started(gate)
    raw = journal(gate, run)
    claim, packed = gate.ledger.admit(run["run_id"], "decision", raw)
    assert json.loads(packed)["thinking"] == {"type": "disabled"}
    gate.ledger.dispatch(claim)
    gate.ledger.settle(claim, response())
    snapshot = gate.ledger.snapshot()
    row = snapshot["calls"][0]
    assert row["reserved_micro_cny"] == 2_104_352
    assert row["usage_peak_upper_micro_cny"] == 600
    assert row["provider_usage"]["prompt_cache_hit_tokens"] == 10
    assert row["provider_billed_micro_cny"] is None
    assert snapshot["envelope"]["reserved_micro_cny"] == 2_104_352
    assert "offline-private-input" not in json.dumps(snapshot, default=str)
    assert CostLedger(gate.dsn).snapshot() == snapshot
    with pytest.raises(CostDenied, match="DUPLICATE_CALL"):
        gate.ledger.admit(run["run_id"], "decision", raw)
    assert gate.ledger.snapshot()["envelope"]["calls"] == 1


@pytest.mark.parametrize("remaining,allowed", [(2_104_352, True), (2_104_351, False)])
def test_fee_boundary_never_releases_reservations(gate, remaining, allowed):
    # A pre-existing reservation can consume any part of the immutable envelope.
    with gate.ledger.store.connect() as conn:
        conn.execute("UPDATE acceptance_cost_envelope SET reserved_micro_cny=%s", (20_000_000 - remaining,))
    run = started(gate)
    raw = journal(gate, run)
    sent = []
    gateway = CostGateway(
        gate.ledger, lambda packed, timeout: sent.append(packed) or httpx.Response(200, json=response())
    )
    if allowed:
        gateway.forward(run["run_id"], "decision", raw)
        assert gate.ledger.snapshot()["envelope"]["reserved_micro_cny"] == 20_000_000
    else:
        with pytest.raises(CostDenied, match="BUDGET_INSUFFICIENT"):
            gateway.forward(run["run_id"], "decision", raw)
        assert not sent
        assert gate.ledger.snapshot()["calls"] == []


@pytest.mark.parametrize(
    "mutation,code",
    [
        ({"model": "deepseek-v4-pro"}, "REQUEST_NOT_ALLOWED"),
        ({"model": "unknown"}, "REQUEST_NOT_ALLOWED"),
        ({"max_tokens": 1201}, "REQUEST_NOT_ALLOWED"),
        ({"max_tokens": 1200}, "JOURNAL_INPUT_CHANGED"),
        ({"thinking": {"type": "enabled"}}, "REQUEST_NOT_ALLOWED"),
        ({"n": 2}, "REQUEST_NOT_ALLOWED"),
        ({"stream": True}, "REQUEST_NOT_ALLOWED"),
        ({"messages": [{"role": "user", "content": [{"type": "image_url"}]}]}, "REQUEST_NOT_ALLOWED"),
        ({"messages": [{"role": "user", "content": "x" * MAX_BODY}]}, "INPUT_LIMIT"),
        ({"tools": [{"type": "web_search"}]}, "REQUEST_NOT_ALLOWED"),
    ],
)
def test_unpriced_or_changed_payload_never_reaches_provider(gate, mutation, code):
    run = started(gate)
    raw = journal(gate, run)
    raw = json.dumps(json.loads(raw) | mutation).encode()
    with pytest.raises(CostDenied, match=code):
        CostGateway(gate.ledger, lambda *_: pytest.fail("upstream must not run")).forward(
            run["run_id"], "decision", raw
        )
    assert gate.ledger.snapshot()["calls"] == []


@pytest.mark.parametrize(
    "url,model",
    [
        ("https://api.deepseek.com.evil/v1", MODEL),
        ("http://api.deepseek.com", MODEL),
        ("https://api.deepseek.com/v1?anything=1", MODEL),
        ("https://api.deepseek.com/v1", "deepseek-v4-pro"),
    ],
)
def test_role_snapshots_reject_other_providers_and_review_models(gate, url, model):
    run = started(gate)
    run["model_config"]["review"].update(base_url=url, model=model)
    with pytest.raises(CostDenied, match="ROUTE_NOT_ALLOWED"):
        AcceptanceProvider("http://127.0.0.1:39001", "not-a-provider-key").for_run(run)


def test_expiry_restart_and_live_activation_cannot_reset_money(gate):
    gate.ledger.install(gate.policy)
    with pytest.raises(CostDenied, match="ALREADY_FROZEN"):
        CostLedger(gate.dsn).install(replace(gate.policy, budget_micro_cny=19_000_000))
    with pytest.raises(CostDenied):
        replace(gate.policy, mode="live", authorization_id="not-an-authorization").validate()
    for policy in [
        replace(gate.policy, max_calls=13),
        replace(gate.policy, budget_micro_cny=20_000_001),
        replace(gate.policy, expires_at=gate.policy.verified_at),
        replace(gate.policy, mode="live"),
    ]:
        with pytest.raises(CostDenied):
            policy.validate()


def test_concurrent_duplicate_claims_have_one_atomic_charge(gate):
    run = started(gate)
    raw = journal(gate, run)

    def reserve(_):
        try:
            return gate.ledger.admit(run["run_id"], "decision", raw)[0]
        except CostDenied as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(reserve, range(16)))
    assert sum(isinstance(outcome, dict) for outcome in outcomes) == 1
    assert outcomes.count("COST_DUPLICATE_CALL") == 15
    assert gate.ledger.snapshot()["envelope"]["calls"] == 1
    assert gate.ledger.snapshot()["envelope"]["reserved_micro_cny"] == 2_104_352


def test_call_limit_and_journal_error_disallow_paid_retry(gate):
    run = started(gate)
    raw = journal(gate, run)
    claim, _ = gate.ledger.admit(run["run_id"], "decision", raw)
    gate.ledger.dispatch(claim)
    gate.ledger.settle(claim, response())
    finish_journal(gate, run, "first")
    raw = journal(gate, run, "second")
    with gate.store.connect() as conn:
        gate.store._event(conn, run["run_id"], "protocol_retry_scheduled", {"retry": 1})
    with pytest.raises(CostDenied, match="RETRY_NOT_ALLOWED"):
        gate.ledger.admit(run["run_id"], "decision", raw)
    assert gate.ledger.snapshot()["envelope"]["calls"] == 1


def test_cancel_between_commit_and_wire_is_not_refunded(gate):
    run = started(gate)
    raw = journal(gate, run)
    claim, _ = gate.ledger.admit(run["run_id"], "decision", raw)
    gate.wire.command("CANCEL")
    with pytest.raises(CostDenied, match="CANCELLED_BEFORE_SEND"):
        gate.ledger.dispatch(claim)
    snapshot = gate.ledger.snapshot()
    assert snapshot["envelope"]["reserved_micro_cny"] == 2_104_352
    assert snapshot["envelope"]["blocked_code"] == "COST_CANCELLED_BEFORE_SEND"


@pytest.mark.parametrize(
    "data",
    [
        {},
        response(usage={}),
        response(model="different"),
        response(usage={"prompt_tokens": True, "completion_tokens": 1}),
        response(usage={"prompt_tokens": INPUT_TOKEN_CEILING + 1, "completion_tokens": 1}),
        response(usage={"prompt_tokens": 1, "completion_tokens": 901}),
    ],
)
def test_unknown_or_out_of_contract_bill_stops_campaign_without_refund(gate, data):
    run = started(gate)
    raw = journal(gate, run)
    sent = []
    gateway = CostGateway(
        gate.ledger, lambda packed, timeout: sent.append(packed) or httpx.Response(200, json=data)
    )
    with pytest.raises(CostDenied):
        gateway.forward(run["run_id"], "decision", raw)
    with pytest.raises(CostDenied, match="CAMPAIGN_STOPPED"):
        gateway.forward(run["run_id"], "decision", raw)
    assert len(sent) == 1
    assert gate.ledger.snapshot()["calls"][0]["state"] == "unknown"
    assert gate.ledger.snapshot()["envelope"]["reserved_micro_cny"] == 2_104_352


@pytest.mark.parametrize("fault", ["timeout", "connection", "exception", "invalid_json"])
def test_sender_faults_persist_unknown_and_block_new_requests(gate, fault):
    sent = []

    def sender(packed, timeout):
        sent.append(packed)
        if fault == "timeout":
            raise httpx.ReadTimeout("synthetic timeout")
        if fault == "connection":
            raise httpx.ConnectError("synthetic connection error")
        if fault == "exception":
            raise RuntimeError("synthetic exception")
        return httpx.Response(200, content=b"{invalid json")

    run = started(gate)
    raw = journal(gate, run)
    gateway = CostGateway(gate.ledger, sender)
    with pytest.raises(CostDenied):
        gateway.forward(run["run_id"], "decision", raw)
    before = gate.ledger.snapshot()
    assert before["envelope"]["blocked_code"]
    assert before["calls"][0]["state"] == "unknown"
    assert before["calls"][0]["provider_billed_micro_cny"] is None
    finish_journal(gate, run, "first")
    changed_key = journal(gate, run, "must-not-retry")
    with pytest.raises(CostDenied, match="CAMPAIGN_STOPPED"):
        CostGateway(CostLedger(gate.dsn), sender).forward(run["run_id"], "decision", changed_key)
    assert len(sent) == 1
    assert gate.ledger.snapshot()["calls"] == before["calls"]


def test_another_owner_run_cannot_spend_or_pollute_the_envelope(gate):
    allowed = started(gate)
    raw = journal(gate, allowed)
    other_scope = {"owner_id": gate.scope["owner_id"] + 1, "course_id": "other-course", "revision": 1}
    other_scope["session_id"] = gate.store.command(
        StudyCommand(**other_scope, operation="CREATE_SESSION", request_key="other"), "real"
    )["session_id"]
    try:
        other = gate.store.command(
            StudyCommand(**other_scope, operation="START", request_key="other", goal="other goal"), "real"
        )["run"]
        gate.store.claim(other["run_id"], "other-worker", 90)
        with pytest.raises(CostDenied, match="RUN_NOT_ACTIVE_OR_ALLOWED"):
            gate.ledger.admit(other["run_id"], "decision", raw)
        assert gate.ledger.snapshot()["envelope"]["calls"] == 0
        gate.ledger.admit(allowed["run_id"], "decision", raw)
        snapshot = gate.ledger.snapshot()
        assert snapshot["envelope"]["calls"] == 1
        assert {call["run_id"] for call in snapshot["calls"]} == {allowed["run_id"]}
        assert gate.store.guard(other["run_id"], "other-worker")["model_calls"] == 0
    finally:
        with gate.store.connect() as conn:
            conn.execute("DELETE FROM study_run WHERE session_id=%s", (other_scope["session_id"],))
            conn.execute("DELETE FROM study_session WHERE session_id=%s", (other_scope["session_id"],))


def test_main_initialization_does_not_install_expense_tables(gate):
    with gate.store.connect() as conn:
        assert (
            conn.execute("SELECT to_regclass('public.acceptance_cost_envelope') AS name").fetchone()["name"]
            is None
        )


def test_no_live_sender_or_authorization_mode_is_available(gate):
    import lecturelens_agent.study.acceptance_egress as egress

    assert not hasattr(egress, "OfficialSender")
    with pytest.raises(CostDenied):
        replace(gate.policy, mode="live", authorization_id="synthetic-not-authorized").validate()


@pytest.mark.parametrize("fault", ["429", "500", "missing_usage", "wrong_tool"])
def test_runtime_failure_or_protocol_retry_never_sends_a_second_fake_request(gate, fault):
    sender = wire_sender(gate)
    sent = []

    def fail(packed, timeout):
        sent.append(packed)
        if fault in {"429", "500"}:
            return httpx.Response(int(fault))
        data = sender(packed, timeout).json()
        if fault == "missing_usage":
            data.pop("usage")
        else:
            data["choices"][0]["message"]["tool_calls"][0]["function"]["name"] = "unoffered_tool"
        return httpx.Response(200, json=data)

    local_token = secrets.token_urlsafe(32)
    with serve_gateway(CostGateway(gate.ledger, fail), local_token) as url:
        gate.runtime.provider = AcceptanceProvider(url, local_token)
        response_run = gate.wire.command("START", request_key="failure", goal="解释停止条件并出两道题")
        run = execute(gate.runtime, gate.store, response_run)
    result = gate.wire.command("READ", run_id=run["run_id"])
    assert result["run"]["status"] == "failed"
    assert result["artifact"] is None
    assert len(sent) == len(gate.ledger.snapshot()["calls"]) == 1
    if fault == "wrong_tool":
        events = gate.wire.command("EVENTS", run_id=run["run_id"])["events"]
        assert any(event["event_type"] == "protocol_retry_scheduled" for event in events)


def test_real_loopback_read_timeout_leaves_an_unknown_unretriable_reservation(gate):
    import threading
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

    entered, release = threading.Event(), threading.Event()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            self.rfile.read(int(self.headers["Content-Length"]))
            entered.set()
            release.wait(5)

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    sent = []

    def sender(packed, timeout):
        sent.append(packed)
        with httpx.Client(timeout=httpx.Timeout(0.2, connect=2), trust_env=False) as client:
            return client.post(f"http://127.0.0.1:{server.server_port}", content=packed)

    try:
        run = started(gate)
        raw = journal(gate, run)
        with pytest.raises(CostDenied, match="OUTCOME_UNKNOWN"):
            CostGateway(gate.ledger, sender).forward(run["run_id"], "decision", raw)
        assert entered.wait(1)
        with pytest.raises(CostDenied, match="CAMPAIGN_STOPPED"):
            CostGateway(gate.ledger, sender).forward(run["run_id"], "decision", raw)
        assert len(sent) == 1
        assert gate.ledger.snapshot()["calls"][0]["state"] == "unknown"
    finally:
        release.set()
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)


def test_ci_test_database_forwarder_uses_only_the_explicit_test_pg(monkeypatch):
    import socket

    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    actual_port = int(conninfo_to_dict(dsn)["port"])
    if actual_port == 5432:
        pytest.fail("The cost database fixture must expose a ledger-compatible port")
    original = socket.create_connection
    targets = []

    def connect(address, *args, **kwargs):
        assert address == ("127.0.0.1", 5432)
        targets.append(address)
        return original(("127.0.0.1", actual_port), *args, **kwargs)

    monkeypatch.setattr(socket, "create_connection", connect)
    monkeypatch.setenv("AGENT_TEST_DATABASE_URL", make_conninfo(dsn, port=5432))
    with ledger_database() as forwarded:
        with StudyStore(forwarded).connect() as conn:
            assert (
                conn.execute("SELECT current_database() AS name").fetchone()["name"]
                == "lecturelens_agent_test"
            )

        def forbidden(*_args, **_kwargs):
            raise AssertionError("An existing forwarder must retain its own upstream connector")

        monkeypatch.setattr(socket, "create_connection", forbidden)
        with StudyStore(forwarded).connect() as conn:
            assert conn.execute("SELECT 1 AS n").fetchone()["n"] == 1
        assert len(targets) == 2
        alternate_targets = []

        def alternate_connect(address, *args, **kwargs):
            assert address == ("127.0.0.1", 5432)
            alternate_targets.append(address)
            return original(("127.0.0.1", actual_port), *args, **kwargs)

        monkeypatch.setattr(socket, "create_connection", alternate_connect)
        with ledger_database() as nested:
            with StudyStore(nested).connect() as conn:
                assert (
                    conn.execute("SELECT current_database() AS name").fetchone()["name"]
                    == "lecturelens_agent_test"
                )
        assert alternate_targets == [("127.0.0.1", 5432)]
    assert targets


@pytest.mark.parametrize("override", [{"hostaddr": "203.0.113.1"}, {"service": "forbidden-service"}])
def test_offline_runner_rejects_native_database_address_overrides(gate, tmp_path, override):
    root = Path(__file__).resolve().parents[2]
    env = dict(os.environ)
    env["AGENT_TEST_DATABASE_URL"] = make_conninfo(gate.dsn, **override)
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/eval/check-study-offline.py"),
            "--database-port",
            conninfo_to_dict(gate.dsn)["port"],
            "--network-records",
            str(tmp_path / "must-not-create"),
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode != 0
    assert not (tmp_path / "must-not-create").exists()


def test_offline_runner_strips_credentials_and_blocks_external_dns(gate, tmp_path):
    root = Path(__file__).resolve().parents[2]
    test = tmp_path / "test_fence.py"
    test.write_text(
        "import os, socket, pytest\n"
        "def test_isolated():\n"
        "    assert 'AGENT_LLM_API_KEY' not in os.environ\n"
        "    assert 'AWS_SECRET_ACCESS_KEY' not in os.environ\n"
        "    assert os.environ['LECTURELENS_PREFLIGHT_GUARDED'] == '1'\n"
        "    with pytest.raises(PermissionError):\n"
        "        socket.getaddrinfo('api.deepseek.com', 443)\n"
    )
    env = dict(os.environ)
    env.update(AGENT_LLM_API_KEY="synthetic-unspendable", AWS_SECRET_ACCESS_KEY="synthetic-unspendable")
    records = tmp_path / "network"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/eval/check-study-offline.py"),
            "--database-port",
            conninfo_to_dict(gate.dsn)["port"],
            "--network-records",
            str(records),
            "--",
            str(test),
            "-q",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout
    assert sum(json.loads(p.read_text())["denied_connections"] for p in records.glob("*.json")) == 1


@pytest.mark.parametrize("phase", ["reserved", "sent", "observed"])
def test_sigkill_recovery_cannot_resend_or_replenish(gate, phase, tmp_path):
    run = started(gate)
    raw = journal(gate, run)
    marker = tmp_path / "fake-paid-sends"
    code = """
import json,sys,signal
from pathlib import Path
from lecturelens_agent.study.acceptance_cost import CostLedger
data=json.loads(sys.stdin.readline()); ledger=CostLedger(data['dsn'])
claim,_=ledger.admit(data['run_id'],'decision',data['raw'].encode())
if data['phase']!='reserved':
    ledger.dispatch(claim); Path(data['marker']).write_text('one fake send')
if data['phase']=='observed':
    ledger.settle(claim,{'model':'deepseek-flash','usage':{'prompt_tokens':100,'completion_tokens':50}})
print(data['phase'],flush=True)
signal.pause()
"""
    child = subprocess.Popen(
        [sys.executable, "-c", code],
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        child.stdin.write(
            json.dumps(
                {
                    "dsn": gate.dsn,
                    "run_id": run["run_id"],
                    "raw": raw.decode(),
                    "phase": phase,
                    "marker": str(marker),
                }
            )
            + "\n"
        )
        child.stdin.flush()
        import select

        assert select.select([child.stdout], [], [], 10)[0], "owned child did not reach crash point"
        assert child.stdout.readline().strip() == phase
        os.kill(child.pid, signal.SIGKILL)
        child.communicate(timeout=10)
        assert child.returncode == -signal.SIGKILL
    finally:
        if child.poll() is None:
            child.kill()
            child.communicate(timeout=10)
    assert marker.exists() == (phase != "reserved")
    recovered = CostLedger(gate.dsn)
    recovered.install(gate.policy)
    with pytest.raises(CostDenied, match="DUPLICATE_CALL"):
        recovered.admit(run["run_id"], "decision", raw)
    assert recovered.snapshot()["envelope"]["reserved_micro_cny"] == 2_104_352
    assert recovered.snapshot()["envelope"]["calls"] == 1


@pytest.mark.parametrize("recover", [False, True])
@pytest.mark.parametrize("scoped", [False, True])
def test_cost_gated_frozen_generation_answer_feedback_persist(gate, monkeypatch, recover, scoped):
    monkeypatch.setenv("STUDY_FEEDBACK_ENABLED", "true")

    original = gate.store.save_tool
    interrupted = False

    def save(*args, **kwargs):
        nonlocal interrupted
        if recover and not interrupted and args[3] == "create_practice_set":
            interrupted = True
            raise SystemExit("after billed-and-journaled response, before artifact")
        return original(*args, **kwargs)

    monkeypatch.setattr(gate.store, "save_tool", save)
    local_key = secrets.token_urlsafe(32)
    with serve_gateway(CostGateway(gate.ledger, wire_sender(gate)), local_key) as url:
        gate.runtime.provider = AcceptanceProvider(url, local_key)
        frozen = (
            {
                "version": 1,
                "kind": "segments",
                "policy": "strict",
                "revision": 1,
                "evidence_ids": [item["evidence_id"] for item in gate.course.sources],
            }
            if scoped
            else None
        )
        started_response = gate.wire.command(
            "START", request_key="practice", goal="解释停止条件并出两道题", learning_scope=frozen
        )
        if recover:
            with pytest.raises(SystemExit):
                execute(gate.runtime, gate.store, started_response)
        run = execute(gate.runtime, gate.store, started_response)
        result = gate.wire.command("READ")
        assert result["run"]["status"] == "succeeded", result["run"]
        assert result["run"]["learning_scope"] == frozen
        assert len(result["artifact"]["questions"]) == 2
        assert 0 < result["run"]["reserved_tokens"] <= 64000
        artifact = result["artifact"]["artifact_id"]
        attempt = gate.wire.command(
            "SAVE_ATTEMPT",
            run_id=run["run_id"],
            artifact_id=artifact,
            question_index=1,
            request_key="answer",
            expected_version=0,
            answer_text="计数达到上限，应停止。",
        )["attempt"]
        feedback = gate.wire.command(
            "START_FEEDBACK",
            run_id=run["run_id"],
            artifact_id=artifact,
            question_index=1,
            attempt_id=attempt["attempt_id"],
            request_key="feedback",
        )
        feedback_run = execute(gate.runtime, gate.store, feedback)
        result_feedback = gate.wire.command("READ", run_id=feedback_run["run_id"])
        assert result_feedback["run"]["status"] == "succeeded", result_feedback["run"]
        assert result_feedback["run"]["learning_scope"] == frozen
        assert 0 < result_feedback["run"]["reserved_tokens"] <= 64000
    snapshot = gate.ledger.snapshot()
    assert len(gate.wire.requests) == snapshot["envelope"]["calls"] == 9
    assert snapshot["envelope"]["reserved_micro_cny"] == 18_941_568
    for detail in (result, result_feedback):
        recorded = [call for call in snapshot["calls"] if call["run_id"] == detail["run"]["run_id"]]
        assert len(recorded) == detail["run"]["model_calls"]
        assert {call["purpose"] for call in recorded} == {"decision", "review"}
        assert len({call["operation_key"] for call in recorded}) == len(recorded)
    assert sum(row["usage_peak_upper_micro_cny"] for row in snapshot["calls"]) == 5400
    assert all(
        row["state"] == "observed" and row["provider_billed_micro_cny"] is None for row in snapshot["calls"]
    )
    assert all(row["run_id"] in {run["run_id"], feedback_run["run_id"]} for row in snapshot["calls"])
    assert all(
        {role: item["model"] for role, item in row["model_selection"].items()}
        == {"decision": MODEL, "review": MODEL}
        for row in (result["run"], result_feedback["run"])
    )
    restored = StudyStore(gate.store.dsn, gate.store.model_resolver).command(
        StudyCommand(**gate.scope, operation="READ", run_id=feedback_run["run_id"]), "real"
    )
    assert restored["feedback"]["attempt_id"] == attempt["attempt_id"]
    print(
        "COST_GATE_OFFLINE_SMOKE",
        json.dumps(
            {
                "recovery": recover,
                "mock_requests": 9,
                "local_reserved_micro_cny": 18_941_568,
                "fake_usage_peak_upper_micro_cny": 5400,
                "paid_requests": 0,
            }
        ),
    )


@pytest.mark.parametrize("expiry_point", ["dispatch_validation", "gateway_boundary"])
def test_expiry_between_dispatch_validation_and_sender_never_sends(gate, monkeypatch, expiry_point):
    import lecturelens_agent.study.acceptance_cost as cost

    class Clock(datetime):
        current = datetime.now(timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz else cls.current.replace(tzinfo=None)

    run = started(gate)
    raw = journal(gate, run)
    monkeypatch.setattr(cost, "datetime", Clock)
    dispatch = gate.ledger.dispatch

    def expire_at_boundary(claim):
        if expiry_point == "dispatch_validation":
            active = gate.ledger._active

            def expire_after_validation(row):
                valid = active(row)
                if valid:
                    Clock.current += timedelta(seconds=120)
                return valid

            monkeypatch.setattr(gate.ledger, "_active", expire_after_validation)
        window = dispatch(claim)
        if expiry_point == "gateway_boundary":
            Clock.current += timedelta(seconds=120)
        return window

    monkeypatch.setattr(gate.ledger, "dispatch", expire_at_boundary)
    sent = []
    gateway = CostGateway(
        gate.ledger, lambda packed, timeout: sent.append(timeout) or httpx.Response(200, json=response())
    )
    try:
        with pytest.raises(CostDenied, match="DEADLINE_BEFORE_SEND"):
            gateway.forward(run["run_id"], "decision", raw)
    finally:
        print("DEADLINE_FAULT", expiry_point, "sender_timeouts", sent)
    assert sent == []
    snapshot = gate.ledger.snapshot()
    assert snapshot["envelope"]["reserved_micro_cny"] == 2_104_352
    assert snapshot["envelope"]["calls"] == 1
    assert snapshot["envelope"]["blocked_code"] == "COST_DEADLINE_BEFORE_SEND"
    assert snapshot["calls"][0]["state"] == "not_sent"
    with pytest.raises(CostDenied, match="CAMPAIGN_STOPPED"):
        CostGateway(CostLedger(gate.dsn), lambda *_: pytest.fail("no retry")).forward(
            run["run_id"], "decision", raw
        )


def test_monotonic_expiry_cannot_be_extended_by_wall_clock_rollback(gate, monkeypatch):
    import lecturelens_agent.study.acceptance_cost as cost

    class Clock(datetime):
        current = datetime.now(timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz else cls.current.replace(tzinfo=None)

    tick = [1000.0]
    monkeypatch.setattr(cost, "datetime", Clock)
    monkeypatch.setattr(cost, "time", SimpleNamespace(monotonic=lambda: tick[0]))
    run = started(gate)
    raw = journal(gate, run)
    dispatch = gate.ledger.dispatch

    def stall(claim):
        window = dispatch(claim)
        tick[0] += 120
        Clock.current -= timedelta(hours=1)
        return window

    monkeypatch.setattr(gate.ledger, "dispatch", stall)
    with pytest.raises(CostDenied, match="DEADLINE_BEFORE_SEND"):
        CostGateway(gate.ledger, lambda *_: pytest.fail("expired sender")).forward(
            run["run_id"], "decision", raw
        )
    assert gate.ledger.snapshot()["calls"][0]["state"] == "not_sent"


def test_dispatch_window_preserves_absolute_and_request_time_caps(monkeypatch):
    import lecturelens_agent.study.acceptance_cost as cost

    class Clock(datetime):
        current = datetime.now(timezone.utc)

        @classmethod
        def now(cls, tz=None):
            return cls.current if tz else cls.current.replace(tzinfo=None)

    tick = [1000.0]
    monkeypatch.setattr(cost, "datetime", Clock)
    monkeypatch.setattr(cost, "time", SimpleNamespace(monotonic=lambda: tick[0]))
    policy_end = Clock.current + timedelta(seconds=5)
    policy_window = cost.DispatchWindow.until(policy_end, 20)
    feedback_window = cost.DispatchWindow.until(Clock.current + timedelta(seconds=90), 20)
    assert policy_window.remaining() == 5
    assert feedback_window.remaining() == 20
    tick[0] += 6
    Clock.current += timedelta(seconds=6)
    assert policy_window.remaining() < 0
    assert feedback_window.remaining() == 14


def test_concurrent_dispatch_and_duplicate_settlement_cannot_reuse_a_charge(gate):
    run = started(gate)
    raw = journal(gate, run)
    claim, _ = gate.ledger.admit(run["run_id"], "decision", raw)

    def dispatch(_):
        try:
            return gate.ledger.dispatch(claim)
        except CostDenied as error:
            return error.code

    with ThreadPoolExecutor(max_workers=8) as pool:
        outcomes = list(pool.map(dispatch, range(16)))
    assert sum(not isinstance(value, str) for value in outcomes) == 1
    assert outcomes.count("COST_DUPLICATE_CALL") == 15
    gate.ledger.settle(claim, response())
    before = gate.ledger.snapshot()
    with pytest.raises(CostDenied, match="DUPLICATE_SETTLEMENT"):
        gate.ledger.settle(claim, response(usage={"prompt_tokens": 0, "completion_tokens": 0}))
    after = gate.ledger.snapshot()
    assert after["calls"] == before["calls"]
    assert after["envelope"]["calls"] == 1
    assert after["envelope"]["reserved_micro_cny"] == 2_104_352
    assert after["envelope"]["blocked_code"] == "COST_DUPLICATE_SETTLEMENT"
    finish_journal(gate, run, "first")
    changed = journal(gate, run, "no-new-charge")
    with pytest.raises(CostDenied, match="CAMPAIGN_STOPPED"):
        CostGateway(CostLedger(gate.dsn), lambda *_: pytest.fail("no send")).forward(
            run["run_id"], "decision", changed
        )


def test_sigkill_inside_sender_blocks_new_operation_and_keeps_unknown_cost(gate, tmp_path):
    run = started(gate)
    raw = journal(gate, run)
    marker = tmp_path / "sender-entered"
    code = """
import json,os,signal,sys
from pathlib import Path
from lecturelens_agent.study.acceptance_cost import CostLedger
from lecturelens_agent.study.acceptance_egress import CostGateway
data=json.loads(sys.stdin.readline())
def sender(*_):
    Path(data['marker']).write_text('synthetic sender entered, no network')
    os.kill(os.getpid(),signal.SIGKILL)
CostGateway(CostLedger(data['dsn']),sender).forward(data['run_id'],'decision',data['raw'].encode())
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=json.dumps(
            {"dsn": gate.dsn, "run_id": run["run_id"], "raw": raw.decode(), "marker": str(marker)}
        ),
        text=True,
        capture_output=True,
        timeout=10,
    )
    assert result.returncode == -signal.SIGKILL and marker.exists()
    before = gate.ledger.snapshot()
    assert before["calls"][0]["state"] == "sent"
    assert before["calls"][0]["provider_usage"] is None
    assert before["calls"][0]["provider_billed_micro_cny"] is None
    recovered = CostLedger(gate.dsn)
    recovered.install(gate.policy)
    with pytest.raises(CostDenied, match="DUPLICATE_CALL"):
        recovered.admit(run["run_id"], "decision", raw)
    finish_journal(gate, run, "first")
    changed = journal(gate, run, "different-operation-after-crash")
    with pytest.raises(CostDenied, match="OUTCOME_PENDING_OR_UNKNOWN"):
        recovered.admit(run["run_id"], "decision", changed)
    after = recovered.snapshot()
    assert after["calls"] == before["calls"]
    assert after["envelope"]["reserved_micro_cny"] == 2_104_352
    assert after["envelope"]["calls"] == 1


def test_guarded_runner_blocks_numeric_http_and_python_children_even_on_exit(gate, tmp_path):
    root = Path(__file__).resolve().parents[2]
    test = tmp_path / "test_network_review.py"
    test.write_text(
        """
import json, os, pathlib, signal, socket, subprocess, sys
import httpx, pytest

def test_no_external_traffic_or_inherited_secrets():
    for name in ['AGENT_LLM_API_KEY', 'DEEPSEEK_API_KEY', 'HTTPS_PROXY', 'HTTP_PROXY',
                 'ALL_PROXY', 'NO_PROXY', 'PGPASSWORD', 'PGSERVICE', 'PGHOSTADDR']:
        assert name not in os.environ
    with pytest.raises(PermissionError):
        socket.create_connection(('203.0.113.1',443),timeout=0.1)
    with pytest.raises(PermissionError):
        socket.create_connection(('127.0.0.1',5432),timeout=0.1)
    with pytest.raises(PermissionError):
        socket.getaddrinfo('api.deepseek.com',443)
    with httpx.Client(trust_env=False,timeout=0.1) as client:
        with pytest.raises(httpx.ConnectError) as error:
            client.get('http://203.0.113.1/')
        pending, seen, denied = [error.value], set(), False
        while pending:
            cause = pending.pop()
            if id(cause) in seen:
                continue
            seen.add(id(cause))
            denied |= isinstance(cause,PermissionError)
            pending.extend(item for item in (cause.__cause__,cause.__context__,*cause.args)
                           if isinstance(item,BaseException))
        assert denied
    probe = "import os,socket; assert os.environ['LECTURELENS_PREFLIGHT_GUARDED']=='1'; socket.create_connection(('203.0.113.1',443),timeout=0.1)"
    child = subprocess.run([sys.executable,'-c',probe],capture_output=True,text=True,timeout=5)
    assert child.returncode == 1 and 'PermissionError' in child.stderr
    records = pathlib.Path(os.environ['LECTURELENS_PREFLIGHT_NETWORK_RECORDS'])
    # Abrupt exits cannot flush atexit counters. Prove denial before the exit,
    # and retain that observability limit instead of treating absent logs as 0.
    for ending, expected in [("os._exit(23)",23),("os.kill(os.getpid(),signal.SIGKILL)",-signal.SIGKILL)]:
        code = "import os,signal,socket\\ntry: socket.create_connection(('203.0.113.1',443),timeout=0.1)\\nexcept PermissionError: print(os.getpid(),flush=True)\\nelse: raise AssertionError('unfenced child')\\n" + ending
        child = subprocess.run([sys.executable,'-c',code],capture_output=True,text=True,timeout=5)
        assert child.returncode == expected,child.stderr
        assert child.stdout.strip().isdigit()
        assert not (records/(child.stdout.strip()+'.json')).exists()
"""
    )
    env = dict(os.environ)
    env.update(
        {
            k: "synthetic-must-be-stripped"
            for k in (
                "AGENT_LLM_API_KEY",
                "DEEPSEEK_API_KEY",
                "HTTPS_PROXY",
                "HTTP_PROXY",
                "ALL_PROXY",
                "NO_PROXY",
                "PGPASSWORD",
                "PGSERVICE",
                "PGHOSTADDR",
            )
        }
    )
    records = tmp_path / "review-network"
    result = subprocess.run(
        [
            sys.executable,
            str(root / "scripts/eval/check-study-offline.py"),
            "--database-port",
            conninfo_to_dict(gate.dsn)["port"],
            "--network-records",
            str(records),
            "--",
            str(test),
            "-q",
        ],
        capture_output=True,
        text=True,
        env=env,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    assert sum(json.loads(p.read_text())["denied_connections"] for p in records.glob("*.json")) == 5


def test_review_read_extension_preserves_prior_frozen_manifest_identity():
    import lecturelens_agent

    package = Path(lecturelens_agent.__file__).parent
    prior = json.loads((Path(__file__).parent / "fixtures/acceptance_agent_702b2f8.json").read_text())
    frozen = json.loads((package / "study/acceptance_agent_manifest.json").read_text())
    assert frozen == prior
    current = json.loads((package / "study/development_agent_manifest.json").read_text())
    assert DEVELOPMENT_AGENT != FROZEN_AGENT
    assert len(prior) == 56
    assert set(current) - set(prior) == {"study/results.py"}
    assert {key for key in prior if current[key] != prior[key]} == {"study/store.py"}


@pytest.fixture
def historical_p9_package(tmp_path):
    import tarfile

    import lecturelens_agent

    package = Path(lecturelens_agent.__file__).parent
    copied = tmp_path / "historical"
    shutil.copytree(package, copied, ignore=shutil.ignore_patterns("__pycache__"))
    # Preserve the P9 candidate independently of the new read-only projection.
    with tarfile.open(Path(__file__).parent / "fixtures/p10-prior-source.tar.gz") as archive:
        for member in archive.getmembers():
            (copied / member.name).write_bytes(archive.extractfile(member).read())
    (copied / "study/choice_review.py").unlink()
    return copied


@pytest.fixture
def historical_p7_package(historical_p9_package):
    import tarfile

    copied = historical_p9_package
    # Reconstruct exact P7 bytes without Git access or weakening the historical manifest.
    with tarfile.open(Path(__file__).parent / "fixtures/p9-prior-source.tar.gz") as archive:
        for member in archive.getmembers():
            (copied / member.name).write_bytes(archive.extractfile(member).read())
    for added in ("choice.py", "choice_graph.py"):
        (copied / "study" / added).unlink()
    return copied


def test_p9_identity_positive_and_tampering_rejected(historical_p9_package):
    copied = historical_p9_package
    assert verify_p9_agent(copied) == 62
    with pytest.raises(CostDenied, match="AGENT_IDENTITY_CHANGED"):
        verify_development_agent(copied)
    with (copied / "study/store.py").open("a") as out:
        out.write("\n# tampered\n")
    with pytest.raises(CostDenied, match="AGENT_IDENTITY_CHANGED"):
        verify_p9_agent(copied)


def test_p7_identity_positive_and_tampering_rejected(historical_p7_package):
    copied = historical_p7_package
    assert verify_p7_agent(copied) == 60
    with pytest.raises(CostDenied, match="AGENT_IDENTITY_CHANGED"):
        verify_development_agent(copied)
    with (copied / "study/store.py").open("a") as out:
        out.write("\n# tampered\n")
    with pytest.raises(CostDenied, match="AGENT_IDENTITY_CHANGED"):
        verify_p7_agent(copied)


def test_historical_identity_positive_and_tampering_rejected(historical_p7_package):
    import tarfile

    copied = historical_p7_package
    # Reconstruct the earlier frozen candidate from the independent P7 baseline.

    with tarfile.open(Path(__file__).parent / "fixtures/p7-prior-source.tar.gz") as archive:
        for member in archive.getmembers():
            (copied / member.name).write_bytes(archive.extractfile(member).read())
    for added in ("flashcards.py", "flashcard_graph.py", "scheduling.py"):
        (copied / "study" / added).unlink()
    prior_store = Path(__file__).parent / "fixtures/acceptance_store_702b2f8.py.txt"
    (copied / "study/store.py").write_bytes(prior_store.read_bytes())
    (copied / "study/results.py").unlink()
    assert verify_frozen_agent(copied) == 56
    with pytest.raises(CostDenied, match="AGENT_IDENTITY_CHANGED"):
        verify_development_agent(copied)
    with (copied / "study/store.py").open("a") as out:
        out.write("\n# tampered\n")
    with pytest.raises(CostDenied, match="AGENT_IDENTITY_CHANGED"):
        verify_frozen_agent(copied)


def test_offline_policy_cannot_claim_historical_candidate_or_gain_live_permission():
    now = datetime.now(timezone.utc)
    policy = CostPolicy("synthetic", now.isoformat(), (now + timedelta(hours=1)).isoformat())
    policy.validate()
    for historical in (FROZEN_AGENT, P7_AGENT, P9_AGENT):
        with pytest.raises(CostDenied, match="POLICY_INVALID"):
            replace(policy, candidate_sha=historical).validate()
    with pytest.raises(CostDenied, match="POLICY_INVALID"):
        replace(policy, mode="live", authorization_id="not-authorized").validate()


@pytest.mark.parametrize(
    ("manifest", "verifier"),
    [
        ("p10_agent_manifest.json", verify_development_agent),
        ("p9_agent_manifest.json", verify_p9_agent),
        ("p7_agent_manifest.json", verify_p7_agent),
    ],
)
def test_development_manifest_tampering_is_rejected(tmp_path, monkeypatch, manifest, verifier):
    from lecturelens_agent.study import acceptance_cost

    original = Path(acceptance_cost.__file__)
    raw = original.with_name(manifest).read_text()
    changed = json.loads(raw)
    changed["study/store.py"] = "0" * 64
    (tmp_path / manifest).write_text(json.dumps(changed))
    monkeypatch.setattr(acceptance_cost, "__file__", str(tmp_path / original.name))
    with pytest.raises(CostDenied, match="MANIFEST_CHANGED"):
        verifier()
