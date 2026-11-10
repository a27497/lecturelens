"""Run checks with current sources, a separate PostgreSQL and a loopback-only socket guard."""

import os
import socket
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
database = os.environ["AGENT_TEST_DATABASE_URL"]
os.environ.clear()
os.environ.update(
    PATH="/usr/local/bin:/usr/bin:/bin",
    AGENT_TEST_DATABASE_URL=database,
    PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    PHASE1D_FAILURE_ZIP=str(ROOT / ".data/phase1e/v19-smoke-2227-REAL-review.zip"),
)
sys.path.insert(0, str(ROOT / "agent-service/src"))
connect = socket.socket.connect


def local(sock, address):
    if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
        raise RuntimeError("PHASE1E_NO_EXTERNAL_NETWORK")
    return connect(sock, address)


socket.socket.connect = local
raise SystemExit(pytest.main(sys.argv[1:]))
