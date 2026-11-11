"""Disposable loopback PostgreSQL for P9 mechanism regressions and negative controls."""

import argparse
import json
import os
import secrets
import signal
import socket
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]

signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
p = argparse.ArgumentParser()
p.add_argument("--output", type=Path, required=True)
p.add_argument("--mutations", action="store_true")
p.add_argument("tests", nargs="*")
a = p.parse_args()
a.output = a.output.resolve()
a.output.mkdir(parents=True, exist_ok=True)
name = "lecturelens-p9-tests-" + secrets.token_hex(5)
with socket.socket() as sock:
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
password = secrets.token_hex(32)
env = {
    k: os.environ[k]
    for k in ("PATH", "HOME", "USER", "LANG", "UV_CACHE_DIR")
    if k in os.environ
}
env["POSTGRES_PASSWORD"] = password
result = {
    "container": name,
    "loopback_port": port,
    "database": "lecturelens_agent_test",
    "status": "RUNNING",
}
code = 1
started = False
try:
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--memory",
            "512m",
            "--cpus",
            "1",
            "-e",
            "POSTGRES_PASSWORD",
            "-e",
            "POSTGRES_USER=p9",
            "-e",
            "POSTGRES_DB=lecturelens_agent_test",
            "-p",
            f"127.0.0.1:{port}:5432",
            "--tmpfs",
            "/var/lib/postgresql/data:rw",
            "pgvector/pgvector:0.8.6-pg17@sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f",
        ],
        env=env,
        check=True,
        stdout=subprocess.DEVNULL,
    )
    started = True
    for _ in range(90):
        if (
            subprocess.run(
                [
                    "docker",
                    "exec",
                    name,
                    "pg_isready",
                    "-U",
                    "p9",
                    "-d",
                    "lecturelens_agent_test",
                ],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
            == 0
        ):
            break
        time.sleep(1)
    else:
        raise RuntimeError("Dedicated PG did not become ready")
    env["AGENT_TEST_DATABASE_URL"] = (
        f"postgresql://p9:{password}@127.0.0.1:{port}/lecturelens_agent_test"
    )
    command = [
        str(ROOT / "agent-service/.venv/bin/python"),
        "-m",
        "pytest",
        "-q",
        *a.tests,
    ]
    if a.mutations:
        command = [
            sys.executable,
            str(ROOT / "eval/p9-choice/run_mutations.py"),
            str(a.output),
        ]
    result["command"] = command
    code = subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/dev/run_check.py"),
            "--name",
            "python",
            "--timeout",
            "900",
            "--output",
            str(a.output),
            "--",
            *command,
        ],
        cwd=ROOT,
        env=env,
        check=False,
    ).returncode
    result["status"] = "PASS" if code == 0 else "FAIL"
finally:
    if started:
        with (a.output / "postgres.log").open("w") as log:
            subprocess.run(
                ["docker", "logs", name],
                stdout=log,
                stderr=subprocess.STDOUT,
                check=False,
            )
        subprocess.run(
            ["docker", "rm", "-f", name], check=True, stdout=subprocess.DEVNULL
        )
    result["exit_code"] = code
    (a.output / "database.json").write_text(json.dumps(result, indent=2) + "\n")
sys.exit(code)
