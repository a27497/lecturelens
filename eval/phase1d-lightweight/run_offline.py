"""Credential-free local mechanism checks against the task-owned PostgreSQL."""

import os
import socket
import sys
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
EVIDENCE = ROOT / ".data/phase1d/offline-evidence" / uuid.uuid4().hex
EVIDENCE.mkdir(parents=True, mode=0o700)
print(f"OFFLINE_EVIDENCE={EVIDENCE}", flush=True)
os.environ.clear()  # No provider credentials are inherited by tests.
os.environ.update(
    PATH="/usr/local/bin:/usr/bin:/bin",
    HOME="/home/dev",
    AGENT_TEST_DATABASE_URL="postgresql://phase1d:phase1d-local-only@127.0.0.1:25851/lecturelens_agent_acceptance",
    PHASE1D_FAILURE_ZIP=str(ROOT / ".data/phase1d/failed-real-review.zip"),
    PYTEST_DISABLE_PLUGIN_AUTOLOAD="1",
    PHASE1D_EVIDENCE_DIR=str(EVIDENCE),
)
sys.path.insert(0, str(ROOT / "agent-service/src"))
connect = socket.socket.connect


def local(sock, address):
    if isinstance(address, tuple) and address[0] not in {"127.0.0.1", "::1"}:
        raise RuntimeError("PHASE1D_NO_EXTERNAL_NETWORK")
    return connect(sock, address)


socket.socket.connect = local
import pytest

raise SystemExit(pytest.main(sys.argv[1:]))
