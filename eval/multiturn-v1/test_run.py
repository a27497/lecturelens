"""Protect real-trial admission, failure retention and START ordering."""

import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location(
    "multiturn_trial", Path(__file__).with_name("run.py")
)
TRIAL = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(TRIAL)


@pytest.mark.parametrize(
    "base",
    ["http://127.0.0.1:8080", "https://example.com", "http://127.0.0.1:8084/other"],
)
def test_trial_rejects_non_isolated_gateway_before_network(base):
    with pytest.raises(ValueError, match="isolated"):
        TRIAL.Gateway(base)


def test_existing_trial_is_not_reused_or_overwritten(tmp_path):
    output = tmp_path / "existing"
    output.mkdir()
    marker = output / "trial.json"
    marker.write_text("original failed trial")

    def unexpected(*args):
        pytest.fail("No network operation is allowed for an existing trial")

    with pytest.raises(FileExistsError):
        TRIAL.execute(SimpleNamespace(api=unexpected), {}, [], {}, {}, output)
    assert marker.read_text() == "original failed trial"


def test_changed_previous_artifact_stops_before_start(tmp_path, monkeypatch):
    calls = []

    def api(method, path, body=None):
        calls.append(body or path)
        if path == "/api/auth/login":
            return {"accessToken": "fixture-token"}
        if path.endswith("index-status"):
            return {"status": "READY"}
        assert body["operation"] == "READ"
        return {"run": {"status": "succeeded"}, "artifact": {"explanation": "changed"}}

    monkeypatch.setattr(
        TRIAL, "evidence_snapshot", lambda *args: {"revision": 1, "items": []}
    )
    cases = [
        {
            "id": "prior",
            "resume": {
                "scope": {"session_id": "session", "run_id": "run"},
                "artifact": {"explanation": "frozen"},
            },
            "turns": [],
        }
    ]
    with pytest.raises(RuntimeError, match="PREVIOUS_TURN_CHANGED"):
        TRIAL.execute(
            SimpleNamespace(api=api),
            {"credentials": {}, "task_id": "course"},
            cases,
            {},
            {},
            tmp_path / "new-trial",
        )
    assert not any(
        isinstance(item, dict) and item.get("operation") == "START" for item in calls
    )


def test_failed_run_keeps_record_and_prevents_following_turns(tmp_path, monkeypatch):
    output, starts, observed_options = tmp_path / "new-trial", [], []

    def api(method, path, body=None):
        if path == "/api/auth/login":
            return {"accessToken": "fixture-token"}
        if path.endswith("index-status"):
            return {"status": "READY"}
        operation = body["operation"]
        if operation == "CREATE_SESSION":
            return {"session_id": "new-session"}
        if operation == "START":
            # A transport failure after acceptance must leave the exact request key.
            reserved = json.loads((output / "failed-turn-1.private.json").read_text())
            assert reserved["command"] == body
            starts.append(body)
            return {
                "run": {
                    "run_id": "new-run",
                    "status": "failed",
                    "error_code": "budget_exceeded",
                    "model_calls": 2,
                    "tool_calls": 1,
                },
                "artifact": None,
            }
        assert operation == "EVENTS"
        return {"events": []}

    class Connection:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def execute(self, sql, parameters):
            assert parameters == ("new-run",)
            return SimpleNamespace(fetchall=list)

    def connect(*args, **kwargs):
        observed_options.append(kwargs["options"])
        return Connection()

    monkeypatch.setattr(
        TRIAL, "evidence_snapshot", lambda *args: {"revision": 1, "items": []}
    )
    monkeypatch.setattr(TRIAL.psycopg, "connect", connect)
    cases = [
        {
            "id": "failed",
            "turns": [
                {"goal": "first", "expected": "explanation"},
                {"goal": "never started", "expected": "explanation"},
            ],
        }
    ]
    assert not TRIAL.execute(
        SimpleNamespace(api=api),
        {"credentials": {}, "task_id": "course"},
        cases,
        {"source_sha256": "frozen"},
        {"AGENT_DATABASE_URL": "fixture"},
        output,
    )
    record = json.loads((output / "failed-turn-1.private.json").read_text())
    assert (
        record["run"]["status"] == "failed" and record["semantic_review"] == "pending"
    )
    assert len(starts) == 1 and not (output / "failed-turn-2.private.json").exists()
    assert observed_options == ["-c default_transaction_read_only=on"]
