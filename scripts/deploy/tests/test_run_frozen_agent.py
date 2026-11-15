import importlib.util
from pathlib import Path
import unittest


spec = importlib.util.spec_from_file_location(
    "frozen_agent", Path(__file__).parents[1] / "run_frozen_agent.py"
)
module = importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)


class FrozenLauncherTests(unittest.TestCase):
    def test_only_release_paths_and_feedback_change(self):
        argv = ["/old/python", "-m", "uvicorn", "lecturelens_agent.app:create_app", "--port", "8090"]
        env = {"PYTHONPATH": "/old/src", "STUDY_FEEDBACK_ENABLED": "false", "STUDY_AGENT_ENABLED": "true", "OPAQUE": object()}
        command, forwarded = module.frozen_command("/frozen/release", argv, env)
        self.assertEqual(command[1:], argv[1:])
        self.assertEqual(command[0], "/frozen/release/agent-service/.venv/bin/python")
        self.assertEqual(forwarded["PYTHONPATH"], "/frozen/release/agent-service/src")
        self.assertEqual(forwarded["STUDY_FEEDBACK_ENABLED"], "true")
        self.assertIs(forwarded["OPAQUE"], env["OPAQUE"])
        self.assertEqual(forwarded["STUDY_AGENT_ENABLED"], "true")
        self.assertEqual(env["STUDY_FEEDBACK_ENABLED"], "false")
        self.assertEqual(argv[0], "/old/python")

    def test_refuses_other_service_commands(self):
        with self.assertRaises(RuntimeError):
            module.frozen_command("/frozen/release", ["java", "-jar", "backend.jar"], {})


if __name__ == "__main__":
    unittest.main()
