import ctypes
import hashlib
import json
import os
import signal
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path

RUNNER = Path(__file__).resolve().parents[1] / "run_check.py"
FIXTURE = Path(__file__).with_name("process_fixture.py")


class ProcessCloseoutTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # If a regression breaks the tested supervisor, adopt and reap only these
        # newly created fixtures instead of leaving their zombies with PID 1.
        if ctypes.CDLL(None).prctl(36, 1, 0, 0, 0) != 0:
            raise RuntimeError("test subreaper unavailable")

    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix="lecturelens-process-test-")
        self.root = Path(self.temporary.name)
        self.processes = []

    def tearDown(self):
        # Emergency cleanup is limited to identities created by this test. A test
        # still fails if it needs this path; never signal pre-existing processes.
        for process, folder, journal in self.processes:
            if process.poll() is None:
                process.kill()
                process.wait(timeout=2)
            if journal.exists():
                for row in map(json.loads, journal.read_text().splitlines()):
                    path = Path(f"/proc/{row['pid']}/stat")
                    try:
                        fields = path.read_text().rsplit(")", 1)[1].split()
                        if int(fields[19]) == row["start_ticks"]:
                            fd = os.pidfd_open(row["pid"])
                            try:
                                signal.pidfd_send_signal(fd, signal.SIGKILL)
                            finally:
                                os.close(fd)
                    except (ProcessLookupError, FileNotFoundError):
                        pass
                deadline = time.monotonic() + 2
                while time.monotonic() < deadline:
                    try:
                        pid, _ = os.waitpid(-1, os.WNOHANG)
                    except ChildProcessError:
                        break
                    if not pid:
                        time.sleep(0.01)
        self.temporary.cleanup()

    def launch(
        self, mode="success", timeout=2, name="check", command=None, deny_signals=False
    ):
        folder = self.root / name
        journal = self.root / (name + "-pids.jsonl")
        argv = [
            sys.executable,
            str(RUNNER),
            "--name",
            name,
            "--cwd",
            str(self.root),
            "--output-root",
            str(self.root),
            "--timeout",
            str(timeout),
            "--grace-seconds",
            ".15",
            "--cleanup-seconds",
            "1",
            "--",
        ]
        argv += (
            command
            if command is not None
            else [sys.executable, str(FIXTURE), mode, str(journal)]
        )
        if deny_signals:
            # Simulate a privilege boundary without sudo or privileged children.
            bootstrap = (
                "import runpy,sys; scope=runpy.run_path(sys.argv.pop(1)); "
                "scope['signal'].pidfd_send_signal=lambda *a: "
                "(_ for _ in ()).throw(PermissionError()); sys.exit(scope['main']())"
            )
            argv = [sys.executable, "-c", bootstrap, str(RUNNER)] + argv[2:]
        environment = {
            key: os.environ[key]
            for key in ("PATH", "HOME", "LANG")
            if key in os.environ
        }
        environment["LECTURELENS_TEST_SENTINEL"] = (
            "synthetic-value-must-not-be-forwarded"
        )
        process = subprocess.Popen(
            argv,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=environment,
            start_new_session=True,
        )
        self.processes.append((process, folder, journal))
        return process, folder, journal

    def finish(self, handle, status, code):
        process, folder, journal = handle
        stdout, stderr = process.communicate(timeout=6)
        self.assertEqual(process.returncode, code, stderr.decode())
        record = json.loads((folder / "run.json").read_text())
        self.assertEqual(record["status"], status)
        self.assertEqual(record["exit_code"], code)
        self.assertIn("finished_at_utc", record)
        self.assertLess(record["elapsed_seconds"], 5)
        if "cleanup" in record:
            self.assertTrue(record["cleanup"]["complete"], record)
            self.assertEqual(record["cleanup"]["remaining"], [])
            self.assertFalse(Path(f"/proc/{record['child_pid']}").exists())
        if journal.exists():
            for row in map(json.loads, journal.read_text().splitlines()):
                self.assertFalse(Path(f"/proc/{row['pid']}").exists(), row)
        if (folder / "output.log").exists():
            digest = hashlib.sha256((folder / "output.log").read_bytes()).hexdigest()
            self.assertEqual(record["log_sha256"], digest)
        self.assertEqual(json.loads(stdout)["status"], status)
        self.assertEqual((folder / "run.json").stat().st_mode & 0o777, 0o600)
        return record

    def ready(self, handle, count=1):
        process, _folder, journal = handle
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            if journal.exists() and len(journal.read_text().splitlines()) >= count:
                record = json.loads((handle[1] / "run.json").read_text())
                fields = (
                    Path(f"/proc/{process.pid}/stat")
                    .read_text()
                    .rsplit(")", 1)[1]
                    .split()
                )
                self.assertEqual(record["status"], "RUNNING")
                self.assertEqual(record["runner_start_ticks"], int(fields[19]))
                return
            self.assertIsNone(process.poll())
            time.sleep(0.01)
        self.fail("fixture did not become ready")

    def test_success_has_eof_stdin_filtered_environment_and_private_output(self):
        handle = self.launch()
        record = self.finish(handle, "SUCCEEDED", 0)
        self.assertEqual(record["child_returncode"], 0)
        self.assertEqual((handle[1] / "output.log").read_text(), "synthetic-success\n")

    def test_failure_keeps_actual_exit_code(self):
        record = self.finish(self.launch("failure"), "FAILED", 7)
        self.assertEqual(record["child_returncode"], 7)

    def test_child_signal_exit_is_not_success(self):
        record = self.finish(self.launch("signal"), "FAILED", 128 + signal.SIGTERM)
        self.assertEqual(record["child_returncode"], -signal.SIGTERM)

    def test_spawn_error_has_terminal_record(self):
        record = self.finish(
            self.launch(command=["/nonexistent-lecturelens-test-command"]),
            "SPAWN_ERROR",
            127,
        )
        self.assertEqual(record["error_type"], "FileNotFoundError")

    def test_timeout_cleans_child(self):
        self.finish(self.launch("sleep", timeout=0.35), "TIMED_OUT", 124)

    def test_timeout_escalates_for_ignored_term(self):
        record = self.finish(self.launch("ignore", timeout=0.35), "TIMED_OUT", 124)
        self.assertIn("SIGKILL", record["cleanup"]["signals"])

    def test_stopped_child_cannot_hold_closeout(self):
        record = self.finish(self.launch("stopped", timeout=0.35), "TIMED_OUT", 124)
        self.assertIn("SIGKILL", record["cleanup"]["signals"])

    def test_successful_parent_does_not_leave_grandchild_or_zombie(self):
        record = self.finish(self.launch("orphan"), "SUCCEEDED", 0)
        self.assertEqual(len(record["cleanup"]["reaped_descendants"]), 1)

    def test_timeout_waits_for_group_even_after_direct_child_exits(self):
        record = self.finish(self.launch("fork-wait", timeout=0.4), "TIMED_OUT", 124)
        self.assertEqual(record["child_returncode"], 0)
        self.assertIn("SIGKILL", record["cleanup"]["signals"])
        self.assertEqual(len(record["cleanup"]["reaped_descendants"]), 1)

    def test_descendant_new_session_is_still_owned_and_reaped(self):
        record = self.finish(self.launch("escape"), "SUCCEEDED", 0)
        self.assertEqual(len(record["cleanup"]["reaped_descendants"]), 1)
        self.assertTrue(
            any(row["pgid"] != record["pgid"] for row in record["cleanup"]["targets"])
        )

    def test_cancel_sigterm_sigint_sighup_each_closes_descendants(self):
        for sig in (signal.SIGTERM, signal.SIGINT, signal.SIGHUP):
            with self.subTest(signal=sig.name):
                handle = self.launch("fork-wait", name=sig.name)
                self.ready(handle, count=2)
                os.kill(handle[0].pid, sig)
                record = self.finish(handle, "CANCELLED", 128 + sig)
                self.assertEqual(record["cancel_signal"], sig.name)

    def test_existing_run_cannot_be_overwritten(self):
        first = self.launch()
        self.finish(first, "SUCCEEDED", 0)
        original = (first[1] / "run.json").read_bytes()
        again = self.launch()
        _stdout, stderr = again[0].communicate(timeout=3)
        self.assertEqual(again[0].returncode, 2)
        self.assertIn(b"existing run", stderr)
        self.assertEqual((first[1] / "run.json").read_bytes(), original)

    def test_cancel_also_reaps_descendant_in_new_session(self):
        handle = self.launch("escape-wait")
        self.ready(handle, count=2)
        os.kill(handle[0].pid, signal.SIGTERM)
        self.finish(handle, "CANCELLED", 128 + signal.SIGTERM)

    def test_permission_denied_is_bounded_and_diagnosed(self):
        handle = self.launch("sleep", timeout=0.3, deny_signals=True)
        process, folder, journal = handle
        process.communicate(timeout=5)
        record = json.loads((folder / "run.json").read_text())
        self.assertEqual(process.returncode, 125)
        self.assertEqual(record["status"], "CLEANUP_INCOMPLETE")
        self.assertEqual(record["terminal_reason"], "TIMED_OUT")
        self.assertIn("SIGNAL_PERMISSION_DENIED", record["cleanup"]["errors"])
        self.assertTrue(record["cleanup"]["remaining"])
        self.assertLess(record["elapsed_seconds"], 4)
        # The test owns the deliberately blocked fixture. Its parent has real
        # permissions and reaps it; the supervisor gains no extra authority.
        for row in map(json.loads, journal.read_text().splitlines()):
            fd = os.pidfd_open(row["pid"])
            try:
                signal.pidfd_send_signal(fd, signal.SIGKILL)
            finally:
                os.close(fd)
            deadline = time.monotonic() + 2
            while time.monotonic() < deadline:
                waited, _ = os.waitpid(row["pid"], os.WNOHANG)
                if waited:
                    break
                time.sleep(0.01)
            self.assertFalse(Path(f"/proc/{row['pid']}").exists())


if __name__ == "__main__":
    unittest.main()
