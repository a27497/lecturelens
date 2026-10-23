#!/usr/bin/env python3
"""Run pytest with no provider credentials and an inherited Python socket fence."""

import argparse
import os
import sys
from pathlib import Path

from psycopg.conninfo import conninfo_to_dict, make_conninfo

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-port", type=int, required=True)
    parser.add_argument("--network-records", type=Path, required=True)
    parser.add_argument("pytest_args", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    config = conninfo_to_dict(dsn)
    if (
        (config.get("host"), config.get("dbname"), config.get("port"))
        != (
            "127.0.0.1",
            "lecturelens_agent_test",
            str(args.database_port),
        )
        or not 20000 <= args.database_port < 32768
        or config.get("hostaddr") not in (None, "127.0.0.1")
        or config.get("service")
    ):
        raise ValueError("Explicit isolated loopback test database required")
    dsn = make_conninfo(dsn, hostaddr="127.0.0.1")
    args.network_records.mkdir(parents=True, exist_ok=False)
    environment = {
        k: os.environ[k]
        for k in ("PATH", "HOME", "USER", "LANG", "LC_ALL")
        if k in os.environ
    }
    environment.update(
        AGENT_TEST_DATABASE_URL=dsn,
        PYTHONPATH=os.pathsep.join(
            [
                str(ROOT / "scripts/eval/preflight_network_guard"),
                str(ROOT / "agent-service/src"),
            ]
        ),
        PYTHONNOUSERSITE="1",
        LECTURELENS_PREFLIGHT_DB_PORT=str(args.database_port),
        LECTURELENS_PREFLIGHT_NETWORK_RECORDS=str(args.network_records.resolve()),
    )
    tests = args.pytest_args[1:] if args.pytest_args[:1] == ["--"] else args.pytest_args
    # A startup failure of sitecustomize must not silently run an unguarded suite.
    code = "import os,sys; assert os.environ.get('LECTURELENS_PREFLIGHT_GUARDED')=='1'; import pytest; raise SystemExit(pytest.main(sys.argv[1:]))"
    os.chdir(ROOT / "agent-service")
    os.execve(sys.executable, [sys.executable, "-c", code, *tests], environment)


if __name__ == "__main__":
    main()
