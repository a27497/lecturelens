import json
import threading
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from fastapi.testclient import TestClient
from test_tutor import command, offline, run, submit  # noqa: F401
from test_tutor_light import lab as light_lab  # noqa: F401

from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor import flash_app
from lecturelens_real_eval.tutor.flash_ledger import TARGET_SCHEMA, FlashStore, Grant, build_digest
from lecturelens_real_eval.tutor.flash_provider import (
    CONTEXT_BOUND,
    MODEL,
    MODEL_VERSION,
    OUTPUT_TOKENS,
    PRICE_ID,
    RESERVE_NANO_USD,
    FlashProvider,
    digest,
)
from lecturelens_real_eval.tutor.store import TutorStore

QUESTION = "Explain BFS levels"
ANSWER = {"outcome": "answered", "text": "In BFS each frontier adds one edge [e1].", "focus": ""}
USAGE = {
    "prompt_tokens": 100,
    "prompt_cache_hit_tokens": 20,
    "prompt_cache_miss_tokens": 80,
    "completion_tokens": 50,
    "total_tokens": 150,
}
CHARGE = 20 * 6 + 80 * 300 + 50 * 1200


def envelope(**change):
    return {
        "model": MODEL,
        "system_fingerprint": "fp_test",
        "id": "fake-42",
        "usage": USAGE.copy(),
        "choices": [{"finish_reason": "stop", "message": {"content": json.dumps(ANSWER)}}],
        **change,
    }


class Fake:
    def __init__(self):
        self.requests = []
        self.respond = lambda: httpx.Response(200, json=envelope())

    def __call__(self, request):
        assert str(request.url) == "https://api.deepseek.com/chat/completions"
        assert request.headers["authorization"] == "Bearer synthetic-fixture"
        self.requests.append(request.content)
        return self.respond()


@pytest.fixture
def flash(light_lab):  # noqa: F811 -- reuse the isolated Phase 1-D schema fixture
    store, authority, _, scope = light_lab
    with store.connect() as conn:
        conn.execute(TARGET_SCHEMA)
        target = conn.execute("INSERT INTO tutor_flash_target DEFAULT VALUES RETURNING target_id").fetchone()
    now = datetime.now(timezone.utc)
    scope = {key: scope[key] for key in ("owner_id", "course_id", "revision")}
    hashes = [digest(row["text"].encode()) for row in authority.read(scope, "READ")["evidence"]]
    sessions = [
        {**scope, "request_key": key, "evidence_sha256": hashes, "turns": [{"text": QUESTION}]}
        for key in ("a", "b")
    ]
    grant = Grant.model_validate(
        {
            "version": "lecturelens-phase1e-flash-v1",
            "mode": "offline-fake",
            "grant_id": uuid.uuid4().hex,
            "target_id": str(target["target_id"]),
            "build_sha256": build_digest(),
            "dataset_sha256": "f" * 64,
            "model": MODEL,
            "model_version": MODEL_VERSION,
            "price_id": PRICE_ID,
            "issued_at": now - timedelta(seconds=1),
            "expires_at": now + timedelta(hours=1),
            "accepts_supplier_risk": True,
            "request_limit": 2,
            "budget_nano_usd": RESERVE_NANO_USD * 2,
            "sessions": sessions,
        }
    )
    fake = Fake()
    store = FlashStore(store.dsn, grant)
    runtime = flash_app.FlashTutorRuntime(
        store, authority, FlashProvider("synthetic-fixture", transport=httpx.MockTransport(fake))
    )
    return (store, authority, runtime, scope), fake


def start(flash, key="a"):
    lab, _ = flash
    lab[2].initialize()
    scope = {**lab[3], "session_id": command(lab, "CREATE", request_key=key)["session"]["session_id"]}
    return (*lab[:3], scope)


def records(lab):
    with lab[0].connect() as conn:
        trial = conn.execute("SELECT * FROM tutor_flash_trial").fetchone()
        calls = conn.execute("SELECT * FROM tutor_flash_call ORDER BY slot").fetchall()
    return trial, calls


def test_transport_contract_pre_reservation_and_exact_usage(flash):
    lab, fake = start(flash), flash[1]

    def respond():
        trial, [call] = records(lab)
        assert trial["request_limit"] == 2
        assert call["charged_nano_usd"] is None and call["reserved_nano_usd"] == RESERVE_NANO_USD
        assert call["request_sha256"] == digest(fake.requests[0])
        return httpx.Response(200, content=b"\r\n \n" + json.dumps(envelope()).encode())

    fake.respond = respond
    result = run(lab)
    assert result["status"] == "completed" and result["usage"] == [USAGE]
    assert submit(lab)["replayed"]
    assert len(fake.requests) == 1
    request = json.loads(fake.requests[0])
    assert request["model"] == MODEL
    assert request["response_format"] == {"type": "json_object"}
    assert request["thinking"] == {"type": "disabled"}
    assert request["max_tokens"] == OUTPUT_TOKENS and request["stream"] is False
    assert set(request) == {
        "model",
        "messages",
        "response_format",
        "thinking",
        "temperature",
        "max_tokens",
        "stream",
    }
    assert "json object" in request["messages"][0]["content"].lower()
    trial, [call] = records(lab)
    assert trial["fingerprint"] == "fp_test" and trial["stop_code"] is None
    assert call["usage"] == USAGE and call["charged_nano_usd"] == CHARGE
    assert call["request_size_units"] == result["reserved_tokens"] and call["published_at"] is not None
    assert call["provider_id"] == "fake-42" and len(call["response_sha256"]) == 64


@pytest.mark.parametrize(
    ("status", "change", "error", "charge"),
    [
        (200, {"choices": [{"finish_reason": "stop", "message": {"content": "   "}}]}, "BLANK", CHARGE),
        (200, {"choices": [{"finish_reason": "length", "message": {"content": "{"}}]}, "TRUNCATED", CHARGE),
        (200, {"choices": [{"finish_reason": "stop", "message": {"content": "[]"}}]}, "INVALID_JSON", CHARGE),
        (
            200,
            {"choices": [{"finish_reason": "stop", "message": {"content": "{bad"}}]},
            "INVALID_JSON",
            CHARGE,
        ),
        (200, {"choices": []}, "INVALID_ENVELOPE", CHARGE),
        (200, {"usage": None}, "USAGE_UNKNOWN", None),
        (200, {"usage": {**USAGE, "prompt_cache_hit_tokens": True}}, "USAGE_UNKNOWN", None),
        (200, {"usage": {**USAGE, "total_tokens": 999}}, "USAGE_UNKNOWN", None),
        (200, {"usage": {**USAGE, "completion_tokens": -1}}, "USAGE_UNKNOWN", None),
        (
            200,
            {
                "usage": {
                    "prompt_tokens": CONTEXT_BOUND,
                    "prompt_cache_hit_tokens": 0,
                    "prompt_cache_miss_tokens": CONTEXT_BOUND,
                    "completion_tokens": OUTPUT_TOKENS + 1,
                    "total_tokens": CONTEXT_BOUND + OUTPUT_TOKENS + 1,
                }
            },
            "USAGE_OVERRUN",
            RESERVE_NANO_USD + 1200,
        ),
        (200, {"model": "different-model"}, "IDENTITY_CHANGED", CHARGE),
        (429, {}, "RATE_LIMITED", None),
        (503, {}, "UNAVAILABLE", None),
        (307, {}, "HTTP_FAILURE", None),
    ],
)
def test_anomalies_never_retry_or_release_unknown(flash, status, change, error, charge):
    lab, fake = start(flash), flash[1]
    fake.respond = lambda: httpx.Response(status, json=envelope(**change))
    result = run(lab)
    assert result["error_code"] == "TUTOR_FLASH_" + error and result["answer"] is None
    trial, [call] = records(lab)
    assert trial["stop_code"] == result["error_code"]
    assert call["charged_nano_usd"] == charge and call["published_at"] is None
    assert call["reserved_nano_usd"] == RESERVE_NANO_USD
    assert run(start(flash, "b"))["error_code"] == "TUTOR_FLASH_TRIAL_STOPPED"
    assert len(fake.requests) == 1


@pytest.mark.parametrize(
    ("exception", "error"),
    [
        (httpx.ReadTimeout, "TUTOR_FLASH_TIMEOUT"),
        (httpx.ReadError, "TUTOR_UNKNOWN_MODEL_OUTCOME"),
    ],
)
def test_send_error_stops_once(flash, exception, error):
    lab, fake = start(flash), flash[1]

    def respond():
        raise exception("test transport")

    fake.respond = respond
    assert run(lab)["error_code"] == error
    assert records(lab)[1][0]["charged_nano_usd"] is None
    assert len(fake.requests) == 1


def test_pending_after_process_death_blocks_other_slot_and_recovers_without_send(flash, monkeypatch):
    lab, fake = start(flash), flash[1]

    def die(*_):
        raise SystemExit

    submit(lab)
    candidate = lab[0].candidates()[0]
    with monkeypatch.context() as patch:
        patch.setattr(lab[2], "generate", die)
        with pytest.raises(SystemExit):
            lab[2].execute(candidate)
    other = start(flash, "b")
    submit(other)
    other[2].execute(next(c for c in lab[0].candidates() if c["session_id"] == other[3]["session_id"]))
    assert command(other, "GET")["turns"][0]["error_code"] == "TUTOR_FLASH_UNRESOLVED_CHARGE"
    restored_store = FlashStore(lab[0].dsn, lab[0].grant)
    restored = flash_app.FlashTutorRuntime(restored_store, lab[1], lab[2].provider)
    restored.initialize()
    restored.execute(candidate)
    assert command(lab, "GET")["turns"][0]["error_code"] == "TUTOR_UNKNOWN_MODEL_OUTCOME"
    assert records(lab)[1][0]["charged_nano_usd"] is None and not fake.requests


def test_received_checkpoint_recovers_without_second_charge(flash, monkeypatch):
    lab, fake = start(flash), flash[1]
    submit(lab)
    candidate = lab[0].candidates()[0]
    with monkeypatch.context() as patch:
        patch.setattr(lab[2], "publish", lambda *_: (_ for _ in ()).throw(SystemExit()))
        with pytest.raises(SystemExit):
            lab[2].execute(candidate)
    trial, [call] = records(lab)
    assert trial["stop_code"] is None and call["charged_nano_usd"] == CHARGE and call["published_at"] is None
    lab[2].execute(candidate)
    assert command(lab, "GET")["turns"][0]["status"] == "completed"
    assert len(fake.requests) == 1 and records(lab)[1][0]["published_at"] is not None


def test_global_admission_serializes_different_sessions(flash):
    lab, other, fake = start(flash), start(flash, "b"), flash[1]
    submit(lab)
    submit(other)
    first, second = lab[0].candidates()
    entered, release = threading.Event(), threading.Event()

    def respond():
        entered.set()
        assert release.wait(10)
        return httpx.Response(200, json=envelope())

    fake.respond = respond
    with ThreadPoolExecutor(2) as pool:
        worker = pool.submit(lab[2].execute, first)
        try:
            assert entered.wait(10)
            pool.submit(lab[2].execute, second).result(10)
            assert command(other, "GET")["turns"][0]["error_code"] == "TUTOR_FLASH_UNRESOLVED_CHARGE"
        finally:
            release.set()
        worker.result(10)
    assert len(fake.requests) == 1 and len(records(lab)[1]) == 1


@pytest.mark.parametrize("boundary", ["cancel", "version", "changed-bytes", "delete"])
def test_late_receipt_settles_without_publication(flash, boundary):
    lab, fake = start(flash), flash[1]
    original_read = lab[1].read

    def respond():
        if boundary == "cancel":
            command(lab, "CANCEL", client_turn_id="turn-1")
        elif boundary == "version":
            lab[1].scope["revision"] += 1
        elif boundary == "changed-bytes":

            def changed(*args, **kwargs):
                result = original_read(*args, **kwargs)
                for row in result["evidence"]:
                    row["text"] += " Changed."
                return result

            lab[1].read = changed
        else:
            with lab[0].connect() as conn:
                conn.execute("CREATE TABLE evidence_index(owner_id bigint,course_id text,state text)")
                conn.execute(
                    "INSERT INTO evidence_index VALUES (%s,%s,'DELETED')",
                    (lab[3]["owner_id"], lab[3]["course_id"]),
                )
        return httpx.Response(200, json=envelope())

    fake.respond = respond
    submit(lab)
    lab[2].execute(lab[0].candidates()[0])
    trial, [call] = records(lab)
    assert call["charged_nano_usd"] == CHARGE and call["published_at"] is None and trial["stop_code"]
    with lab[0].connect() as conn:
        row = conn.execute(
            "SELECT status,answer FROM tutor_turn WHERE turn_id=%s", (call["turn_id"],)
        ).fetchone()
    assert row["status"] == ("cancelled" if boundary == "cancel" else "failed") and row["answer"] is None
    if boundary == "delete":
        lab[0].purge_deleted()
        with lab[0].connect() as conn:
            assert (
                conn.execute(
                    "SELECT count(*) AS n FROM tutor_turn WHERE turn_id=%s", (call["turn_id"],)
                ).fetchone()["n"]
                == 0
            )
        assert records(lab)[1][0]["charged_nano_usd"] == CHARGE


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("budget", "TUTOR_FLASH_COST_BUDGET"),
        ("expiry", "TUTOR_FLASH_GRANT_EXPIRED"),
        ("rates", "TUTOR_FLASH_GRANT_MISMATCH"),
        ("model", "TUTOR_FLASH_GRANT_MISMATCH"),
        ("evidence", "TUTOR_FLASH_EVIDENCE_NOT_APPROVED"),
    ],
)
def test_pre_send_invalidations_preserve_zero_calls(flash, change, code):
    lab, fake = start(flash), flash[1]
    if change == "evidence":
        original = lab[1].read

        def changed(*args, **kwargs):
            data = original(*args, **kwargs)
            for row in data["evidence"]:
                row["text"] += " An unapproved addition."
            return data

        lab[1].read = changed
    else:
        with lab[0].connect() as conn:
            conn.execute(
                {
                    "budget": "UPDATE tutor_flash_trial SET budget_nano_usd=1",
                    "expiry": "UPDATE tutor_flash_trial SET expires_at=clock_timestamp()",
                    "rates": "UPDATE tutor_flash_trial SET rates='{}'",
                    "model": "UPDATE tutor_flash_trial SET model='other'",
                }[change]
            )
    assert run(lab)["error_code"] == code
    assert not records(lab)[1] and not fake.requests


def test_grant_identity_scope_and_namespace_boundaries(flash):
    lab, fake = start(flash), flash[1]
    for changes, error in [
        ({"grant_id": uuid.uuid4().hex}, "TUTOR_FLASH_GRANT_ALREADY_USED"),
        ({"budget_nano_usd": 1}, "TUTOR_FLASH_GRANT_ALREADY_USED"),
        ({"target_id": str(uuid.uuid4())}, "TUTOR_FLASH_WRONG_DATABASE"),
        ({"build_sha256": "e" * 64}, "TUTOR_FLASH_BUILD_CHANGED"),
    ]:
        with pytest.raises(StudyError, match=error):
            FlashStore(lab[0].dsn, lab[0].grant.model_copy(update=changes)).initialize()
    for change in [{"owner_id": 802}, {"course_id": "other"}, {"revision": 42}]:
        with pytest.raises(StudyError, match="TUTOR_FLASH_SCOPE_DENIED"):
            command(lab, "GET", **change)
    with pytest.raises(StudyError, match="TUTOR_FLASH_SCOPE_DENIED"):
        command(lab, "CREATE", request_key="other")
    with pytest.raises(StudyError, match="TUTOR_FLASH_TASK_DENIED"):
        submit(lab, text="different question")
    mock = TutorStore(lab[0].dsn, engine="light")
    with pytest.raises(StudyError, match="TUTOR_SESSION_NOT_FOUND"):
        command((mock, lab[1], mock, lab[3]), "GET")
    submit(lab)
    assert mock.candidates() == [] and not fake.requests


def test_fingerprint_change_charges_then_stops(flash):
    lab, fake = start(flash), flash[1]
    assert run(lab)["status"] == "completed"
    fake.respond = lambda: httpx.Response(200, json=envelope(system_fingerprint="fp_changed"))
    other = start(flash, "b")
    assert run(other)["error_code"] == "TUTOR_FLASH_IDENTITY_CHANGED"
    trial, calls = records(lab)
    assert trial["fingerprint"] == "fp_test" and [call["charged_nano_usd"] for call in calls] == [CHARGE] * 2


def test_dedicated_factory_denies_mock_and_missing_receipt(monkeypatch):
    monkeypatch.setenv("TUTOR_FLASH_EXPERIMENT", "enabled")
    monkeypatch.setenv("AGENT_LLM_MODE", "mock")
    monkeypatch.delenv("TUTOR_FLASH_GRANT_FILE", raising=False)
    with pytest.raises(RuntimeError, match="EXPERIMENT_DISABLED"):
        flash_app.create_app()
    monkeypatch.setenv("AGENT_LLM_MODE", "real")
    with pytest.raises(RuntimeError, match="GRANT_REQUIRED"):
        flash_app.create_app()


def test_unsigned_experiment_command_is_denied(flash, monkeypatch):
    lab, fake = start(flash), flash[1]
    monkeypatch.setenv("STUDY_AGENT_ENABLED", "false")
    app = flash_app.tutor_app(tutor=lab[2], secret="synthetic-signing-secret" * 2, retriever=object())
    with TestClient(app) as client:
        assert client.post("/internal/v1/tutor/command", json={"operation": "CREATE"}).status_code == 401
    assert not fake.requests


def test_offline_receipt_cannot_use_real_factory(flash, monkeypatch, tmp_path):
    grant = tmp_path / "grant.json"
    grant.write_text(flash[0][0].grant.model_dump_json())
    monkeypatch.setenv("TUTOR_FLASH_EXPERIMENT", "enabled")
    monkeypatch.setenv("AGENT_LLM_MODE", "real")
    monkeypatch.setenv("TUTOR_FLASH_GRANT_FILE", str(grant))
    with pytest.raises(RuntimeError, match="GRANT_MODE_MISMATCH"):
        flash_app.create_app()


def test_cancel_before_reservation_is_free(flash):
    lab, fake = start(flash), flash[1]
    submit(lab)
    candidate = lab[0].candidates()[0]
    command(lab, "CANCEL", client_turn_id="turn-1")
    lab[2].execute(candidate)
    assert command(lab, "GET")["turns"][0]["status"] == "cancelled"
    assert not records(lab)[1] and not fake.requests


def test_budget_reservation_is_replaced_by_settled_charge(flash):
    lab, fake = start(flash), flash[1]
    with lab[0].connect() as conn:
        conn.execute("UPDATE tutor_flash_trial SET budget_nano_usd=%s", (RESERVE_NANO_USD + CHARGE - 1,))
    assert run(lab)["status"] == "completed"
    other = start(flash, "b")
    assert run(other)["error_code"] == "TUTOR_FLASH_COST_BUDGET"
    assert len(fake.requests) == 1
    assert records(lab)[1][0]["charged_nano_usd"] == CHARGE


def test_known_receipt_before_checkpoint_crash_is_never_replayed(flash, monkeypatch):
    lab, fake = start(flash), flash[1]
    submit(lab)
    candidate = lab[0].candidates()[0]
    original = lab[0].checkpoint

    def checkpoint(conn, turn_id, state):
        if state["phase"] == "received":
            raise SystemExit
        return original(conn, turn_id, state)

    with monkeypatch.context() as patch:
        patch.setattr(lab[0], "checkpoint", checkpoint)
        with pytest.raises(SystemExit):
            lab[2].execute(candidate)
    assert records(lab)[1][0]["charged_nano_usd"] == CHARGE
    lab[2].execute(candidate)
    assert len(fake.requests) == 1
    assert command(lab, "GET")["turns"][0]["error_code"] == "TUTOR_UNKNOWN_MODEL_OUTCOME"


def test_http_deadline_and_bounded_body():
    import asyncio

    async def slow(request):
        await asyncio.sleep(5)

    with pytest.raises(StudyError, match="TUTOR_FLASH_TIMEOUT"):
        FlashProvider("synthetic-fixture", transport=httpx.MockTransport(slow)).complete(b"{}", 0.01)
    with pytest.raises(StudyError, match="TUTOR_FLASH_RESPONSE_LIMIT"):
        FlashProvider(
            "synthetic-fixture",
            transport=httpx.MockTransport(
                lambda request: httpx.Response(200, content=b" " * (128 * 1024 + 1))
            ),
        ).complete(b"{}", 1)


def test_ordinary_light_factory_keeps_builtin_mock(light_lab, monkeypatch):  # noqa: F811
    from lecturelens_real_eval.tutor.app import create_app
    from lecturelens_real_eval.tutor.light import MockLightTutor

    store, _, _, _ = light_lab
    monkeypatch.setenv("STUDY_AGENT_ENABLED", "false")
    monkeypatch.setenv("TUTOR_ENABLED", "true")
    monkeypatch.setenv("TUTOR_ENGINE", "light")
    monkeypatch.setenv("AGENT_LLM_MODE", "mock")
    monkeypatch.setenv("AGENT_DATABASE_URL", store.dsn)
    monkeypatch.setenv("TUTOR_FLASH_EXPERIMENT", "enabled")
    app = create_app(secret="synthetic-signing-secret" * 2, retriever=object())
    with TestClient(app):
        assert type(app.state.tutor.provider) is MockLightTutor
