"""Synthetic processes only: no network, databases, sudo, services or credentials."""

import json
import os
import signal
import sys
import time
from pathlib import Path

mode, journal = sys.argv[1:]


def identity():
    stat = Path(f"/proc/{os.getpid()}/stat").read_text().rsplit(")", 1)[1].split()
    row = json.dumps({"pid": os.getpid(), "start_ticks": int(stat[19])}) + "\n"
    fd = os.open(journal, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
    try:
        os.write(fd, row.encode())
    finally:
        os.close(fd)


identity()
if mode == "success":
    assert sys.stdin.read() == ""
    assert "LECTURELENS_TEST_SENTINEL" not in os.environ
    print("synthetic-success", flush=True)
elif mode == "failure":
    raise SystemExit(7)
elif mode == "signal":
    os.kill(os.getpid(), signal.SIGTERM)
elif mode in ("sleep", "ignore", "stopped"):
    if mode == "ignore":
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
    if mode == "stopped":
        os.kill(os.getpid(), signal.SIGSTOP)
    time.sleep(60)
elif mode in ("orphan", "fork-wait", "escape", "escape-wait"):
    child = os.fork()
    if child == 0:
        if mode in ("escape", "escape-wait"):
            os.setsid()
        signal.signal(signal.SIGTERM, signal.SIG_IGN)
        identity()
        time.sleep(60)
        os._exit(0)
    deadline = time.monotonic() + 3
    while len(Path(journal).read_text().splitlines()) < 2:
        assert time.monotonic() < deadline
        time.sleep(0.01)
    if mode in ("fork-wait", "escape-wait"):
        # Reproduce the old timeout hole: the direct child exits on TERM but its
        # descendant ignores it. Waiting only for the direct child leaks it.
        signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
        time.sleep(60)
else:
    raise ValueError("unknown fixture")
