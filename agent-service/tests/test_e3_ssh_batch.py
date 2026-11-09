import subprocess
import sys
from argparse import Namespace
from datetime import datetime, timezone
from types import SimpleNamespace

import httpx
import pytest
from test_tutor import command, offline  # noqa: F401
from test_tutor_flash import Fake, envelope
from test_tutor_flash_phase import phase, receipt, worker  # noqa: F401

from lecturelens_real_eval import cli
from lecturelens_real_eval.experiments import e3, e3_terminal
from lecturelens_real_eval.tutor.flash_phase import phase_usage
from lecturelens_real_eval.tutor.flash_provider import RESERVE_NANO_USD


def test_explicit_developer_mode_rejects_without_ssh(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(cli, "workspace", lambda _: tmp_path)
    monkeypatch.delenv("SSH_TTY", raising=False)
    args = ["eval", "run", "e3", "--dev-ssh", "--confirmed-price-id", e3.PRICE_ID]
    assert cli.main(args) == 2
    assert "REQUIRES_LIVE_BATCH" in capsys.readouterr().err
    assert cli.main(args + ["--live", "--batch"]) == 2
    assert "FOREGROUND_SSH_TTY" in capsys.readouterr().err
    assert not (tmp_path / ".data").exists()


def test_foreground_pty_alone_is_insufficient(monkeypatch):
    monkeypatch.setenv("SSH_TTY", "/dev/pts/29")
    streams = SimpleNamespace(fileno=lambda: 0)
    monkeypatch.setattr(e3_terminal, "sys", SimpleNamespace(stdin=streams, stdout=streams, stderr=streams))
    monkeypatch.setattr(e3_terminal.os, "ttyname", lambda _: "/dev/pts/29")
    monkeypatch.setattr(e3_terminal.os, "tcgetpgrp", lambda _: e3_terminal.os.getpgrp())
    monkeypatch.setattr(e3_terminal, "ssh_login_session", lambda _: False)
    with pytest.raises(cli.CLIError, match="FOREGROUND_SSH_TTY"):
        e3_terminal.require_ssh_tty()
    monkeypatch.setattr(e3_terminal, "ssh_login_session", lambda _: True)
    e3_terminal.require_ssh_tty()


def test_dev_admission_binds_commit_deadline_and_single_anchor(tmp_path, monkeypatch):
    args = Namespace(dev_ssh=True, confirmed_price_id=e3.PRICE_ID)
    monkeypatch.setattr(e3, "require_ssh_tty", lambda: None)
    monkeypatch.setattr(e3, "git", lambda _root, operation, *_: "" if operation == "status" else "e" * 40)
    jar = tmp_path / "java.jar"
    jar.write_bytes(b"fixture")
    monkeypatch.setattr(e3, "options", lambda *_: {"java_jar": str(jar)})
    monkeypatch.setattr(e3, "check_disk", lambda _: None)
    monkeypatch.setattr(
        e3, "datetime", SimpleNamespace(now=lambda _: datetime(2026, 11, 9, tzinfo=timezone.utc))
    )
    admission = e3.live_admission(tmp_path, args)
    assert admission.directory is None and admission.commit_sha == "e" * 40
    assert admission.expires_at == e3.PHASE_EXPIRY
    path = tmp_path / ".data/phase1e3/live-anchor.json"
    path.parent.mkdir(parents=True)
    path.write_text("{}")
    with pytest.raises(cli.CLIError, match="CONSUMED_PHASE"):
        e3.live_admission(tmp_path, args)
    monkeypatch.setattr(e3, "datetime", SimpleNamespace(now=lambda _: e3.PHASE_EXPIRY))
    with pytest.raises(cli.CLIError, match="AUTHORIZATION_INVALID_OR_EXPIRED"):
        e3.live_admission(tmp_path, args)


def test_hidden_input_refuses_missing_key_and_echo_fallback(monkeypatch):
    monkeypatch.setattr(e3_terminal, "require_ssh_tty", lambda: None)
    monkeypatch.setattr(e3_terminal.resource, "setrlimit", lambda *_: None)
    monkeypatch.setattr("builtins.input", lambda _: "E3 USD10")
    monkeypatch.setattr(e3_terminal.getpass, "getpass", lambda _: "")
    with pytest.raises(cli.CLIError, match="CREDENTIAL_INVALID"):
        e3_terminal.read_operator_key()

    def fallback(_):
        e3_terminal.warnings.warn("fixture fallback", e3_terminal.getpass.GetPassWarning, stacklevel=1)

    monkeypatch.setattr(e3_terminal.getpass, "getpass", fallback)
    with pytest.raises(cli.CLIError, match="HIDDEN_KEY_INPUT_REQUIRED"):
        e3_terminal.read_operator_key()


def test_disk_policy_propagates_original_refusal_code(tmp_path, monkeypatch):
    monkeypatch.setattr(
        e3_terminal.runpy,
        "run_path",
        lambda _: {
            "disk": lambda: {
                "allowed": False,
                "used_bytes": 87 * 1024**3,
                "available_bytes": 13 * 1024**3,
            }
        },
    )
    monkeypatch.setattr(cli, "workspace", lambda _: tmp_path)
    monkeypatch.setattr(e3, "require_ssh_tty", lambda: None)
    monkeypatch.setattr(e3, "check_checkout", lambda _: None)
    monkeypatch.setattr(
        e3, "datetime", SimpleNamespace(now=lambda _: datetime(2026, 11, 9, tzinfo=timezone.utc))
    )
    assert (
        cli.main(["eval", "run", "e3", "--live", "--dev-ssh", "--batch", "--confirmed-price-id", e3.PRICE_ID])
        == 88
    )
    assert not (tmp_path / ".data").exists()


def test_anonymous_pipe_delivers_only_explicit_synthetic_key():
    code = """
from lecturelens_real_eval.experiments import e3_worker
def sink(*, api_key):
    assert api_key == 'sk-synthetic-pipe-fixture'
    return 0
e3_worker.experiment_app = sink
raise SystemExit(e3_worker.pipe_app())
"""
    result = subprocess.run(
        [sys.executable, "-c", code],
        input=b"sk-synthetic-pipe-fixture",
        env={"TUTOR_E3_LAUNCHER_PID": str(e3_terminal.os.getpid()), "TUTOR_FLASH_API_KEY": "unused-fixture"},
        capture_output=True,
        check=False,
        timeout=10,
    )
    assert result.returncode == 0 and not result.stdout and not result.stderr


@pytest.mark.parametrize("failure", [None, "blank", "unknown"])
def test_batch_stops_at_first_failure_with_pg_and_mock_http(phase, failure):  # noqa: F811
    fake = Fake()
    first = receipt(phase)
    # Leave a third frozen position available to detect accidental skipping.
    last = first.grant.sessions[-1]
    last = last.model_copy(update={"turns": [*last.turns, last.turns[0]]})
    first = first.model_copy(
        update={
            "case_ids": ["loop-1", "sql-1", "sql-2"],
            "required": [*first.required, first.required[-1]],
            "grant": first.grant.model_copy(
                update={
                    "request_limit": 3,
                    "budget_nano_usd": 3 * RESERVE_NANO_USD,
                    "sessions": [first.grant.sessions[0], last],
                }
            ),
        }
    )
    lab = worker(phase, first, fake)
    store, _, runtime, scope = lab

    def respond():
        if len(fake.requests) == 2 and failure == "unknown":
            return httpx.Response(503, json={"error": "synthetic"})
        if len(fake.requests) == 2 and failure == "blank":
            return httpx.Response(
                200, json=envelope(choices=[{"finish_reason": "stop", "message": {"content": " "}}])
            )
        return httpx.Response(200, json=envelope())

    fake.respond = respond

    class Smoke:
        receipt = first
        cases = {
            key: ({"question": first.grant.sessions[0].turns[0].text, "socratic": False}, {})
            for key in first.case_ids
        }
        scopes = dict.fromkeys(first.case_ids, scope)
        result = {"positions": dict.fromkeys(first.case_ids, "NOT_RUN")}

        def api(self, method, path, body=None):
            if path.endswith("/sessions"):
                return command(lab, "CREATE", **body)
            current = (*lab[:3], {**scope, "session_id": path.split("/")[6]})
            if method == "POST":
                result = command(current, "TURN", **body)
                runtime.execute(store.candidates()[0])
                return result
            return command(current, "GET")

        def wait(self, action, predicate, timeout, label):
            value = action()
            assert predicate(value)
            return value

        def record(self):
            with store.connect() as conn:
                self.result["phase_usage"] = phase_usage(conn)
                for row in conn.execute("SELECT * FROM tutor_turn").fetchall():
                    self.result["positions"][row["client_turn_id"]] = {
                        "semantic_quality": "QUALITY_PENDING"
                        if row["status"] == "completed"
                        else "NOT_SCORED",
                    }

        def save(self):
            pass

    smoke = Smoke()
    result = e3.evaluate_batch(smoke, lambda: None)
    assert result == ("COMPLETE" if failure is None else "STOPPED_EXECUTION_OR_RETRIEVAL")
    assert len(fake.requests) == (3 if failure is None else 2)
    assert smoke.result["positions"]["loop-1"]["semantic_quality"] == "QUALITY_PENDING"
    if failure:
        assert smoke.result["positions"]["sql-2"] == "NOT_RUN"
    assert smoke.result["phase_usage"]["unsettled_nano_usd"] == (
        RESERVE_NANO_USD if failure == "unknown" else 0
    )
