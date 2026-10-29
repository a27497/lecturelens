"""Local CI-equivalent check using a new disposable PG; no credentials in argv/logs."""

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

import psycopg

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--tests", nargs="*")
parser.add_argument("--mutations", action="store_true")
args = parser.parse_args()
output = args.output.resolve()
output.mkdir(parents=True, exist_ok=True)
signal.signal(signal.SIGTERM, lambda *_: (_ for _ in ()).throw(KeyboardInterrupt()))
name = "lecturelens-p10-tests-" + secrets.token_hex(6)
port = None
for candidate in [25741] + [20000 + secrets.randbelow(12768) for _ in range(50)]:
    with socket.socket() as sock:
        try:
            sock.bind(("127.0.0.1", candidate))
        except OSError:
            continue
        port = candidate
        break
if port is None:
    raise RuntimeError("No free isolated loopback test port")
password = secrets.token_hex(32)
env = {key: os.environ[key] for key in ("PATH", "HOME", "USER", "LANG", "UV_CACHE_DIR") if key in os.environ}
env.update(
    POSTGRES_PASSWORD=password,
    AGENT_LLM_MODE="mock",
    UV_PROJECT_ENVIRONMENT=str(Path(sys.executable).parent.parent),
)
started = False
result = dict(
    container=name,
    loopback_port=port,
    host="127.0.0.1",
    databases=["lecturelens_agent_test", "lecturelens_agent_acceptance"],
    sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    dirty=subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).splitlines(),
    python=sys.version,
    llm_mode="mock",
    checks=[],
)
code = 1
try:
    subprocess.run(
        [
            "docker",
            "run",
            "-d",
            "--name",
            name,
            "--memory",
            "1g",
            "--cpus",
            "2",
            "-e",
            "POSTGRES_PASSWORD",
            "-e",
            "POSTGRES_USER=lecturelens",
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
    env["AGENT_TEST_DATABASE_URL"] = (
        f"postgresql://lecturelens:{password}@127.0.0.1:{port}/lecturelens_agent_test"
    )
    for _ in range(90):
        try:
            with psycopg.connect(env["AGENT_TEST_DATABASE_URL"], autocommit=True) as conn:
                conn.execute("CREATE DATABASE lecturelens_agent_acceptance")
                conn.execute("CREATE EXTENSION IF NOT EXISTS vector")
                result["vector"] = conn.execute(
                    "SELECT extversion FROM pg_extension WHERE extname='vector'"
                ).fetchone()[0]
            break
        except psycopg.OperationalError:
            time.sleep(1)
    else:
        raise RuntimeError("New isolated PG unavailable")
    uv = "/home/dev/.local/bin/uv"
    commands = [
        ("ruff-check", [uv, "run", "ruff", "check", "src", "tests"]),
        ("ruff-format", [uv, "run", "ruff", "format", "--check", "src", "tests"]),
        ("pytest", [uv, "run", "pytest", "-q"]),
    ]
    if args.tests:
        commands = [("targeted", [uv, "run", "pytest", "-q", *args.tests])]
    if args.mutations:
        commands = [
            (
                "mutations",
                [sys.executable, str(ROOT / "eval/p10-review/run_mutations.py"), str(output / "mutations")],
            )
        ]
    for check_name, command in commands:
        exit_code = subprocess.run(
            [
                sys.executable,
                str(ROOT / "scripts/dev/run_check.py"),
                "--name",
                check_name,
                "--timeout",
                "1200",
                "--output",
                str(output),
                "--",
                *command,
            ],
            cwd=ROOT / "agent-service",
            env=env,
            check=False,
        ).returncode
        result["checks"].append(dict(name=check_name, command=command, exit_code=exit_code))
        if exit_code:
            break
    code = exit_code
finally:
    if started:
        with (output / "postgres.log").open("w") as log:
            subprocess.run(["docker", "logs", name], stdout=log, stderr=subprocess.STDOUT, check=False)
        subprocess.run(["docker", "rm", "-f", name], check=True, stdout=subprocess.DEVNULL)
        remaining = subprocess.check_output(
            ["docker", "ps", "-aq", "--filter", f"name=^{name}$"], text=True
        ).strip()
        result["removed"] = not remaining
    for log in output.glob("*.log"):
        log.write_text(log.read_text().replace(password, "[REDACTED]"))
    result["exit_code"] = code
    result["status"] = "PASS" if code == 0 else "FAIL"
    (output / "database.json").write_text(json.dumps(result, indent=2) + "\n")
sys.exit(code)
