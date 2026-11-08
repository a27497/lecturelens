"""Fixed-run consent, expiry, replay and native handoff regression; no paid transport."""

import copy
import json
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path

import admission
import pytest
import risk_once
from test_workflow import (
    no_secret_or_transport,  # noqa: F401 -- reuse credential/transport fence
)

NOW = datetime(2026, 11, 8, 15, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def isolated_fixed_run_records(tmp_path, monkeypatch):
    # Unit receipts retain the exact frozen scope, but replay state is synthetic.
    # A consumed real claim must neither break unit positives nor be removed.
    original = risk_once.record_paths
    fixed = Path(risk_once.authority()["execution_root"])

    def records(root):
        if Path(root) == fixed:
            return original(tmp_path / "synthetic-fixed-run")
        return original(root)

    monkeypatch.setattr(risk_once, "record_paths", records)


def receipts():
    source = risk_once.authority()
    data = {key: source[key] for key in risk_once.SCOPE_KEYS}
    data.update(
        kind=risk_once.KIND,
        accepted=True,
        authority_sha256=risk_once.AUTHORITY_SHA256,
        statement=source["statement"],
        outer_expires_utc=source["outer_expires_utc"],
        supplier_may_exceed_local_cap=True,
        supplier_absolute_cap_verified=False,
        preparation_git_head="a" * 40,
        issued_utc=NOW.isoformat(),
        expires_utc=(NOW + timedelta(minutes=10)).isoformat(),
    )
    return data, copy.deepcopy(data)


def test_explicit_user_scope_is_not_an_account_hard_cap():
    data, grant = receipts()
    validated = risk_once.validate(data, grant, "a" * 40, NOW)
    assert validated["run_id"] == "v19-smoke-20261108-2227-once"
    assert validated["supplier_absolute_cap_verified"] is False
    assert validated["max_nano_usd"] == 300000000


@pytest.mark.parametrize(
    "field,value",
    [
        ("run_id", "v19-another-run"),
        ("model", "deepseek-v4-pro"),
        ("execution_root", "/tmp/wrong-checkout"),
        ("git_head", "b" * 40),
        ("candidate_sha256", "b" * 64),
        ("packet_sha256", "b" * 64),
        ("scope", "EXPANDED"),
        ("endpoint", "https://example.invalid/chat/completions"),
        ("max_nano_usd", 300000001),
        ("max_requests", 13),
        ("max_output_tokens", 4097),
        ("ordinary_decisions_per_turn", 4),
        ("shared_finish_corrections_per_turn", 2),
        ("concurrency", 2),
        ("concurrency", True),
        ("transport_retries", 1),
        ("reviewer_calls", 1),
        ("embedding_calls", 1),
        ("statement", "I accept risk"),
        ("authority_sha256", "0" * 64),
        ("accepted", False),
        ("supplier_absolute_cap_verified", True),
        ("preparation_git_head", "b" * 40),
    ],
)
def test_boolean_or_changed_scope_cannot_expand_risk_consent(field, value):
    data, grant = receipts()
    data[field] = value
    grant[field] = value
    with pytest.raises(ValueError, match="RISK_BINDING_OR_DEADLINE_INVALID"):
        risk_once.validate(data, grant, "a" * 40, NOW)


@pytest.mark.parametrize(
    "issued,expires,current",
    [
        (NOW, NOW + timedelta(minutes=16), NOW),
        (NOW, NOW + timedelta(minutes=10), NOW + timedelta(minutes=10)),
        (NOW + timedelta(minutes=1), NOW + timedelta(minutes=10), NOW),
        (NOW, NOW + timedelta(seconds=184), NOW),
        (
            datetime(2026, 11, 8, 18, 55, tzinfo=timezone.utc),
            datetime(2026, 11, 8, 19, 1, tzinfo=timezone.utc),
            datetime(2026, 11, 8, 18, 55, tzinfo=timezone.utc),
        ),
    ],
)
def test_no_expiry_extension_or_last_second_launch(issued, expires, current):
    data, grant = receipts()
    for obj in (data, grant):
        obj["issued_utc"], obj["expires_utc"] = issued.isoformat(), expires.isoformat()
    with pytest.raises(ValueError):
        risk_once.validate(data, grant, "a" * 40, current)


@pytest.mark.parametrize("position", [0, 1, 2])
def test_existing_claim_start_or_output_stops_even_without_native_claim(
    tmp_path, position
):
    path = risk_once.record_paths(tmp_path)[position]
    path.parent.mkdir(parents=True)
    path.symlink_to(tmp_path / "nonexistent")
    with pytest.raises(ValueError, match="ALREADY_CLAIMED_STARTED_OR_OBSERVED"):
        risk_once.available(tmp_path)


@pytest.mark.parametrize("position", [0, 1, 2])
def test_valid_risk_receipt_cannot_bypass_consumed_slot(position):
    data, grant = receipts()
    marker = risk_once.record_paths(data["execution_root"])[position]
    marker.parent.mkdir(parents=True)
    marker.write_bytes(b"SYNTHETIC CONSUMED SLOT")
    with pytest.raises(ValueError, match="ALREADY_CLAIMED_STARTED_OR_OBSERVED"):
        risk_once.validate(data, grant, "a" * 40, NOW)


def test_only_one_concurrent_outer_handoff_can_consume_start(tmp_path, monkeypatch):
    monkeypatch.setattr(risk_once, "utcnow", lambda: NOW)
    _, grant = receipts()
    files = [
        tmp_path / name
        for name in ["synthetic-grant", "synthetic-price", "synthetic-risk"]
    ]
    for path in files:
        path.write_bytes(b"SYNTHETIC ONLY")

    def start():
        try:
            risk_once.begin_handoff(tmp_path, grant, *files)
            return "STARTED"
        except (ValueError, FileExistsError):
            return "DENIED"

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: start(), range(2)))
    assert sorted(results) == ["DENIED", "STARTED"]
    marker = risk_once.record_paths(tmp_path)[1]
    assert marker.stat().st_mode & 0o777 == 0o600
    assert (
        json.loads(marker.read_bytes())["state"] == "HANDOFF_STARTED_NO_AUTOMATIC_RETRY"
    )
    with pytest.raises(ValueError):
        risk_once.available(tmp_path)


def test_missing_key_stops_after_explicit_risk_check_before_database_and_claim(
    tmp_path, monkeypatch
):
    data, grant = receipts()
    monkeypatch.setattr(risk_once, "utcnow", lambda: NOW)
    monkeypatch.setattr(admission, "inspect", lambda _: {"frozen": {"synthetic": True}})
    monkeypatch.setattr(admission, "preparation_head", lambda: "a" * 40)
    # The reused autouse fixture replaces the entire credential mapping with a
    # synthetic dictionary; deleting this toy key does not inspect real values.
    del admission.os.environ["AGENT_LLM_API_KEY"]
    receipt, auth = tmp_path / "synthetic-risk.json", tmp_path / "synthetic-grant.json"
    receipt.write_text(json.dumps(data))
    grant["cost_assurance_sha256"] = admission.digest(receipt)
    auth.write_text(json.dumps(grant))
    monkeypatch.setattr(
        admission,
        "database_ready",
        lambda: pytest.fail("no database before injected key"),
    )
    monkeypatch.setattr(
        risk_once,
        "begin_handoff",
        lambda *a: pytest.fail("no claim before injected key"),
    )
    with pytest.raises(ValueError, match="RUNTIME_KEY_NOT_INJECTED"):
        admission.handoff(
            data["execution_root"],
            tmp_path,
            auth,
            auth,
            receipt,
            execute=lambda *a: pytest.fail("no native exec"),
        )


def test_explicit_risk_path_hands_off_original_cli_with_bounded_timeout(
    tmp_path, monkeypatch
):
    data, grant = receipts()
    monkeypatch.setattr(risk_once, "utcnow", lambda: NOW)

    class Clock:
        fromisoformat = staticmethod(datetime.fromisoformat)
        now = staticmethod(lambda *args: NOW)

    monkeypatch.setattr(admission, "datetime", Clock)
    monkeypatch.setattr(admission, "inspect", lambda _: {"frozen": {"synthetic": True}})
    monkeypatch.setattr(admission, "preparation_head", lambda: "a" * 40)
    from lecturelens_real_eval.tutor import selection_smoke

    events = []
    monkeypatch.setattr(
        selection_smoke, "live_admission", lambda *a: events.append("native-admission")
    )
    monkeypatch.setattr(admission, "database_ready", lambda: events.append("database"))
    monkeypatch.setattr(
        risk_once, "begin_handoff", lambda *a: events.append("durable-start")
    )
    receipt, auth = tmp_path / "synthetic-risk.json", tmp_path / "synthetic-grant.json"
    receipt.write_text(json.dumps(data))
    grant["cost_assurance_sha256"] = admission.digest(receipt)
    grant["review_plan_sha256"] = admission.digest(admission.POLICY)
    auth.write_text(json.dumps(grant))
    executed = []
    admission.handoff(
        data["execution_root"],
        Path(data["execution_root"]) / ".data" / ("synthetic-handoff-" + tmp_path.name),
        auth,
        auth,
        receipt,
        execute=lambda *a: executed.append(a),
    )
    assert events == ["native-admission", "database", "durable-start"]
    assert executed[0][0] == "/usr/bin/timeout"
    assert executed[0][1][1:4] == ["--signal=TERM", "--kill-after=2s", "180s"]
    assert (
        str(data["execution_root"]) + "/scripts/dev/run_tutor_smoke_v19.py"
        in executed[0][1]
    )
