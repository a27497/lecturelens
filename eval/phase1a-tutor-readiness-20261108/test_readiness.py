"""Synthetic receipts and fake HTTP only; never a valid dispatch authorization."""

import json
from datetime import datetime, timedelta, timezone

import httpx
import pytest
import test_p8_tutor_eval as accounting
import test_tutor_v15 as legacy
from lecturelens_agent.study.store import StudyError
from lecturelens_real_eval.tutor.complete_authority import CompleteEvidenceAuthority
from lecturelens_real_eval.tutor.diagnostic_capture import private_file
from lecturelens_real_eval.tutor.selection_smoke import live_admission, verify_inputs
from lecturelens_real_eval.tutor.usable_policy import UsablePolicy
from lecturelens_real_eval.tutor_channel import Channel, EvalError, encode

offline = legacy.offline
isolated = accounting.isolated


def test_phase0_legacy_evidence_cannot_masquerade_as_v19_complete_source():
    scope = dict(owner_id=42, course_id="task", revision=1)
    legacy_body = {**scope, "evidence": []}
    authority = CompleteEvidenceAuthority(
        "http://127.0.0.1:39999",
        "synthetic-only",
        transport=httpx.MockTransport(
            lambda _: httpx.Response(200, json={"data": legacy_body})
        ),
    )
    with pytest.raises(StudyError, match="EVIDENCE_SCOPE_MISMATCH"):
        authority.read(scope)


def receipts(tmp_path, monkeypatch):
    state = verify_inputs()
    now = datetime.now(timezone.utc)
    grant = dict(
        authorized=True,
        scope="ONE_V19_THREE_TURN_SHARED_FINISH_NO_RETRY_NO_EXPANSION",
        candidate_sha256=state["candidate_sha256"],
        packet_sha256=state["packet_sha256"],
        model="deepseek-flash",
        shared_finish_corrections_per_turn=1,
        ordinary_decisions_per_turn=3,
        max_output_tokens=4096,
        max_requests=12,
        max_nano_usd=300000000,
        expires_utc=(now + timedelta(minutes=1)).isoformat(),
        run_id="v19-synthetic-test-only",
        git_head="2ecf4d52af1084bad405e98a6e78027bf4c5ab5d",
    )
    price = dict(
        requested_model="deepseek-flash",
        configuration_available_verified=True,
        input_nano_usd_per_token=300,
        output_nano_usd_per_token=1200,
        official_source="https://api-docs.deepseek.com/quick_start/pricing/",
        reviewed_utc=now.isoformat(),
        no_cache_peak_rates_cover_current_prices=True,
    )
    monkeypatch.setenv("LECTURELENS_REAL_EVAL", "1")
    paths = [tmp_path / "synthetic-grant.json", tmp_path / "synthetic-price.json"]
    return state, grant, price, paths


@pytest.mark.parametrize(
    "field,value",
    [
        ("authorized", False),
        ("model", "deepseek-v4-pro"),
        ("max_requests", 13),
        ("max_nano_usd", 300000001),
        ("max_output_tokens", 4097),
        ("ordinary_decisions_per_turn", 4),
        ("shared_finish_corrections_per_turn", 2),
        ("packet_sha256", "0" * 64),
        ("expires_utc", "2000-01-01T00:00:00+00:00"),
    ],
)
def test_admission_refuses_expansion_before_transport_or_secret(
    tmp_path, monkeypatch, field, value
):
    state, grant, price, paths = receipts(tmp_path, monkeypatch)
    grant[field] = value
    for path, data in zip(paths, [grant, price], strict=True):
        path.write_text(json.dumps(data))
    with pytest.raises(EvalError, match="V19_LIVE_RECEIPTS_INVALID"):
        live_admission(state, *paths)


def test_admission_checks_exact_head_and_price_age(tmp_path, monkeypatch):
    state, grant, price, paths = receipts(tmp_path, monkeypatch)
    for path, data in zip(paths, [grant, price], strict=True):
        path.write_text(json.dumps(data))
    # Admission validates receipts without constructing transport or reading a key.
    assert live_admission(state, *paths)["run_id"] == "v19-synthetic-test-only"
    grant["git_head"] = "0" * 40
    paths[0].write_text(json.dumps(grant))
    with pytest.raises(EvalError, match="EXACT_CLEAN_COMMIT"):
        live_admission(state, *paths)
    grant["git_head"] = "2ecf4d52af1084bad405e98a6e78027bf4c5ab5d"
    price["reviewed_utc"] = "2000-01-01T00:00:00+00:00"
    for path, data in zip(paths, [grant, price], strict=True):
        path.write_text(json.dumps(data))
    with pytest.raises(EvalError, match="RECEIPTS_INVALID"):
        live_admission(state, *paths)


def test_single_use_claim_refuses_repeat_and_symlink(tmp_path):
    path = tmp_path / "synthetic.used"
    private_file(path, b"synthetic only")
    with pytest.raises(FileExistsError):
        private_file(path, b"replacement")
    assert (
        path.read_bytes() == b"synthetic only" and path.stat().st_mode & 0o777 == 0o600
    )
    link = tmp_path / "link.used"
    link.symlink_to(path)
    with pytest.raises(FileExistsError):
        private_file(link, b"replacement")


def test_thirteenth_request_never_reaches_transport(isolated):
    ledger = accounting.account(isolated, UsablePolicy())
    sent = []

    def send(request):
        assert ledger.check()["pending"] == 1
        sent.append(1)
        return accounting.response()

    channel = Channel(ledger, transport=httpx.MockTransport(send))
    for _ in range(12):
        channel.request(accounting.MESSAGES, accounting.TUTOR, max_tokens=4096)
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        channel.request(accounting.MESSAGES, accounting.TUTOR, max_tokens=4096)
    assert len(sent) == ledger.check()["calls"] == 12


def test_money_limit_prevents_first_send_and_unknown_or_divergence_stops(isolated):
    raw = encode({"model": "deepseek-flash", "tools": accounting.TUTOR})
    ledger = accounting.account(isolated, UsablePolicy(max_nano_usd=1))
    transport = httpx.MockTransport(
        lambda _: pytest.fail("budget must precede transport")
    )
    with pytest.raises(EvalError, match="BUDGET_EXHAUSTED"):
        Channel(ledger, transport=transport).request(
            accounting.MESSAGES, accounting.TUTOR, max_tokens=4096
        )
    assert ledger.check()["calls"] == 0
    # A separate test ledger exercises the crash window, before any HTTP send.
    ledger.path = ledger.path.with_name("pending.jsonl")
    ledger.run_id += "-pending"
    ledger.policy = UsablePolicy()
    ledger.install()
    reservation = ledger.reserve(raw, 4096)
    assert ledger.check()["nano_usd"] == reservation["reserved_nano_usd"] > 0
    with pytest.raises(EvalError, match="UNKNOWN_OUTCOME"):
        ledger.reserve(raw, 4096)
    ledger.path.write_bytes(b"")
    with pytest.raises(EvalError, match="LEDGER_MISMATCH"):
        ledger.check()


def test_usage_over_reservation_blocks_further_requests(isolated):
    ledger = accounting.account(isolated, UsablePolicy())
    reservation = ledger.reserve(
        encode({"model": "deepseek-flash", "tools": accounting.TUTOR}), 4096
    )
    with pytest.raises(EvalError, match="USAGE_EXCEEDED"):
        ledger.settle(
            reservation, {"prompt_tokens": 1048576, "completion_tokens": 4096}
        )
    assert ledger.check()["blocked"] == "REAL_EVAL_USAGE_EXCEEDED"
    assert ledger.check()["nano_usd"] > 300000000
    # Detecting excess usage is necessarily after the supplier's response. This
    # negative documents why the local cap cannot be called an invoice hard cap.
    with pytest.raises(EvalError, match="RUN_STOPPED"):
        ledger.reserve(
            encode({"model": "deepseek-flash", "tools": accounting.TUTOR}), 4096
        )
