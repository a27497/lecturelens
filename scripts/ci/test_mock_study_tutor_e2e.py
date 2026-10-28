"""Harness safety/contract checks; the sibling integration script tests real services."""

import argparse
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


if __name__ == "__main__":
    unittest.main()
