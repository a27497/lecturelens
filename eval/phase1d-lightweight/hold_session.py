"""Task-owned advisory lock makes queued cancellation deterministic, not a mock API."""

import os
import sys
import time
from pathlib import Path

import psycopg

session, folder = sys.argv[1:]
folder = Path(folder)
folder.mkdir(exist_ok=False)
with psycopg.connect(os.environ["AGENT_DATABASE_URL"], autocommit=True) as conn:
    conn.execute("SELECT pg_advisory_lock(hashtextextended(%s,8))", (session,))
    (folder / "ready").touch()
    deadline = time.monotonic() + 30
    while not (folder / "release").exists() and time.monotonic() < deadline:
        time.sleep(0.05)
