"""Exercise the test wrapper through the real app lifespan and runtime provider."""

import json
import os
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from lecturelens_real_eval.tutor import app as tutor_app
from lecturelens_real_eval.tutor.runtime import MockTutor, TutorRuntime

from scripts.ci import tutor_hold_app

MESSAGES = [{"content": json.dumps({
    "observations": [], "history": [], "summary": "", "learner_text": "explain",
})}]
EXPECTED = MockTutor().decide(MESSAGES, [], 1)


class HoldFactory(unittest.TestCase):
    def test_refuses_non_mock(self):
        for mode in (None, "real", "MOCK", ""):
            with self.subTest(mode=mode), patch.dict(os.environ, {}, clear=True):
                if mode is not None:
                    os.environ["AGENT_LLM_MODE"] = mode
                with self.assertRaisesRegex(RuntimeError, "REQUIRES_MOCK"):
                    tutor_hold_app.create_app()

    def provider(self, directory):
        self.enterContext(patch.dict(os.environ, {
            "AGENT_LLM_MODE": "mock", "TUTOR_ENABLED": "true",
            "STUDY_AGENT_ENABLED": "false", "AGENT_DATABASE_URL": "unused",
            "TUTOR_MOCK_TEST_HOLD_DIR": str(directory),
        }))
        self.enterContext(patch.object(tutor_app, "TutorStore"))
        for method in ("initialize", "start", "close"):
            self.enterContext(patch.object(TutorRuntime, method))
        app = tutor_hold_app.create_app(retriever=object(), secret="s" * 32)
        self.enterContext(TestClient(app))
        return app.state.tutor.provider

    def test_installed_provider_handshake_and_followup(self):
        with tempfile.TemporaryDirectory() as directory:
            hold = Path(directory)
            provider = self.provider(hold)
            self.assertIsNot(type(provider), MockTutor)
            (hold / "arm").touch()
            results = []
            thread = threading.Thread(target=lambda: results.append(provider.decide(MESSAGES, [], 1)))
            thread.start()
            try:
                deadline = time.monotonic() + 2
                while not (hold / "entered").is_file() and time.monotonic() < deadline:
                    time.sleep(0.01)
                self.assertTrue((hold / "entered").is_file())
                self.assertTrue(thread.is_alive())
                self.assertEqual(results, [])
            finally:
                (hold / "arm").unlink(missing_ok=True)
                (hold / "release").touch()
                thread.join(2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(results, [EXPECTED])
            (hold / "release").unlink()
            (hold / "entered").unlink()
            self.assertEqual(provider.decide(MESSAGES, [], 1), EXPECTED)
            self.assertFalse((hold / "entered").exists())

    def test_timeout_resumes_normal_payload_within_ten_seconds(self):
        with tempfile.TemporaryDirectory() as directory:
            hold = Path(directory)
            provider = self.provider(hold)
            (hold / "arm").touch()
            started = time.monotonic()
            self.assertEqual(provider.decide(MESSAGES, [], 1), EXPECTED)
            elapsed = time.monotonic() - started
            self.assertGreaterEqual(elapsed, 10)
            self.assertLess(elapsed, 10.5)
            self.assertTrue((hold / "entered").is_file())

    def test_default_provider_restored_after_lifespan(self):
        with tempfile.TemporaryDirectory() as directory:
            self.provider(Path(directory))
            self.doCleanups()
            from lecturelens_real_eval.tutor import runtime
            self.assertIs(runtime.MockTutor, MockTutor)


if __name__ == "__main__":
    unittest.main()
