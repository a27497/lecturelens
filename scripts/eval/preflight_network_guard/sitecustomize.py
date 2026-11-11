"""Opt-in socket fence for isolated checks, inherited by spawned Python workers."""

import atexit
import json
import os
import socket
import sys
from pathlib import Path

PORT = int(os.environ["LECTURELENS_PREFLIGHT_DB_PORT"])
COUNTS = {
    "database_connections": 0,
    "loopback_test_connections": 0,
    "denied_connections": 0,
}


def audit(event, args):
    if event == "socket.getaddrinfo" and args[0] not in (
        "127.0.0.1",
        "localhost",
        "::1",
        None,
    ):
        COUNTS["denied_connections"] += 1
        raise PermissionError("Preflight denies external DNS")
    if event in {"socket.connect", "socket.sendto"}:
        sock, address = args[0], args[-1]
        if sock.family not in (socket.AF_INET, socket.AF_INET6):
            return
        host, port = address[:2]
        if host in ("127.0.0.1", "::1") and (port == PORT or port >= 32768):
            COUNTS[
                "database_connections" if port == PORT else "loopback_test_connections"
            ] += 1
            return
        COUNTS["denied_connections"] += 1
        raise PermissionError(
            "Preflight allows only its test database and ephemeral loopback servers"
        )


sys.addaudithook(audit)
os.environ["LECTURELENS_PREFLIGHT_GUARDED"] = "1"


@atexit.register
def record():
    directory = os.environ.get("LECTURELENS_PREFLIGHT_NETWORK_RECORDS")
    if directory:
        path = Path(directory) / f"{os.getpid()}.json"
        path.write_text(json.dumps(COUNTS, sort_keys=True) + "\n")
