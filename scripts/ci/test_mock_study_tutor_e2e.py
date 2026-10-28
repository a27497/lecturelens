"""Harness safety/contract checks; the sibling integration script tests real services."""

import argparse
import copy
import importlib.util
import io
import json
import os
import socket
import subprocess
import sys
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

SPEC = importlib.util.spec_from_file_location(
    "cross_service_smoke", Path(__file__).with_name("mock-study-tutor-e2e.py")
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class HarnessSafety(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        with patch.dict(
            os.environ, {"OPENAI_API_KEY": "caller-secret", "JAVA_TOOL_OPTIONS": "caller-options"}
        ):
            self.smoke = MODULE.Smoke(
                argparse.Namespace(
                    output_dir=Path(self.temp.name) / "run",
                    legacy_only=False,
                    embedding_cache_source=None,
                )
            )

    def test_existing_project_refused_without_claiming_or_cleanup(self):
        def capture(command):
            return "baseline" if command[0] == "git" else "existing-container"

        with (
            patch.object(self.smoke, "capture", side_effect=capture),
            self.assertRaisesRegex(AssertionError, "Refuse existing container"),
        ):
            self.smoke.preflight()
        self.assertEqual(self.smoke.owned, [])

    def test_config_ignores_inherited_credentials_and_falls_back_from_busy_port(self):
        with socket.socket() as occupied:
            occupied.bind(("127.0.0.1", 0))
            busy = occupied.getsockname()[1]
            with (
                patch.dict(MODULE.PORTS, {"APP_PORT": busy}),
                patch.object(self.smoke, "capture", return_value=""),
            ):
                self.smoke.preflight()
        self.assertNotEqual(self.smoke.result["ports"]["APP_PORT"], busy)
        public = (self.smoke.out / "public.env").read_text()
        for secret in self.smoke.private:
            self.assertNotIn(secret, public)
        self.assertNotIn("AGENT_DATABASE_URL=", public)
        self.assertEqual(self.smoke.env["AGENT_LLM_MODE"], "mock")
        self.assertIn(str(MODULE.ROOT), self.smoke.env["PYTHONPATH"].split(os.pathsep))
        self.assertEqual(self.smoke.env["SERVER_ADDRESS"], "127.0.0.1")
        self.assertNotIn("OPENAI_API_KEY", self.smoke.env)
        self.assertNotIn("JAVA_TOOL_OPTIONS", self.smoke.env)
        override = (self.smoke.out / "loopback.compose.yaml").read_text()
        self.assertEqual(override.count("127.0.0.1:"), 9)
        self.assertTrue(
            all(
                line.strip().startswith('- "127.0.0.1:')
                for line in override.splitlines()
                if line.strip().startswith("- ")
            )
        )

    def test_agent_launch_uses_test_factory_from_agent_working_directory(self):
        self.smoke.result["ports"] = {"AGENT_HTTP_PORT": 28092}
        self.smoke.agent_base = "http://127.0.0.1:28092"
        with (
            patch.object(self.smoke, "free_port"),
            patch.object(self.smoke, "spawn") as spawn,
            patch.object(self.smoke, "health"),
        ):
            self.smoke.start_agent()
        command, name, cwd = spawn.call_args.args
        self.assertIn("scripts.ci.tutor_hold_app:create_app", command)
        self.assertIn("--factory", command)
        self.assertEqual(cwd, MODULE.ROOT / "agent-service")
        self.assertEqual(name, "agent")

    def test_real_provider_template_is_rejected_before_startup(self):
        original = Path.read_text

        def read(path, *args, **kwargs):
            text = original(path, *args, **kwargs)
            if path.name == ".env.demo.example":
                return text.replace("OPENAI_COMPATIBLE_ENABLED=false", "OPENAI_COMPATIBLE_ENABLED=true")
            return text

        with (
            patch.object(Path, "read_text", read),
            patch.object(self.smoke, "capture", return_value=""),
            self.assertRaisesRegex(AssertionError, "OPENAI_COMPATIBLE_ENABLED must be false"),
        ):
            self.smoke.preflight()
        self.assertEqual(self.smoke.owned, [])
        self.assertEqual(self.smoke.children, [])

    def test_restart_port_probe_allows_time_wait_but_refuses_listener(self):
        with socket.socket() as server, socket.socket() as client:
            server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server.bind(("127.0.0.1", 0))
            port = server.getsockname()[1]
            server.listen(1)
            with self.assertRaises(OSError):
                self.smoke.free_port(port)
            client.connect(("127.0.0.1", port))
            accepted, _ = server.accept()
            accepted.close()
            client.close()
            server.close()
            self.assertEqual(self.smoke.free_port(port), port)

    def test_child_logs_are_redacted_before_persistence(self):
        secret = "private-test-secret-12345"
        jwt = "eyJtest.encoded.signature"
        self.smoke.private.append(secret)
        env = dict(os.environ, SMOKE_TEST_VALUE=secret)
        process = self.smoke.spawn(
            [
                sys.executable,
                "-c",
                'import os; print(os.environ["SMOKE_TEST_VALUE"]); print("eyJtest.encoded.signature")',
            ],
            "redaction",
            env=env,
        )
        process.wait(timeout=10)
        self.smoke.stop(process)
        log = (self.smoke.out / "redaction.log").read_text()
        self.assertNotIn(secret, log)
        self.assertNotIn(jwt, log)
        self.assertIn("[REDACTED]", log)
        self.assertIn("[JWT REDACTED]", log)

    def test_agent_guard_blocks_external_connect_and_marks_activation(self):
        guard = Path(self.temp.name) / "guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(MODULE.NETWORK_GUARD)
        active = Path(self.temp.name) / "active.log"
        denied = Path(self.temp.name) / "denied.log"
        env = dict(
            os.environ,
            PYTHONPATH=str(guard),
            SMOKE_GUARD_ACTIVE_LOG=str(active),
            SMOKE_DENIED_NETWORK_LOG=str(denied),
        )
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                'import socket; socket.socket().connect(("192.0.2.1", 443))',
            ],
            env=env,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(active.read_text().splitlines(), ["ACTIVE"])
        self.assertEqual(denied.read_text().splitlines(), ["DENIED_NON_LOOPBACK_CONNECT"])
        self.assertIn("Smoke forbids", result.stderr)

    def test_cross_account_records_actual_status_and_rejects_unexpected_denial(self):
        self.smoke.base = "http://127.0.0.1:1"
        error = urllib.error.HTTPError(
            self.smoke.base,
            403,
            "Forbidden",
            {},
            io.BytesIO(json.dumps({"code": "denied"}).encode()),
        )
        with (
            patch.object(self.smoke.http, "open", side_effect=error),
            self.assertRaisesRegex(AssertionError, "HTTP 403, expected 404"),
        ):
            self.smoke.api("GET", "/tutor", expected=404)
        self.assertEqual(self.smoke.result["cross_account"]["GET /tutor"], 403)

    def test_cancelled_requires_terminal_status_and_empty_publication(self):
        turn = {
            "status": "cancelled", "answer": None, "citations": [],
            "model_calls": 0, "tool_calls": 0,
        }
        for answer in (None, ""):
            with self.subTest(answer=answer):
                self.smoke.cancelled({**turn, "answer": answer}, "API")
        for change, message in (
            ({"status": "completed"}, "changed status"),
            ({"answer": "late answer"}, "published an answer"),
            ({"citations": [{"evidence_id": "synthetic"}]}, "published citations"),
        ):
            with self.subTest(change=change), self.assertRaisesRegex(AssertionError, message):
                self.smoke.cancelled({**turn, **change}, "API")

    def test_queued_cancel_rejects_nonqueued_submission_and_records_actual_status(self):
        for status in ("running", "completed"):
            with (
                self.subTest(status=status),
                patch.object(
                    self.smoke, "ask",
                    return_value={"turns": [{"client_turn_id": "cancel-now", "status": status}]},
                ) as ask,
                patch.object(self.smoke, "api") as cancel,
                patch.object(self.smoke, "turn") as poll,
                patch.object(self.smoke, "sql") as sql,
            ):
                with self.assertRaisesRegex(AssertionError, f"status_at_submission='{status}'"):
                    self.smoke.queued_cancel()
                ask.assert_called_once_with("cancel-now")
                cancel.assert_not_called()
                poll.assert_not_called()
                sql.assert_not_called()
                self.smoke.save()
                evidence = json.loads((self.smoke.out / "result.json").read_text())
                self.assertEqual(evidence["queued_cancel"]["status_at_submission"], status)

    def test_queued_cancel_checks_api_and_pg_and_records_evidence(self):
        self.smoke.session_path = "/synthetic/session"
        self.smoke.owner = "123"
        self.smoke.task = "task_" + "a" * 32
        turn = {
            "client_turn_id": "cancel-now", "status": "cancelled", "answer": None,
            "citations": [], "model_calls": 0, "tool_calls": 0,
        }
        row = {**turn, "deadline": None, "checkpoint_phase": "ready"}
        for boundary, field, value, message in (
            (None, None, None, None),
            ("api", "status", "completed", "API:.*changed status"),
            ("api", "answer", "late answer", "published an answer"),
            ("api", "citations", [{"evidence_id": "synthetic"}], "published citations"),
            ("api", "model_calls", 1, "API:.*model_calls=1"),
            ("api", "tool_calls", 1, "API:.*tool_calls=1"),
            ("pg", "status", "completed", "PG:.*changed status"),
            ("pg", "answer", "late answer", "published an answer"),
            ("pg", "citations", [{"evidence_id": "synthetic"}], "published citations"),
            ("pg", "model_calls", 1, "PG:.*model_calls=1"),
            ("pg", "tool_calls", 1, "PG:.*tool_calls=1"),
        ):
            api_turn, pg_turn = dict(turn), dict(row)
            if boundary:
                (api_turn if boundary == "api" else pg_turn)[field] = value
            with (
                self.subTest(boundary=boundary, field=field),
                patch.object(self.smoke, "ask", return_value={"turns": [{**turn, "status": "queued"}]}),
                patch.object(self.smoke, "api") as cancel,
                patch.object(self.smoke, "turn", return_value=api_turn) as poll,
                patch.object(self.smoke, "sql", return_value=json.dumps([pg_turn])) as sql,
            ):
                if message:
                    with self.assertRaisesRegex(AssertionError, message):
                        self.smoke.queued_cancel()
                    continue
                self.smoke.queued_cancel()
                cancel.assert_called_once_with("POST", "/synthetic/session/turns/cancel-now/cancel")
                poll.assert_called_once_with("cancel-now", "cancelled")
                self.assertTrue(sql.call_args.kwargs["pg"])
                evidence = self.smoke.result["queued_cancel"]
                self.assertEqual(evidence["status_at_submission"], "queued")
                self.assertIsNone(evidence["status_at_cancel_time"])
                self.assertEqual(evidence["turn"], turn)
                self.assertEqual(evidence["pg_rows"], [row])

    def test_running_cancel_is_a_required_stage(self):
        self.assertIn("Tutor-queued-cancel", MODULE.STAGES)
        self.assertIn("Tutor-running-cancel", MODULE.STAGES)
        self.assertFalse(any("Tutor-running-cancel" in reason for reason in self.smoke.result["not_run"]))

    def running_setup(self):
        self.smoke.session_path = "/synthetic/session"
        self.smoke.hold = self.smoke.out / "hold"
        self.smoke.hold.mkdir()
        running = {
            "status": "running", "answer": None, "citations": [],
            "model_calls": 1, "tool_calls": 0,
            "deadline": "2026-10-28T12:00:20Z", "checkpoint_phase": "reserved",
        }
        cancelled = {**running, "status": "cancelled"}
        return {"api": dict(running), "pg": dict(running)}, {
            "api": dict(cancelled), "pg": dict(cancelled),
        }

    def test_marker_wait_requires_entered_before_polling_running(self):
        self.smoke.hold = self.smoke.out
        with patch.object(self.smoke, "turn") as turn:
            with self.assertRaisesRegex(AssertionError, "entered marker"):
                self.smoke.wait(lambda: (self.smoke.hold / "entered").is_file(), bool, 0, "entered marker")
            turn.assert_not_called()
            (self.smoke.hold / "entered").touch()
            self.smoke.wait_for_running()
            turn.assert_called_once_with("cancel-running", "running")

    def test_running_cancel_rejects_nonrunning_boundary_even_without_wait(self):
        running, _ = self.running_setup()
        for boundary in ("api", "pg"):
            observation = copy.deepcopy(running)
            observation[boundary]["status"] = "queued"
            with (
                self.subTest(boundary=boundary),
                patch.object(self.smoke, "ask"),
                patch.object(self.smoke, "wait_for_running", side_effect=lambda: (self.smoke.hold / "entered").write_text("123")),
                patch.object(self.smoke, "observe_running_cancel", return_value=observation),
                patch.object(self.smoke, "api") as cancel,
            ):
                (self.smoke.hold / "entered").touch()
                with self.assertRaisesRegex(AssertionError, "status_at_cancel_time='queued'"):
                    self.smoke.running_cancel()
                cancel.assert_not_called()
                self.assertEqual(self.smoke.result["running_cancel"]["at_cancel"], observation)
                self.assertTrue((self.smoke.hold / "release").is_file())
                self.assertFalse((self.smoke.hold / "arm").exists())

    def test_running_requires_deadline_reserved_checkpoint_and_actual_counters(self):
        running, _ = self.running_setup()
        for boundary, field, value in (
            ("pg", "deadline", None), ("pg", "checkpoint_phase", "ready"),
            ("api", "model_calls", 0), ("pg", "model_calls", 0),
            ("api", "tool_calls", 1), ("pg", "tool_calls", 1),
        ):
            observation = copy.deepcopy(running)
            observation[boundary][field] = value
            with self.subTest(boundary=boundary, field=field), self.assertRaises(AssertionError):
                self.smoke.assert_running_at_cancel(observation)

    def test_running_cancel_stability_and_followup(self):
        running, cancelled = self.running_setup()
        followup = {"status": "completed", "answer": "normal"}

        def entered():
            self.assertTrue((self.smoke.hold / "arm").is_file())
            self.assertFalse((self.smoke.hold / "release").exists())
            (self.smoke.hold / "entered").write_text("123")

        def cancel(*args):
            self.assertEqual(args, ("POST", "/synthetic/session/turns/cancel-running/cancel"))
            self.assertFalse((self.smoke.hold / "release").exists())

        with (
            patch.object(self.smoke, "ask") as ask,
            patch.object(self.smoke, "wait_for_running", side_effect=entered),
            patch.object(self.smoke, "observe_running_cancel", side_effect=[running, cancelled, cancelled]),
            patch.object(self.smoke, "api", side_effect=cancel),
            patch.object(self.smoke, "turn", return_value=followup),
            patch.object(self.smoke, "answer") as answer,
            patch.object(MODULE.time, "sleep") as sleep,
        ):
            self.smoke.running_cancel()
        sleep.assert_called_once_with(3)
        self.assertEqual([c.args for c in ask.call_args_list], [("cancel-running",), ("after-running-cancel",)])
        answer.assert_called_once_with(followup)
        evidence = self.smoke.result["running_cancel"]
        self.assertEqual(evidence["status_at_cancel_time"], "running")
        self.assertEqual(evidence["pg_status_at_cancel_time"], "running")
        self.assertEqual(evidence["stable"], cancelled)
        self.assertEqual(evidence["entered"], "123")
        self.assertFalse((self.smoke.hold / "arm").exists())

    def test_running_cancel_rejects_late_publication_at_both_observations(self):
        running, cancelled = self.running_setup()
        for phase in ("after_release", "stable"):
            for boundary in ("api", "pg"):
                for field, value in (
                    ("status", "completed"), ("answer", "late answer"),
                    ("citations", [{"evidence_id": "e1"}]),
                    ("model_calls", 0), ("tool_calls", 1),
                ):
                    bad = copy.deepcopy(cancelled)
                    bad[boundary][field] = value
                    observations = [running, bad] if phase == "after_release" else [running, cancelled, bad]
                    with (
                        self.subTest(phase=phase, boundary=boundary, field=field),
                        patch.object(self.smoke, "ask") as ask,
                        patch.object(self.smoke, "wait_for_running", side_effect=lambda: (self.smoke.hold / "entered").write_text("123")),
                        patch.object(self.smoke, "observe_running_cancel", side_effect=observations),
                        patch.object(self.smoke, "api"),
                        patch.object(self.smoke, "turn"),
                        patch.object(MODULE.time, "sleep"),
                    ):
                        with self.assertRaises(AssertionError):
                            self.smoke.running_cancel()
                        self.assertEqual(self.smoke.result["running_cancel"][phase], bad)
                        ask.assert_called_once_with("cancel-running")


if __name__ == "__main__":
    unittest.main()
