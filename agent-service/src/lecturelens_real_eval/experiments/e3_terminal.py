"""Explicit operator input on a foreground OpenSSH login terminal."""

import getpass
import os
import re
import resource
import runpy
import sys
import warnings
from pathlib import Path

from lecturelens_real_eval.cli import CLIError


class DiskGate(CLIError):
    exit_code = 88


def check_disk(root):
    # Use the original supervisor's workspace-filesystem policy for live launches.
    result = runpy.run_path(str(root / "scripts/dev/run_check.py"))["disk"]()
    if not result["allowed"]:
        used, available = result["used_bytes"], result["available_bytes"]
        needed = int(used + 2 * 1024**3 - 0.85 * (used + available)) + 1
        raise DiskGate(
            f"E3_DISK_GATE used={100 * used / (used + available):.2f}% "
            f"available_bytes={available} additional_free_bytes_required={needed}"
        )


def proc_parent(pid):
    return int(Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[1])


def ssh_process(pid):
    return Path(f"/proc/{pid}/comm").read_text().strip() in {"sshd", "sshd-session"}


def ssh_login_session(session):
    # OpenSSH creates the login shell as the session leader. A new automation PTY
    # has its own session leader and does not inherit this parent relationship.
    parent = proc_parent(session)
    if not ssh_process(parent):
        return False
    while parent > 1 and ssh_process(parent):
        status = Path(f"/proc/{parent}/status").read_text().splitlines()
        uid = next(line.split()[2] for line in status if line.startswith("Uid:"))
        if uid == "0":
            return True
        parent = proc_parent(parent)
    return False


def require_ssh_tty():
    tty = os.environ.get("SSH_TTY", "")
    try:
        attached = (
            bool(re.fullmatch(r"/dev/pts/[0-9]+", tty))
            and all(os.ttyname(stream.fileno()) == tty for stream in (sys.stdin, sys.stdout, sys.stderr))
            and os.tcgetpgrp(sys.stdin.fileno()) == os.getpgrp()
            and ssh_login_session(os.getsid(0))
        )
    except (OSError, ValueError, IndexError, StopIteration):
        attached = False
    if not attached:
        raise CLIError("E3_DEVELOPMENT_REQUIRES_FOREGROUND_SSH_TTY")


def read_operator_key():
    require_ssh_tty()
    resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        if input("Type E3 USD10 to confirm this one-shot phase and supplier billing risk: ") != "E3 USD10":
            raise CLIError("E3_OPERATOR_CONFIRMATION_REQUIRED")
        with warnings.catch_warnings():
            warnings.simplefilter("error", getpass.GetPassWarning)
            key = getpass.getpass("DeepSeek API key (hidden): ")
    except (EOFError, OSError, getpass.GetPassWarning):
        raise CLIError("E3_HIDDEN_KEY_INPUT_REQUIRED") from None
    if not valid_key(key):
        raise CLIError("E3_PROVIDER_CREDENTIAL_INVALID")
    return key


def valid_key(key):
    return re.fullmatch(r"[A-Za-z0-9._-]{16,512}", key) is not None
