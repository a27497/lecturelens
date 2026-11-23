import json
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from test_tutor import command, offline, run, submit  # noqa: F401
from test_tutor_flash import CHARGE, MIXED_REFUSAL, USAGE, envelope
from test_tutor_light import lab as light_lab  # noqa: F401

from lecturelens_agent.study.contracts import StudyScope
from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor import app
from lecturelens_real_eval.tutor.flash_ledger import TARGET_SCHEMA, build_digest
from lecturelens_real_eval.tutor.flash_provider import (
    MODEL,
    MODEL_VERSION,
    PRICE_ID,
    PRODUCT_TEXT_SYSTEM,
    REFUSAL_WITH_BODY,
    RESERVE_NANO_USD,
    TEXT_CONTRACT_VERSION,
    digest,
)
from lecturelens_real_eval.tutor.trial import TrialAuthorization, create_trial

ANSWER = "answered\nBFS visits each frontier before the next [e1].\n\n```python\nqueue.append(vertex)\n```"


@pytest.fixture
def trial(light_lab, tmp_path, monkeypatch):  # noqa: F811
    old_store, authority, _, old_scope = light_lab
    with old_store.connect() as conn:
        conn.execute(TARGET_SCHEMA)
        target = conn.execute("INSERT INTO tutor_flash_target DEFAULT VALUES RETURNING target_id").fetchone()
    scope = StudyScope.model_validate({key: old_scope[key] for key in StudyScope.model_fields})
    now = datetime.now(timezone.utc)
    grant = TrialAuthorization(
        version="lecturelens-light-tutor-trial-v1",
        grant_id=uuid.uuid4().hex,
        target_id=str(target["target_id"]),
        build_sha256=build_digest(),
        dataset_sha256=digest(scope.model_dump_json().encode()),
        model=MODEL,
        model_version=MODEL_VERSION,
        price_id=PRICE_ID,
        mode="offline-fake",
        issued_at=now - timedelta(seconds=1),
        expires_at=now + timedelta(hours=1),
        accepts_supplier_risk=True,
        request_limit=3,
        budget_nano_usd=1_000_000_000,
        scope=scope,
    )
    path = tmp_path / "receipt.json"
    path.write_text(grant.model_dump_json())
    path.chmod(0o600)
    monkeypatch.setenv("TUTOR_TRIAL_RECEIPT_FILE", str(path))
    requests = []

    def respond(request):
        requests.append(request.content)
        return httpx.Response(
            200, json=envelope(choices=[{"finish_reason": "stop", "message": {"content": ANSWER}}])
        )

    runtime = create_trial(old_store.dsn, authority, transport=httpx.MockTransport(respond))
    runtime.initialize()
    return (runtime.store, authority, runtime, scope.model_dump()), grant, path, requests


def session(lab):
    result = command(lab, "CREATE", request_key=uuid.uuid4().hex)
    assert result["provider_mode"] == "mock-http"
    return (*lab[:3], lab[3] | {"session_id": result["session"]["session_id"]})


def test_normal_sessions_share_three_slots_and_keep_private_evidence(trial):
    lab, _, _, requests = trial
    first = session(lab)
    result = run(first, text="Why is breadth-first search layered?")
    assert result["answer"] == ANSWER.split("\n", 1)[1]
    assert result["model_calls"] == 1 and result["citations"][0]["evidence_id"] == "e1"
    assert "checkpoint" not in result and "provider_content" not in result
    assert submit(first, text="Why is breadth-first search layered?")["replayed"]
    for change in ({"owner_id": 111}, {"course_id": "foreign"}, {"revision": 20}):
        with pytest.raises(StudyError, match="TUTOR_FLASH_SCOPE_DENIED"):
            command(lab, "LIST", **change)
    for index in (2, 3):
        assert run(session(lab), text=f"Explain another BFS example {index}")["outcome"] == "answered"
    assert run(session(lab))["error_code"] == "TUTOR_FLASH_COST_BUDGET"
    assert len(requests) == 3
    request = json.loads(requests[0])
    assert request["response_format"] == {"type": "text"} and "tools" not in request
    assert request["messages"][0]["content"] == PRODUCT_TEXT_SYSTEM
    assert PRODUCT_TEXT_SYSTEM.startswith(f"Tutor response contract {TEXT_CONTRACT_VERSION}.")
    assert PRODUCT_TEXT_SYSTEM.index("Full refusal takes precedence") < PRODUCT_TEXT_SYSTEM.index(
        "For direct answers"
    )
    with lab[0].connect() as conn:
        checkpoint = conn.execute(
            "SELECT checkpoint FROM tutor_turn WHERE turn_id=%s", (result["turn_id"],)
        ).fetchone()["checkpoint"]
        calls = conn.execute("SELECT * FROM tutor_flash_call ORDER BY slot").fetchall()
    assert request["messages"] == checkpoint["messages"]
    assert checkpoint["provider_content"] == ANSWER
    assert [r["slot"] for r in calls] == [1, 2, 3]
    for row, request_body in zip(calls, requests, strict=True):
        assert row["reserved_nano_usd"] == RESERVE_NANO_USD and row["charged_nano_usd"] == CHARGE
        assert (lab[0].dispatch_dir / f"trial-{row['slot']}").read_text() == digest(request_body)


@pytest.mark.parametrize(
    ("content", "previous_fingerprint", "error", "diagnostic_error"),
    [
        (MIXED_REFUSAL, None, "TUTOR_PROTOCOL_FAILURE", REFUSAL_WITH_BODY),
        (
            "answered\nEach edge adds one hop [unrelated]",
            None,
            "TUTOR_CITATION_MISMATCH",
            "TUTOR_CITATION_MISMATCH",
        ),
        (MIXED_REFUSAL, "previous_fp", "TUTOR_FLASH_IDENTITY_CHANGED", "TUTOR_FLASH_IDENTITY_CHANGED"),
    ],
)
def test_invalid_text_settles_once_without_publication(
    trial, monkeypatch, content, previous_fingerprint, error, diagnostic_error
):
    lab, _, _, requests = trial

    def respond(request):
        requests.append(request.content)
        return httpx.Response(
            200, json=envelope(choices=[{"finish_reason": "stop", "message": {"content": content}}])
        )

    runtime = create_trial(lab[0].dsn, lab[1], transport=httpx.MockTransport(respond))
    runtime.initialize()
    if previous_fingerprint:
        with runtime.store.connect() as conn:
            conn.execute(
                "UPDATE tutor_flash_trial SET fingerprint=%s WHERE singleton", (previous_fingerprint,)
            )
    settles = []
    settle = runtime.store.settle

    def record_settlement(turn_id, request_sha256, result):
        settles.append(turn_id)
        return settle(turn_id, request_sha256, result)

    monkeypatch.setattr(runtime.store, "settle", record_settlement)
    active = session((runtime.store, lab[1], runtime, lab[3]))
    result = run(active)
    assert result["status"] == result["outcome"] == "failed"
    assert result["answer"] is None and result["citations"] == []
    assert result["error_code"] == error and result["usage"] == [USAGE]
    assert result["model_calls"] == 1
    assert submit(active)["replayed"] and not runtime.store.candidates()
    assert settles == [result["turn_id"]] and len(requests) == 1
    with runtime.store.connect() as conn:
        [call] = conn.execute("SELECT * FROM tutor_flash_call").fetchall()
        stop_code = conn.execute("SELECT stop_code FROM tutor_flash_trial").fetchone()["stop_code"]
    assert call["error_code"] == diagnostic_error and stop_code == error
    assert call["charged_nano_usd"] == CHARGE and call["usage"] == USAGE
    assert call["observed_at"] is not None and call["published_at"] is None


def test_trial_cannot_resume_restored_ledger(trial):
    lab, _, _, requests = trial
    assert run(session(lab))["status"] == "completed"
    with lab[0].connect() as conn:
        conn.execute("DELETE FROM tutor_flash_call")
    assert run(session(lab))["error_code"] == "TUTOR_E3_LEDGER_RESTORE_MISMATCH"
    assert len(requests) == 1


def test_trial_unknown_charge_blocks_after_restart(trial):
    lab, _, _, requests = trial

    def timeout(request):
        requests.append(request.content)
        raise httpx.ReadTimeout("synthetic", request=request)

    # Install a transport on a fresh instance using the same immutable authorization.
    runtime = create_trial(lab[0].dsn, lab[1], transport=httpx.MockTransport(timeout))
    runtime.initialize()
    assert run(session((runtime.store, lab[1], runtime, lab[3])))["error_code"] == "TUTOR_FLASH_TIMEOUT"
    restored = create_trial(lab[0].dsn, lab[1], transport=httpx.MockTransport(timeout))
    restored.initialize()
    assert (
        run(session((restored.store, lab[1], restored, lab[3])))["error_code"] == "TUTOR_FLASH_TRIAL_STOPPED"
    )
    with restored.store.connect() as conn:
        [call] = conn.execute("SELECT * FROM tutor_flash_call").fetchall()
    assert call["charged_nano_usd"] is None and call["reserved_nano_usd"] == RESERVE_NANO_USD
    assert len(requests) == 1


def test_trial_receipt_caps_and_e3_database_refusal(trial):
    lab, grant, _, _ = trial
    for change in ({"request_limit": 4}, {"budget_nano_usd": 1_000_000_001}, {"dataset_sha256": "0" * 64}):
        with pytest.raises(ValidationError):
            TrialAuthorization.model_validate(grant.model_dump() | change)
    # This DB is already isolated. A historical schema is checked outside its search path.
    with lab[0].connect() as conn:
        conn.execute("CREATE SCHEMA tutor_e3")
    try:
        with pytest.raises(StudyError, match="TUTOR_TRIAL_REQUIRES_ISOLATED_DATABASE"):
            lab[2].initialize()
    finally:
        with lab[0].connect() as conn:
            conn.execute("DROP SCHEMA tutor_e3")


def test_normal_factory_requires_separate_receipt_and_matches_mock_mode(trial, monkeypatch):
    lab, _, path, _ = trial
    for key, value in {
        "TUTOR_ENABLED": "true",
        "TUTOR_ENGINE": "light",
        "TUTOR_PROVIDER": "deepseek-flash",
        "AGENT_LLM_MODE": "mock",
        "STUDY_AGENT_ENABLED": "false",
        "AGENT_DATABASE_URL": lab[0].dsn,
        "AGENT_JAVA_BASE_URL": "http://127.0.0.1:1",
    }.items():
        monkeypatch.setenv(key, value)
    with pytest.raises(RuntimeError, match="TUTOR_FLASH_GRANT_MODE_MISMATCH"):
        with TestClient(app.create_app(retriever=object(), secret="s" * 32)):
            pytest.fail("offline receipt must never start a live provider")
    transport = httpx.MockTransport(lambda _: pytest.fail("startup has no HTTP requests"))
    path.chmod(0o644)
    with pytest.raises(RuntimeError, match="TUTOR_TRIAL_RECEIPT_REQUIRED"):
        with TestClient(app.create_app(retriever=object(), secret="s" * 32, trial_transport=transport)):
            pytest.fail("receipt must be private")
    path.chmod(0o600)
    with TestClient(app.create_app(retriever=object(), secret="s" * 32, trial_transport=transport)) as client:
        assert client.app.state.tutor.provider.offline
        assert client.app.state.tutor.query_language is None
    monkeypatch.setenv("TUTOR_QUERY_LANGUAGE", "english")
    with TestClient(app.create_app(retriever=object(), secret="s" * 32, trial_transport=transport)) as client:
        assert client.app.state.tutor.query_language.mode == "english"
