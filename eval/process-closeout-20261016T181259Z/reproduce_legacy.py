#!/usr/bin/env python3
"""Reproduce frozen runner defects in new synthetic processes, then reap them."""
import ctypes
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import tempfile
import time

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / ".data" / PUBLIC.name
ORIGINAL = ROOT / "eval/p2-1c-20261016T155847Z/run_check.py"
FIXTURE = ROOT / "scripts/dev/tests/process_fixture.py"


def identity(row):
    try:
        fields = Path(f"/proc/{row['pid']}/stat").read_text().rsplit(")", 1)[1].split()
        if int(fields[19]) == row["start_ticks"]:
            return {**row, "state": fields[0], "ppid": int(fields[1])}
    except FileNotFoundError:
        pass
    return None


def main():
    output = PUBLIC / "legacy-reproduction.json"
    assert not output.exists()
    assert ctypes.CDLL(None).prctl(36, 1, 0, 0, 0) == 0
    results = []
    for case, mode in (("success-descendant", "orphan"),
                       ("cancel-without-record", "fork-wait"),
                       ("timeout-descendant", "fork-wait")):
        with tempfile.TemporaryDirectory(dir=PRIVATE, prefix=case + "-") as directory:
            base = Path(directory)
            (base / "backend").mkdir()
            (base / "public").mkdir()
            journal = base / "pids.jsonl"
            # Execute the unchanged source in a fresh interpreter with isolated
            # evidence destinations. Do not modify/import the frozen directory.
            bootstrap = """
import sys
from pathlib import Path
source,base,fixture,mode,journal=sys.argv[1:]
base=Path(base)
scope={'__file__':source,'__name__':'legacy_probe'}
exec(compile(Path(source).read_text(),source,'exec'),scope)
scope.update(ROOT=base,PUBLIC=base/'public',PRIVATE=base/'private')
sys.argv=[source,'--name','probe','--cwd','backend','--seconds','1','--',sys.executable,fixture,mode,journal]
scope['main']()
"""
            command = [sys.executable, "-c", bootstrap, str(ORIGINAL), str(base),
                       str(FIXTURE), mode, str(journal)]
            environment = {name: os.environ[name] for name in ("PATH", "HOME", "LANG") if name in os.environ}
            began = time.monotonic()
            with (PRIVATE / (case + ".log")).open("x") as log:
                process = subprocess.Popen(command, env=environment, stdin=subprocess.DEVNULL,
                                           stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
                try:
                    deadline = time.monotonic() + 4
                    while not journal.exists() or len(journal.read_text().splitlines()) < 2:
                        assert time.monotonic() < deadline, "fixture readiness timeout"
                        time.sleep(.01)
                    rows = list(map(json.loads, journal.read_text().splitlines()))
                    if case == "cancel-without-record":
                        os.kill(process.pid, signal.SIGTERM)
                    code = process.wait(timeout=5)
                    leftovers = [value for row in rows if (value := identity(row))]
                    record = base / "public/probe.json"
                    result = {"case": case, "runner_exit_code": code,
                              "terminal_record_exists": record.exists(),
                              "leftovers_before_probe_cleanup": leftovers}
                    assert any(row["state"] not in ("Z", "X") for row in leftovers)
                    if case == "cancel-without-record":
                        assert code == -signal.SIGTERM and not record.exists()
                    else:
                        original_record = json.loads(record.read_text())
                        result["original_stop_reason"] = original_record.get("stop_reason")
                        result["original_child_returncode"] = original_record["exit_code"]
                        assert code == (88 if case == "timeout-descendant" else 0)
                finally:
                    if process.poll() is None:
                        process.kill()
                        process.wait(timeout=2)
                    rows = list(map(json.loads, journal.read_text().splitlines())) if journal.exists() else []
                    for row in rows:
                        if identity(row):
                            fd = os.pidfd_open(row["pid"])
                            try:
                                signal.pidfd_send_signal(fd, signal.SIGKILL)
                            finally:
                                os.close(fd)
                    deadline = time.monotonic() + 2
                    while time.monotonic() < deadline:
                        try:
                            pid, _ = os.waitpid(-1, os.WNOHANG)
                        except ChildProcessError:
                            break
                        if not pid:
                            time.sleep(.01)
                    assert not any(identity(row) for row in rows), "new probe process not reaped"
                result.update(probe_cleanup_complete=True, elapsed_seconds=time.monotonic() - began)
                results.append(result)
    output.write_text(json.dumps({"unchanged_legacy_source": str(ORIGINAL.relative_to(ROOT)),
                                 "cases": results, "existing_processes_signaled": False}, indent=2) + "\n")
    print(json.dumps({"reproduced_cases": len(results), "probe_cleanup_complete": True}))


if __name__ == "__main__":
    main()
