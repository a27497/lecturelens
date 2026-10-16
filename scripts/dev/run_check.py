#!/usr/bin/env python3
"""Run a local check with bounded cancellation and cleanup of its own descendants."""

import argparse
import ctypes
import datetime as dt
import errno
import hashlib
import json
import math
import os
import signal
import subprocess
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
ENVIRONMENT = (
    "PATH",
    "HOME",
    "USER",
    "LOGNAME",
    "JAVA_HOME",
    "LANG",
    "LC_ALL",
    "SYSTEM_MODEL_TEST_JDBC_URL",
    "SYSTEM_MODEL_TEST_MYSQL_USER",
    "SYSTEM_MODEL_TEST_MYSQL_PASSWORD",
    "AGENT_TEST_DATABASE_URL",
)


def disk():
    stat = os.statvfs(ROOT)
    used = (stat.f_blocks - stat.f_bfree) * stat.f_frsize
    available = stat.f_bavail * stat.f_frsize
    return {
        "used_bytes": used,
        "available_bytes": available,
        "allowed": used / (used + available) <= 0.85
        and 0.85 * (used + available) - used >= 2 * 1024**3,
    }


def descendants():
    """Only this supervisor's descendants; no arguments or environments are read."""
    rows = []
    for path in Path("/proc").iterdir():
        if not path.name.isdigit():
            continue
        try:
            fields = (path / "stat").read_text().rsplit(")", 1)[1].split()
            rows.append(
                {
                    "pid": int(path.name),
                    "ppid": int(fields[1]),
                    "pgid": int(fields[2]),
                    "state": fields[0],
                    "start_ticks": int(fields[19]),
                }
            )
        except (OSError, IndexError, ValueError):
            continue
    owned = {os.getpid()}
    while True:
        found = {row["pid"] for row in rows if row["ppid"] in owned}
        if found <= owned:
            break
        owned.update(found)
    return sorted(
        (row for row in rows if row["pid"] in owned and row["pid"] != os.getpid()),
        key=lambda item: item["pid"],
    )


def exited(process):
    # Observe exit without stealing Popen's wait status. The leader is reaped
    # separately, before waitpid(-1) collects adopted grandchildren.
    return (
        os.waitid(os.P_PID, process.pid, os.WEXITED | os.WNOHANG | os.WNOWAIT)
        is not None
    )


def start_ticks(pid):
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19])


def cleanup(process, grace, kill_wait):
    result = {
        "pgid": process.pid,
        "signals": [],
        "errors": [],
        "targets": [],
        "reaped_descendants": [],
    }
    sent = set()

    def signal_owned(sig):
        for row in descendants():
            identity = (row["pid"], row["start_ticks"], sig)
            if row["state"] in ("Z", "X") or identity in sent:
                continue
            fd = None
            try:
                fd = os.pidfd_open(row["pid"])
                current = (
                    Path(f"/proc/{row['pid']}/stat")
                    .read_text()
                    .rsplit(")", 1)[1]
                    .split()
                )
                if int(current[19]) != row["start_ticks"]:
                    continue
                # A pidfd prevents reuse races. PPid ancestry and subreaper
                # adoption also cover children that start a different session.
                signal.pidfd_send_signal(fd, sig)
                sent.add(identity)
                name = signal.Signals(sig).name
                if name not in result["signals"]:
                    result["signals"].append(name)
                result["targets"].append({**row, "signal": name})
            except (ProcessLookupError, FileNotFoundError):
                pass
            except PermissionError:
                if "SIGNAL_PERMISSION_DENIED" not in result["errors"]:
                    result["errors"].append("SIGNAL_PERMISSION_DENIED")
            finally:
                if fd is not None:
                    os.close(fd)

    def live():
        return [row for row in descendants() if row["state"] not in ("Z", "X")]

    deadline = time.monotonic() + grace
    while live() and time.monotonic() < deadline:
        signal_owned(signal.SIGTERM)
        time.sleep(0.02)
    deadline = time.monotonic() + kill_wait
    while True:
        # Stopped tasks cannot act on TERM. A second deadline covers KILL,
        # concurrent exits/forks and reaping; no wait here is unbounded.
        signal_owned(signal.SIGKILL)
        if process.returncode is None and exited(process):
            process.wait(timeout=0)
        if process.returncode is not None:
            while time.monotonic() < deadline:
                try:
                    pid, status = os.waitpid(-1, os.WNOHANG)
                except ChildProcessError:
                    break
                if not pid:
                    break
                result["reaped_descendants"].append(
                    {
                        "pid": pid,
                        "returncode": os.waitstatus_to_exitcode(status),
                    }
                )
        remaining = descendants()
        if not remaining or time.monotonic() >= deadline:
            break
        time.sleep(0.02)
    result["remaining"] = remaining
    result["complete"] = process.returncode is not None and not remaining
    return result


def positive(value):
    number = float(value)
    if not math.isfinite(number) or number <= 0:
        raise argparse.ArgumentTypeError("must be finite and positive")
    return number


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--name", required=True)
    parser.add_argument("--cwd", type=Path, default=ROOT)
    parser.add_argument("--output-root", type=Path, default=ROOT / ".data/dev-checks")
    parser.add_argument("--timeout", type=positive, default=600)
    parser.add_argument("--grace-seconds", type=positive, default=2)
    parser.add_argument("--cleanup-seconds", type=positive, default=3)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    if not args.name.replace("-", "").replace("_", "").isalnum() or not command:
        parser.error("a unique alphanumeric check name and command are required")
    if not Path("/proc/self/stat").exists():
        parser.error("this local process supervisor requires Linux /proc")
    folder = args.output_root.resolve() / args.name
    folder.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    try:
        folder.mkdir(mode=0o700)
    except FileExistsError:
        parser.error("existing run must not be overwritten")
    record_path = folder / "run.json"
    log_path = folder / "output.log"
    started = time.monotonic()
    received = []
    process = None
    record = {
        "status": "STARTING",
        "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
        "runner_pid": os.getpid(),
        "runner_start_ticks": start_ticks(os.getpid()),
        "cwd": str(args.cwd.resolve()),
        "executable": Path(command[0]).name,
        # Arguments may contain private data; do not duplicate them in diagnostics.
        "argv_sha256": hashlib.sha256(json.dumps(command).encode()).hexdigest(),
        "timeout_seconds": args.timeout,
        "grace_seconds": args.grace_seconds,
        "cleanup_seconds": args.cleanup_seconds,
        "child_returncode": None,
        "exit_code": 125,
        "log_path": str(log_path),
        "disk_before": disk(),
    }

    def save():
        temporary = folder / "run.json.tmp"
        temporary.write_text(json.dumps(record, indent=2) + "\n")
        temporary.chmod(0o600)
        temporary.replace(record_path)

    def cancel(signum, _frame):
        # Do no blocking I/O or cleanup inside a signal handler; the polling loop
        # owns the only teardown path, including repeated cancellation signals.
        if not received:
            received.append(signum)

    previous = {
        sig: signal.signal(sig, cancel)
        for sig in (
            signal.SIGINT,
            signal.SIGTERM,
            signal.SIGHUP,
        )
    }
    save()
    try:
        # This applies only to this new supervisor, never to the Codex app-server.
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(36, 1, 0, 0, 0) != 0:  # PR_SET_CHILD_SUBREAPER
            raise OSError(ctypes.get_errno(), "subreaper unavailable")
        probe = os.pidfd_open(os.getpid())
        os.close(probe)
        if not record["disk_before"]["allowed"]:
            record.update(status="DISK_GATE", exit_code=88)
        elif received:
            record.update(status="CANCELLED", exit_code=128 + received[0])
        else:
            environment = {
                name: os.environ[name] for name in ENVIRONMENT if name in os.environ
            }
            with log_path.open("x") as log:
                log_path.chmod(0o600)
                process = subprocess.Popen(
                    command,
                    cwd=args.cwd,
                    env=environment,
                    stdin=subprocess.DEVNULL,
                    stdout=log,
                    stderr=subprocess.STDOUT,
                    start_new_session=True,
                    close_fds=True,
                )
                record.update(
                    status="RUNNING",
                    child_pid=process.pid,
                    pgid=process.pid,
                    child_start_ticks=start_ticks(process.pid),
                )
                save()
                while True:
                    if received:
                        record.update(status="CANCELLED", exit_code=128 + received[0])
                        break
                    if exited(process):
                        record["status"] = "EXITED"
                        break
                    if time.monotonic() - started >= args.timeout:
                        record.update(status="TIMED_OUT", exit_code=124)
                        break
                    if not disk()["allowed"]:
                        record.update(status="DISK_GATE", exit_code=88)
                        break
                    time.sleep(0.05)
    except OSError as error:
        record.update(
            status="SPAWN_ERROR" if process is None else "SUPERVISOR_ERROR",
            error_type=type(error).__name__,
            error_errno=error.errno,
            exit_code=127 if error.errno == errno.ENOENT else 125,
        )
    except Exception as error:  # noqa: BLE001 - preserve terminal status without logging private exception text
        record.update(
            status="SUPERVISOR_ERROR", error_type=type(error).__name__, exit_code=125
        )
    finally:
        if process is not None:
            try:
                record["cleanup"] = cleanup(
                    process, args.grace_seconds, args.cleanup_seconds
                )
            except Exception as error:  # noqa: BLE001 - a teardown failure must produce an explicit incomplete record
                record["cleanup"] = {
                    "complete": False,
                    "error_type": type(error).__name__,
                }
            record["child_returncode"] = process.returncode
            if record["status"] == "EXITED":
                code = process.returncode
                record.update(
                    status="SUCCEEDED" if code == 0 else "FAILED",
                    exit_code=code
                    if code is not None and code >= 0
                    else 128 - code
                    if code is not None
                    else 125,
                )
            if not record["cleanup"]["complete"]:
                record.update(
                    terminal_reason=record["status"],
                    status="CLEANUP_INCOMPLETE",
                    exit_code=125,
                )
        if received:
            record["cancel_signal"] = signal.Signals(received[0]).name
        record.update(
            finished_at_utc=dt.datetime.now(dt.timezone.utc).isoformat(),
            elapsed_seconds=time.monotonic() - started,
            disk_after=disk(),
        )
        if log_path.exists():
            with log_path.open("rb") as stream:
                record["log_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
        save()
        for sig, handler in previous.items():
            signal.signal(sig, handler)
    print(
        json.dumps(
            {
                "record": str(record_path),
                "status": record["status"],
                "exit_code": record["exit_code"],
            }
        ),
        flush=True,
    )
    return record["exit_code"]


if __name__ == "__main__":
    raise SystemExit(main())
