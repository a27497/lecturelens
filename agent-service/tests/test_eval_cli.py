import hashlib
import json
from argparse import Namespace
from datetime import datetime, timezone

import pytest

from lecturelens_real_eval import cli
from lecturelens_real_eval.experiments import e3


def approved():
    return {
        "experiment": "e3",
        "approval_id": "b" * 32,
        "commit_sha": "c" * 40,
        "java_jar_sha256": "d" * 64,
        "expires_at": "2026-11-12T23:59:00+08:00",
        "dataset_sha256": e3.DATASET,
        "price_id": e3.PRICE_ID,
        "accepts_supplier_risk": True,
        "budget_nano_usd": 10_000_000_000,
        "initial_requests": 10,
        "retest_requests": 6,
    }


def test_exact_phase_authorization():
    now = datetime(2026, 11, 9, tzinfo=timezone.utc)
    record = approved()
    assert e3.parse_authorization(json.dumps(record), "c" * 40, now)[0] == "b" * 32
    for change in (
        {"commit_sha": "a" * 40},
        {"dataset_sha256": "a" * 64},
        {"price_id": "different"},
        {"expires_at": "2026-11-12T23:59:00-08:00"},
        {"expires_at": "2026-11-08T23:00:00Z"},
        {"expires_at": "2026-11-12T23:59:00"},
        {"accepts_supplier_risk": 1},
        {"budget_nano_usd": 10_000_000_001},
        {"initial_requests": 11},
        {"retest_requests": 7},
    ):
        with pytest.raises(cli.CLIError, match="AUTHORIZATION_INVALID"):
            e3.parse_authorization(json.dumps(record | change), "c" * 40, now)


def test_systemd_credentials_are_explicit_and_private(tmp_path, monkeypatch):
    monkeypatch.setenv("CREDENTIALS_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("TUTOR_FLASH_API_KEY", "inherited-synthetic-fixture")
    with pytest.raises(cli.CLIError, match="ISOLATED_SYSTEMD_SERVICE"):
        e3.service_directory()
    missing = tmp_path / e3.PROVIDER_KEY
    with pytest.raises(cli.CLIError, match="CREDENTIAL_REQUIRED"):
        e3.private_file(tmp_path, missing.name, 1024, read=False)
    fixture = tmp_path / "synthetic-file"
    fixture.write_text("fixture-token")
    fixture.chmod(0o640)
    with pytest.raises(cli.CLIError, match="CREDENTIAL_PERMISSIONS"):
        e3.private_file(tmp_path, fixture.name, 1024, read=False)
    fixture.chmod(0o600)
    assert e3.private_file(tmp_path, fixture.name, 1024, read=False) is None
    missing.symlink_to(fixture)
    with pytest.raises(cli.CLIError, match="CREDENTIAL_REQUIRED"):
        e3.private_file(tmp_path, missing.name, 1024, read=False)


def test_admission_refusal_leaves_no_run(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "workspace", lambda _: tmp_path)
    monkeypatch.delenv("CREDENTIALS_DIRECTORY", raising=False)
    assert cli.main(["eval", "run", "e3", "--run-id", "denied", "--live"]) == 2
    assert "ISOLATED_SYSTEMD_SERVICE" in capsys.readouterr().err
    assert not (tmp_path / ".data").exists()


def test_run_ids_are_unique_and_status_preserves_nonterminal_exit(tmp_path):
    args = Namespace(experiment="e3", run_id="one")
    directory = cli.run_dir(tmp_path, args, create=True)
    cli.write_json_once(directory / "manifest.json", {"mode": "offline", "run_id": "one"})
    with pytest.raises(cli.CLIError, match="RUN_ID_ALREADY_EXISTS"):
        cli.run_dir(tmp_path, args, create=True)
    assert cli.run_dir(tmp_path, args) == directory
    assert cli.summary(directory)["status"] == "STARTING_OR_INTERRUPTED"
    folder = directory / "supervisor"
    folder.mkdir()
    (folder / "run.json").write_text('{"status":"RUNNING","exit_code":125}')
    assert cli.summary(directory)["exit_code"] is None
    (folder / "run.json").write_text('{"status":"DISK_GATE","exit_code":88,"finished_at_utc":"done"}')
    assert cli.summary(directory)["exit_code"] == 88


def test_review_import_is_digest_bound_and_immutable(tmp_path):
    evidence = tmp_path / "evidence"
    packet_dir = evidence / "review-packets"
    packet_dir.mkdir(parents=True)
    packet = {"case_id": "loop-1", "criteria": {"1": "test"}, "answer": "synthetic answer"}
    packet["packet_sha256"] = hashlib.sha256(
        json.dumps(packet, sort_keys=True, ensure_ascii=False).encode()
    ).hexdigest()
    cli.write_json_once(packet_dir / "loop-1.json", packet)
    review = {
        "packet_sha256": packet["packet_sha256"],
        "severe_error": False,
        "confidence": "LOW",
        "checks": {"1": {"verdict": "UNRESOLVED", "basis": "fixture"}},
        "claim_checks": [],
        "citation_and_teaching_check": {"verdict": "UNRESOLVED", "basis": "fixture"},
    }
    votes = [{**review, "model": name, "independent_context": name} for name in ("fake-a", "fake-b")]
    path = tmp_path / "reviews.json"
    args = Namespace(case="loop-1", decision=path)
    path.write_text(json.dumps([votes[0], votes[0]]))
    with pytest.raises(cli.CLIError, match="REVIEW_INDEPENDENCE"):
        cli.add_review(tmp_path, e3, args)
    path.write_text(json.dumps([votes[0], {**votes[1], "packet_sha256": "wrong"}]))
    with pytest.raises(cli.CLIError, match="PACKET_MISMATCH"):
        cli.add_review(tmp_path, e3, args)
    path.write_text(json.dumps(votes))
    cli.add_review(tmp_path, e3, args)
    dest = evidence / "review-decisions" / "loop-1.json"
    assert json.loads(dest.read_bytes()) == votes
    assert cli.summary(tmp_path)["reviews"] == [
        {"case": "loop-1", "packet": str(packet_dir / "loop-1.json"), "received": True}
    ]
    with pytest.raises(cli.CLIError, match="RECORD_ALREADY_EXISTS"):
        cli.add_review(tmp_path, e3, args)
    assert "synthetic answer" not in json.dumps(cli.summary(tmp_path, detailed=True))


def test_unchanged_frozen_phase_budget_can_reserve_all_initial_slots():
    initial = len(e3.CASES) * e3.RESERVE_NANO_USD
    whole_phase = e3.PHASE_REQUESTS * e3.RESERVE_NANO_USD
    assert initial == 3_194_880_000
    assert whole_phase == 5_111_808_000 < e3.PHASE_BUDGET


def test_supervisor_override_cannot_change_the_supervisor(tmp_path, monkeypatch):
    source = tmp_path / "scripts/dev/run_check.py"
    source.parent.mkdir(parents=True)
    source.write_text("frozen supervisor")
    override = tmp_path / "other.py"
    override.write_text("different supervisor")
    monkeypatch.setattr(cli, "workspace", lambda _: tmp_path)
    assert cli.main(["eval", "run", "e3", "--check-supervisor", str(override)]) == 2
    assert not (tmp_path / ".data").exists()


def test_systemd_acl_mask_requires_read_only_root_mount(tmp_path, monkeypatch):
    from types import SimpleNamespace

    credential = tmp_path / "synthetic-file"
    credential.write_text("fixture-token")
    credential.chmod(0o440)
    actual = e3.os.fstat
    monkeypatch.setattr(e3, "SERVICE_CREDENTIALS", tmp_path)

    def root_owned(fd):
        info = actual(fd)
        return SimpleNamespace(st_mode=info.st_mode, st_uid=0, st_gid=0, st_size=info.st_size)

    monkeypatch.setattr(e3.os, "fstat", root_owned)
    monkeypatch.setattr(e3.os, "fstatvfs", lambda fd: SimpleNamespace(f_flag=0))
    with pytest.raises(cli.CLIError, match="CREDENTIAL_PERMISSIONS"):
        e3.private_file(tmp_path, credential.name, 1024, read=False)
    monkeypatch.setattr(e3.os, "fstatvfs", lambda fd: SimpleNamespace(f_flag=e3.os.ST_RDONLY))
    assert e3.private_file(tmp_path, credential.name, 1024, read=False) is None
