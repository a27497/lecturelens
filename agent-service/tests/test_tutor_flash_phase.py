import json
import os
import uuid
from datetime import datetime, timedelta, timezone

import httpx
import psycopg
import pytest
from psycopg import sql
from psycopg.conninfo import make_conninfo
from test_tutor import Authority, command, offline, run, submit  # noqa: F401
from test_tutor_flash import CHARGE, QUESTION, Fake, envelope

from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor import flash_phase
from lecturelens_real_eval.tutor.flash_app import FlashTutorRuntime
from lecturelens_real_eval.tutor.flash_ledger import Grant, build_digest
from lecturelens_real_eval.tutor.flash_phase import (
    PhaseFlashStore,
    PhaseReceipt,
    approve_retest,
    phase_usage,
    provision_phase,
    provision_target,
)
from lecturelens_real_eval.tutor.flash_provider import (
    MODEL,
    MODEL_VERSION,
    PRICE_ID,
    RESERVE_NANO_USD,
    FlashProvider,
    digest,
)


@pytest.fixture
def phase():
    # Phase SQL is qualified deliberately. Use a unique physical test database per test.
    test_dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    db = "e3_" + uuid.uuid4().hex
    with psycopg.connect(test_dsn, autocommit=True) as conn:
        conn.execute(sql.SQL("CREATE DATABASE {}").format(sql.Identifier(db)))
    dsn = make_conninfo(test_dsn, dbname=db)
    phase_id = provision_phase(dsn, "offline-fake")
    scope = dict(owner_id=801, course_id="e3-frozen-course", revision=1)
    authority = Authority(scope)
    try:
        yield dsn, phase_id, scope, authority
    finally:
        with psycopg.connect(test_dsn, autocommit=True) as conn:
            conn.execute(sql.SQL("DROP DATABASE {} WITH (FORCE)").format(sql.Identifier(db)))


def receipt(phase, kind="initial", n=2, **change):
    dsn, phase_id, scope, authority = phase
    now = datetime.now(timezone.utc)
    hashes = [digest(row["text"].encode()) for row in authority.read(scope, "READ")["evidence"]]
    grant = Grant.model_validate(
        {
            "version": "lecturelens-phase1e-flash-v1",
            "mode": "offline-fake",
            "grant_id": uuid.uuid4().hex,
            "target_id": provision_target(dsn, kind),
            "build_sha256": build_digest(),
            "dataset_sha256": flash_phase.DATASET,
            "model": MODEL,
            "model_version": MODEL_VERSION,
            "price_id": PRICE_ID,
            "issued_at": now - timedelta(seconds=1),
            "expires_at": now + timedelta(hours=1),
            "accepts_supplier_risk": True,
            "request_limit": n,
            "budget_nano_usd": RESERVE_NANO_USD * n,
            "sessions": [
                {**scope, "request_key": key, "evidence_sha256": hashes, "turns": [{"text": QUESTION}]}
                for key in ("a", "b")[:n]
            ],
        }
    )
    return PhaseReceipt.model_validate(
        {
            "phase_id": phase_id,
            "kind": kind,
            "commit_sha": uuid.uuid4().hex + "0" * 8,
            "case_ids": ["loop-1", "sql-1"][:n],
            "required": [[hashes]] * n,
            "grant": grant,
            **change,
        }
    )


def worker(phase, receipt, fake):
    dsn, _, scope, authority = phase
    store = PhaseFlashStore(dsn, receipt)
    provider = FlashProvider("synthetic-fixture", transport=httpx.MockTransport(fake), observer=store.observe)
    runtime = FlashTutorRuntime(store, authority, provider)
    runtime.initialize()
    return store, authority, runtime, scope


def session(lab, key):
    result = command(lab, "CREATE", request_key=key)["session"]
    return (*lab[:3], {**lab[3], "session_id": result["session_id"]})


def test_order_atomic_reserve_wire_and_known_charge(phase):
    fake = Fake()
    lab = worker(phase, receipt(phase), fake)
    assert run(session(lab, "b"))["error_code"] == "TUTOR_E3_POSITION_OUT_OF_ORDER"
    assert not fake.requests
    assert run(session(lab, "a"))["status"] == "completed"
    with lab[0].connect() as conn:
        assert phase_usage(conn) == {"reservations": 1, "settled_nano_usd": CHARGE, "unsettled_nano_usd": 0}
        wire = conn.execute("SELECT * FROM tutor_e3_wire").fetchone()
        call = conn.execute("SELECT * FROM tutor_flash_call").fetchone()
    assert wire["request"] == fake.requests[0]
    assert wire["response_complete"] and wire["http_status"] == 200
    assert digest(wire["response"]) == call["response_sha256"] and json.loads(wire["response"]) == envelope()


def test_retrieval_miss_before_reservation(phase):
    fake = Fake()
    lab = worker(phase, receipt(phase, n=1, required=[[["a" * 64]]]), fake)
    assert run(session(lab, "a"))["error_code"] == "TUTOR_E3_RETRIEVAL_MISS"
    with lab[0].connect() as conn:
        assert phase_usage(conn)["reservations"] == 0
    assert not fake.requests


@pytest.mark.parametrize("failure", ["http", "identity", "overrun"])
def test_irrecoverable_across_phase(phase, failure):
    first = receipt(phase, n=1)
    fake = Fake()
    if failure == "http":
        fake.respond = lambda: httpx.Response(503, json={"error": "synthetic"})
    elif failure == "identity":
        fake.respond = lambda: httpx.Response(200, json=envelope(model="wrong"))
    else:
        usage = dict(
            prompt_tokens=100,
            prompt_cache_hit_tokens=0,
            prompt_cache_miss_tokens=100,
            completion_tokens=4097,
            total_tokens=4197,
        )
        fake.respond = lambda: httpx.Response(200, json=envelope(usage=usage))
    lab = worker(phase, first, fake)
    assert run(session(lab, "a"))["status"] == "failed"
    with lab[0].connect() as conn:
        wire = conn.execute("SELECT * FROM tutor_e3_wire").fetchone()
        assert wire["response_complete"] and wire["http_status"] == (503 if failure == "http" else 200)
        assert phase_usage(conn)["unsettled_nano_usd"] == (RESERVE_NANO_USD if failure == "http" else 0)
    with pytest.raises(StudyError, match="TUTOR_E3_RETEST_DENIED"):
        approve_retest(phase[0], first, "loop-1", "e" * 64)
    assert len(fake.requests) == 1


@pytest.mark.parametrize("cap", ["budget", "requests", "allowed"])
def test_retest_shares_cumulative_liability_and_does_not_reopen_first(phase, monkeypatch, cap):
    fake = Fake()
    first = receipt(phase)
    lab = worker(phase, first, fake)
    assert run(session(lab, "a"))["status"] == "completed"
    with pytest.raises(StudyError, match="TUTOR_E3_REPAIR_EVIDENCE_REQUIRED"):
        approve_retest(phase[0], first, "shell-1", "e" * 64)
    approve_retest(phase[0], first, "loop-1", "e" * 64)
    assert run(session(lab, "b"))["error_code"] == "TUTOR_E3_INITIAL_CLOSED"
    second = receipt(phase, kind="retest", n=1)
    with pytest.raises(StudyError, match="TUTOR_E3_RETEST_DENIED"):
        worker(phase, second, fake)
    monkeypatch.setattr("lecturelens_real_eval.tutor.flash_ledger.build_digest", lambda: "d" * 64)
    second = second.model_copy(update={"grant": second.grant.model_copy(update={"build_sha256": "d" * 64})})
    retest = worker(phase, second, fake)
    if cap == "budget":
        monkeypatch.setattr(flash_phase, "PHASE_BUDGET", RESERVE_NANO_USD + CHARGE - 1)
    if cap == "requests":
        monkeypatch.setattr(flash_phase, "PHASE_REQUESTS", 1)
    result = run(session(retest, "a"))
    if cap == "allowed":
        assert result["status"] == "completed"
    else:
        assert result["error_code"] == "TUTOR_E3_PHASE_BUDGET"
    with retest[0].connect() as conn:
        assert phase_usage(conn)["settled_nano_usd"] == CHARGE * (2 if cap == "allowed" else 1)
        assert conn.execute("SELECT count(*) AS n FROM tutor_e3.run").fetchone()["n"] == 2
    altered = second.model_copy(update={"commit_sha": "a" * 40})
    with pytest.raises(StudyError, match="TUTOR_E3_RUN_ALREADY_BOUND"):
        worker(phase, altered, fake)
    assert len(fake.requests) == (2 if cap == "allowed" else 1)


def test_restart_pending_wire_is_not_sent_again(phase, monkeypatch):
    fake = Fake()
    first = receipt(phase, n=1)
    lab = session(worker(phase, first, fake), "a")
    submit(lab)
    candidate = lab[0].candidates()[0]

    def stop(*_):
        raise SystemExit

    with monkeypatch.context() as patch:
        patch.setattr(lab[2], "generate", stop)
        with pytest.raises(SystemExit):
            lab[2].execute(candidate)
    restored = worker(phase, first, fake)
    restored[2].execute(candidate)
    with restored[0].connect() as conn:
        assert phase_usage(conn)["unsettled_nano_usd"] == RESERVE_NANO_USD
        assert not conn.execute("SELECT * FROM tutor_e3_wire").fetchone()
    assert not fake.requests
    with pytest.raises(StudyError, match="TUTOR_E3_RETEST_DENIED"):
        approve_retest(phase[0], first, "loop-1", "e" * 64)


def test_e3_factory_requires_explicit_injection(monkeypatch):
    from lecturelens_real_eval.tutor.flash_e3_app import create_app

    monkeypatch.setenv("TUTOR_FLASH_EXPERIMENT", "phase1e3")
    monkeypatch.setenv("AGENT_LLM_MODE", "real")
    monkeypatch.setenv("STUDY_AGENT_ENABLED", "false")
    monkeypatch.delenv("LECTURELENS_E3_KEY_INJECTED", raising=False)
    with pytest.raises(RuntimeError, match="TUTOR_E3_EXPERIMENT_DISABLED"):
        create_app()


def test_dispatch_markers_detect_pre_send_snapshot_restore(tmp_path):
    directory = tmp_path / "live-dispatch"
    marker = "9" * 64
    flash_phase.mark_dispatch(directory, "initial", 1, marker)
    with pytest.raises(StudyError, match="TUTOR_E3_LEDGER_RESTORE_MISMATCH"):
        flash_phase.verify_dispatch_markers(directory, [])
    call = {"run_kind": "initial", "slot": 1, "request_sha256": marker}
    flash_phase.verify_dispatch_markers(directory, [call])
    with pytest.raises(FileExistsError):
        flash_phase.mark_dispatch(directory, "initial", 1, marker)
