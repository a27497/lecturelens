"""Ownership, locking, teardown and course-reuse checks for scripts/demo/stack.py.

No Docker, services or model calls: Docker and the Java API are offline fakes.

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
SECRETS = (
    '{"MYSQL_ROOT_PASSWORD": "x", "MYSQL_PASSWORD": "x", "REDIS_PASSWORD": "x",'
    ' "MINIO_ROOT_USER": "x", "MINIO_ROOT_PASSWORD": "x", "AGENT_POSTGRES_PASSWORD": "x",'
    ' "DEMO_PASSWORD": "x"}'
)
REAL = {"mode": "real", "model": "deepseek-flash", "java_base_url": "https://api.deepseek.com"}


def completed(stdout="", returncode=0):
    return subprocess.CompletedProcess([], returncode, stdout=stdout, stderr="")


class FakeDocker:
    """Answers `docker ps -a` / `docker volume ls` for the whole daemon; records every command.

    Each resource is (kind, name, owner label, Compose project label); "" means the label is absent.
    """

    def __init__(self, resources):
        self.resources = list(resources)
        self.calls = []

    def __call__(self, command, **kwargs):
        self.calls.append(command)
        if command[:2] == ["docker", "ps"] or command[:3] == ["docker", "volume", "ls"]:
            kind = "container" if command[1] == "ps" else "volume"
            rows = [f"{n}\t{o}\t{p}" for k, n, o, p in self.resources if k == kind]
            return completed("\n".join(rows))
        if "down" in command and "-v" in command:
            project = command[command.index("-p") + 1]
            self.resources = [r for r in self.resources if r[3] != project]
        return completed()

    def compose_downs(self):
        return [call[call.index("-p") + 1] for call in self.calls if "down" in call]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        for name, value in (
            ("ROOT", Path(self.tmp.name) / "clone-a"),
            ("LOCK_DIR", Path(self.tmp.name) / "locks"),
        ):
            patcher = mock.patch.object(stack, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.stack = stack.Stack("t1")
        self.stack.state = {"owner": OWNER, "pids": {}}
        self.stack.dir.mkdir(parents=True)
        (self.stack.dir / "compose.env").write_text("")
        (self.stack.dir / "secrets.json").write_text(SECRETS)


class OwnershipTest(Base):
    def test_only_demo_projects_of_this_instance_are_managed(self):
        for project in ("lecturelens-dev", "lecturelens-dev-mysql-1", "lecturelens-demo-other"):
            with self.assertRaises(RuntimeError):
                self.stack.check_project(project)
        self.stack.check_project("lecturelens-demo-t1")
        self.stack.check_project("lecturelens-demoagent-t1")

    def test_unlabelled_volume_with_the_expected_name_is_foreign(self):
        # Neither an owner nor a Compose project label: only the exact name links it to the project.
        docker = FakeDocker([("volume", "lecturelens-demo-t1_mysql_data", "", "")])
        with mock.patch.object(stack.subprocess, "run", docker):
            self.assertEqual(
                self.stack.foreign_resources("lecturelens-demo-t1"), ["volume lecturelens-demo-t1_mysql_data"]
            )
            self.assertEqual(self.stack.foreign_resources("lecturelens-demoagent-t1"), [])

    def test_unlabelled_container_with_the_expected_name_is_foreign(self):
        docker = FakeDocker([("container", "lecturelens-demoagent-t1-postgres-1", "", "")])
        with mock.patch.object(stack.subprocess, "run", docker):
            self.assertEqual(
                self.stack.foreign_resources("lecturelens-demoagent-t1"),
                ["container lecturelens-demoagent-t1-postgres-1"],
            )

    def test_project_labelled_resources_without_this_owner_are_foreign(self):
        docker = FakeDocker(
            [
                ("container", "lecturelens-demo-t1-mysql-1", OWNER, "lecturelens-demo-t1"),
                ("container", "quickstart-extra", "", "lecturelens-demo-t1"),
                ("volume", "other-clone-data", "b" * 32, "lecturelens-demo-t1"),
                ("volume", "lecturelens-dev_mysql_data", "", "lecturelens-dev"),
            ]
        )
        with mock.patch.object(stack.subprocess, "run", docker):
            self.assertEqual(
                self.stack.foreign_resources("lecturelens-demo-t1"),
                ["container quickstart-extra", "volume other-clone-data"],
            )

    def test_without_an_owner_id_everything_is_foreign(self):
        self.stack.state.pop("owner")
        docker = FakeDocker([("volume", "lecturelens-demo-t1_redis_data", OWNER, "lecturelens-demo-t1")])
        with mock.patch.object(stack.subprocess, "run", docker):
            self.assertEqual(
                self.stack.foreign_resources("lecturelens-demo-t1"), ["volume lecturelens-demo-t1_redis_data"]
            )

    def test_docker_errors_are_not_empty_results(self):
        with mock.patch.object(stack.subprocess, "run", return_value=completed("", returncode=1)):
            with self.assertRaises(RuntimeError):
                self.stack.foreign_resources("lecturelens-demo-t1")

    def test_up_preflight_refuses_an_unlabelled_volume_with_the_expected_name(self):
        docker = FakeDocker([("volume", "lecturelens-demo-t1_minio_data", "", "")])
        with mock.patch.object(stack.subprocess, "run", docker):
            with self.assertRaises(SystemExit):
                self.stack.check_projects_free()
        self.assertEqual(docker.compose_downs(), [])

    def test_up_preflight_accepts_an_empty_daemon_and_own_stopped_resources(self):
        docker = FakeDocker([("volume", "lecturelens-demo-t1_minio_data", OWNER, "lecturelens-demo-t1")])
        with mock.patch.object(stack.subprocess, "run", docker):
            self.stack.check_projects_free()

    def test_purge_with_an_unlabelled_expected_volume_removes_nothing_and_keeps_state(self):
        docker = FakeDocker(
            [
                ("container", "lecturelens-demoagent-t1-postgres-1", OWNER, "lecturelens-demoagent-t1"),
                ("volume", "lecturelens-demo-t1_mysql_data", "", ""),
            ]
        )
        with mock.patch.object(stack.subprocess, "run", docker), mock.patch.object(stack.Stack, "lock"):
            with self.assertRaises(SystemExit):
                self.stack.down(purge=True)
        self.assertEqual(docker.compose_downs(), [])
        self.assertTrue(self.stack.dir.exists())

    def test_purge_keeps_state_until_expected_volumes_are_gone(self):
        # The volume is owned but Compose leaves it behind (for example still in use).
        docker = FakeDocker([("volume", "lecturelens-demo-t1_mysql_data", OWNER, "")])
        with mock.patch.object(stack.subprocess, "run", docker), mock.patch.object(stack.Stack, "lock"):
            with self.assertRaises(SystemExit):
                self.stack.down(purge=True)
        self.assertEqual(docker.compose_downs(), ["lecturelens-demoagent-t1", "lecturelens-demo-t1"])
        self.assertTrue((self.stack.dir / "secrets.json").exists())

    def test_purge_deletes_local_state_once_volumes_are_gone(self):
        docker = FakeDocker([("volume", "lecturelens-demo-t1_mysql_data", OWNER, "lecturelens-demo-t1")])
        with mock.patch.object(stack.subprocess, "run", docker), mock.patch.object(stack.Stack, "lock"):
            self.stack.down(purge=True)
        self.assertFalse(self.stack.dir.exists())

    def test_a_hung_first_project_does_not_skip_the_second(self):
        docker = FakeDocker([])

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
        self.assertEqual(infra.count(label), len(stack.INFRA_SERVICES) + len(stack.INFRA_VOLUMES))
        self.assertEqual(agent.count(label), len(stack.AGENT_SERVICES) + len(stack.AGENT_VOLUMES))


class LockTest(Base):
    def test_two_clones_cannot_preflight_the_same_instance_at_once(self):
        first = self.stack
        with mock.patch.object(stack, "ROOT", Path(self.tmp.name) / "clone-b"):
            second = stack.Stack("t1")
        self.assertNotEqual(first.dir, second.dir)
        self.assertEqual(first.lock_file, second.lock_file)
        first.lock()
        with self.assertRaises(SystemExit):
            second.lock()
        # Another instance name has its own lock.
        stack.Stack("t2").lock()

    def test_the_lock_is_outside_every_clone(self):
        self.assertFalse(self.stack.lock_file.is_relative_to(stack.ROOT))


class SeedTest(Base):
    """seed() against an offline Java API; any upload means a new (possibly paid) import."""

    def seed(self, status, *, prepared=REAL, active=REAL):
        self.stack.state.update(task_id="task_1", course_identity=prepared, model_identity=active)
        calls = []

        def api(method, path, body=None, token=None, content_type=None):
            calls.append((method, path))
            if path == "/api/auth/login":
                return {"accessToken": "t"}
            if path == "/api/auth/register":
                return None
            if path == "/api/tasks/task_1":
                if isinstance(status, BaseException):
                    raise status
                return {"status": status}
            if path.startswith("/api/uploads"):
                raise AssertionError("new upload")
            raise AssertionError(path)

        with mock.patch.object(self.stack, "api", api), mock.patch.object(self.stack, "wait_index") as wait:
            try:
                self.stack.seed({"DEMO_PASSWORD": "x"})
                outcome = "reused"
            except SystemExit:
                outcome = "refused"
            except AssertionError as error:
                outcome = str(error)
        return outcome, wait.called, calls

    def test_running_queued_or_unreadable_tasks_are_refused_without_an_upload(self):
        for status in (
            "QUEUED",
            "RUNNING",
            "CREATED",
            "RETRYING",
            RuntimeError("GET /api/tasks/task_1: HTTP 503 code=None"),
            OSError("timed out"),
        ):
            with self.subTest(status=status):
                outcome, waited, calls = self.seed(status)
                self.assertEqual(outcome, "refused")
                self.assertFalse(waited)
                self.assertFalse(any(path.startswith("/api/uploads") for _, path in calls))

    def test_succeeded_course_from_another_model_is_not_reused_or_reimported(self):
        for prepared in ({**REAL, "model": "other-model"}, {"mode": "mock"}, None):
            with self.subTest(prepared=prepared):
                outcome, waited, _ = self.seed("SUCCEEDED", prepared=prepared)
                self.assertEqual(outcome, "refused")
                self.assertFalse(waited)

    def test_succeeded_course_from_the_same_model_is_reused(self):
        outcome, waited, _ = self.seed("SUCCEEDED")
        self.assertEqual(outcome, "reused")
        self.assertTrue(waited)

    def test_only_failed_or_canceled_tasks_are_replaced(self):
        for status in ("FAILED", "CANCELED"):
            with self.subTest(status=status):
                self.assertEqual(self.seed(status)[0], "new upload")

    def test_identity_names_the_java_model_and_endpoint(self):
        with mock.patch.dict(
            os.environ,
            {"LECTURELENS_LLM_MODEL": "m1", "LECTURELENS_LLM_BASE_URL": "https://a.example/"},
            clear=False,
        ):
            os.environ.pop("LECTURELENS_JAVA_LLM_BASE_URL", None)
            self.assertEqual(
                stack.model_identity(True),
                {"mode": "real", "model": "m1", "java_base_url": "https://a.example"},
            )
        self.assertEqual(stack.model_identity(False), {"mode": "mock"})


class MiscTest(Base):
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
