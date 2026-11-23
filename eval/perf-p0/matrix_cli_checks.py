"""Exercise batch control with inert command stubs in a temporary checkout.

Separate from deterministic_tests.py, whose audit guard forbids Bash subprocesses.
No real runner, service, Docker command or network operation is executed here.
"""

import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


class BatchControl(unittest.TestCase):
    def invoke(self, *, include_s2=False, fail_at=0, expired=False):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            script = root / "eval/perf-p0/fast_matrix.sh"
            script.parent.mkdir(parents=True)
            shutil.copyfile(Path(__file__).with_name("fast_matrix.sh"), script)
            binaries = root / "bin"
            binaries.mkdir()
            log = root / "calls.jsonl"
            runner = binaries / "python3"
            runner.write_text(
                "#!/usr/bin/python3\n"
                "import json, os, sys\n"
                "from pathlib import Path\n"
                "p = Path(os.environ['MATRIX_STUB_LOG'])\n"
                "with p.open('a') as f: f.write(json.dumps(sys.argv[1:]) + '\\n')\n"
                "raise SystemExit(7 if len(p.read_text().splitlines()) == "
                "int(os.environ['MATRIX_FAIL_AT']) else 0)\n"
            )
            runner.chmod(0o700)
            verifier = root / "agent-service/.venv/bin/python"
            verifier.parent.mkdir(parents=True)
            verifier.write_text("#!/bin/sh\nexit 0\n")
            verifier.chmod(0o700)
            git = binaries / "git"
            git.write_text("#!/bin/sh\nprintf '%040d\\n' 0\n")
            git.chmod(0o700)
            env = {
                "PATH": f"{binaries}:/usr/bin:/bin",
                "HOME": str(root),
                "MATRIX_STUB_LOG": str(log),
                "MATRIX_FAIL_AT": str(fail_at),
            }
            command = [
                "bash",
                str(script),
                ".data/result",
                "2000-01-01T00:00:00Z" if expired else "2100-01-01T00:00:00Z",
            ]
            if include_s2:
                command.append("--include-s2")
            done = subprocess.run(
                command,
                env=env,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
            calls = (
                [json.loads(line) for line in log.read_text().splitlines()]
                if log.exists()
                else []
            )
            return done, calls

    def test_full_matrix_has_twelve_serial_invocations_and_one_seed(self):
        done, calls = self.invoke(include_s2=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(calls), 13)
        self.assertIn("--requests", calls[0])
        names = [args[args.index("--name") + 1] for args in calls[1:]]
        self.assertEqual(
            names,
            [
                f"l2-{name}-r{rep}"
                for rep in (1, 2, 3)
                for name in ("a-qa", "a-run", "b-qa", "c-run")
            ],
        )
        for args in calls[1:]:
            self.assertIn("--offline", args)
            self.assertIn("--reuse-build-from", args)
            self.assertEqual(args[args.index("--seconds") + 1], "60")

    def test_fallback_never_raises_qa_limit_or_measures_s2(self):
        done, calls = self.invoke()
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(len(calls), 13)
        for args in calls:
            self.assertNotIn("S2", args[args.index("--scenarios") + 1].split(","))
            self.assertEqual(args[args.index("--qa-per-minute") + 1], "10")

    def test_failure_stops_without_retry_or_later_points(self):
        done, calls = self.invoke(include_s2=True, fail_at=3)
        self.assertEqual(done.returncode, 7, done.stderr)
        self.assertEqual(len(calls), 3)

    def test_expired_window_never_invokes_runner(self):
        done, calls = self.invoke(expired=True)
        self.assertEqual(done.returncode, 1, done.stderr)
        self.assertEqual(calls, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
