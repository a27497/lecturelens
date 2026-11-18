"""Ownership and teardown checks for scripts/demo/stack.py without Docker or services.

python3 -m unittest discover -s scripts/demo/tests -p 'test_*.py' -v
"""

import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import stack  # noqa: E402

OWNER = "a" * 32


def completed(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class FakeDocker:
    """Answers `docker ps -a` / `docker volume ls` per project; records every other command."""

    def __init__(self, resources):
        self.resources = resources  # project -> list of (kind, name, owner label value)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[:2] in (["docker", "ps"], ["docker", "volume"]):
            project = next(arg.rsplit("=", 1)[1] for arg in command if arg.startswith("label=com.docker"))
            kind = "container" if command[1] == "ps" else "volume"
            rows = [f"{name}\t{owner}" for k, name, owner in self.resources.get(project, []) if k == kind]
            return completed("\n".join(rows))
        return completed()

    def compose_downs(self):
        return [call[call.index("-p") + 1] for call in self.calls if "down" in call]


class StackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        patcher = mock.patch.object(stack, "ROOT", Path(self.tmp.name))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.addCleanup(self.tmp.cleanup)
        self.stack = stack.Stack("t1")
        self.stack.state = {"owner": OWNER, "pids": {}}
        self.stack.dir.mkdir(parents=True)
        (self.stack.dir / "compose.env").write_text("")
        (self.stack.dir / "secrets.json").write_text(
            '{"MYSQL_ROOT_PASSWORD": "x", "MYSQL_PASSWORD": "x", "REDIS_PASSWORD": "x",'
            ' "MINIO_ROOT_USER": "x", "MINIO_ROOT_PASSWORD": "x", "AGENT_POSTGRES_PASSWORD": "x"}'
        )

    def test_only_demo_projects_of_this_instance_are_managed(self):
        for project in ("lecturelens-dev", "lecturelens-dev-mysql-1", "lecturelens-demo-other"):
            with self.assertRaises(RuntimeError):
                self.stack.check_project(project)
        self.stack.check_project("lecturelens-demo-t1")
        self.stack.check_project("lecturelens-demoagent-t1")

    def test_resources_without_this_owner_are_foreign(self):
        docker = FakeDocker(
            {
                "lecturelens-demo-t1": [
                    ("container", "mine", OWNER),
                    ("container", "quickstart-mysql", ""),
                    ("volume", "other-clone-data", "b" * 32),
                ]
            }
        )
        with mock.patch.object(stack.subprocess, "run", docker):
            self.assertEqual(
                self.stack.foreign_resources("lecturelens-demo-t1"),
                ["container quickstart-mysql", "volume other-clone-data"],
            )
            self.assertEqual(self.stack.foreign_resources("lecturelens-demoagent-t1"), [])

    def test_without_an_owner_id_everything_is_foreign(self):
        self.stack.state.pop("owner")
        docker = FakeDocker({"lecturelens-demo-t1": [("volume", "data", OWNER)]})
        with mock.patch.object(stack.subprocess, "run", docker):
            self.assertEqual(self.stack.foreign_resources("lecturelens-demo-t1"), ["volume data"])

    def test_docker_errors_are_not_empty_results(self):
        with mock.patch.object(stack.subprocess, "run", return_value=completed("", returncode=1)):
            with self.assertRaises(RuntimeError):
                self.stack.foreign_resources("lecturelens-demo-t1")

    def test_purge_skips_a_project_with_foreign_resources_and_still_handles_the_other(self):
        docker = FakeDocker({"lecturelens-demo-t1": [("volume", "lecturelens-demo-t1_mysql_data", "")]})
        with mock.patch.object(stack.subprocess, "run", docker):
            failures = self.stack.teardown(purge=True)
        self.assertEqual(docker.compose_downs(), ["lecturelens-demoagent-t1"])
        self.assertEqual(len(failures), 1)
        self.assertIn("lecturelens-demo-t1", failures[0])
        self.assertIn("nothing removed", failures[0])

    def test_a_hung_first_project_does_not_skip_the_second(self):
        docker = FakeDocker({})

        def run(command, **kwargs):
            if "down" in command and "lecturelens-demoagent-t1" in command:
                docker.calls.append(command)
                raise subprocess.TimeoutExpired(command, 300)
            return docker(command, **kwargs)

        with mock.patch.object(stack.subprocess, "run", run):
            failures = self.stack.teardown(purge=False)
        self.assertEqual(docker.compose_downs(), ["lecturelens-demoagent-t1", "lecturelens-demo-t1"])
        self.assertEqual(len(failures), 1)
        self.assertIn("lecturelens-demoagent-t1", failures[0])

    def test_every_generated_service_and_volume_carries_the_owner_label(self):
        self.stack.write_compose_files(dict(stack.DEFAULT_PORTS), {})
        infra = (self.stack.dir / "infra.override.yaml").read_text()
        agent = (self.stack.dir / "agent.override.yaml").read_text()
        label = f'{stack.OWNER_LABEL}: "{OWNER}"'
        self.assertEqual(infra.count(label), len(stack.CONTAINER_MEMORY) - 1 + len(stack.INFRA_VOLUMES))
        self.assertEqual(agent.count(label), 1 + len(stack.AGENT_VOLUMES))

    def test_stop_command_always_names_the_instance(self):
        self.assertEqual(stack.Stack("default").stop_command, "scripts/demo/down.sh --instance default")

    @unittest.skipUnless(Path("/proc/self/stat").exists(), "Linux identity path")
    def test_process_identity_ignores_time_zone(self):
        first = stack.Stack.start_time(os.getpid())
        with mock.patch.dict(os.environ, {"TZ": "America/Los_Angeles", "LC_ALL": "C"}):
            self.assertEqual(stack.Stack.start_time(os.getpid()), first)
        self.assertTrue(first.startswith("linux:"))


if __name__ == "__main__":
    unittest.main()
