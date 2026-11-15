"""Evaluation-only helpers; never read provider credentials or replay tasks."""

import importlib.util
import json
import os
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path("/home/dev/projects/lecturelens")
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / ".data" / PUBLIC.name


def utc():
    return datetime.now(timezone.utc).isoformat()


def redact(value):
    if isinstance(value, dict):
        banned = {
            "authorization",
            "api_key",
            "apikey",
            "ciphertext",
            "accessToken",
            "refreshToken",
        }
        return {
            k: (
                "[REDACTED]"
                if k in banned
                else "****"
                if k == "keyLast4" and v
                else redact(v)
            )
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [redact(v) for v in value]
    if isinstance(value, str):
        value = re.sub(r"(?i)Bearer\s+[A-Za-z0-9._~-]+", "Bearer [REDACTED]", value)
        value = re.sub(r"\bsk-[A-Za-z0-9_-]+", "[REDACTED]", value)
        value = re.sub(r"(?i)(api[_-]?key[\"\s:=]+)[^\s,\"}]+", r"\1[REDACTED]", value)
    return value


def save(name, value, private=False):
    path = (PRIVATE if private else PUBLIC) / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(redact(value), ensure_ascii=False, indent=2) + "\n")
    if private:
        path.chmod(0o600)


def append(name, value):
    with (PUBLIC / name).open("a") as out:
        out.write(json.dumps(redact(value), ensure_ascii=False) + "\n")


def disk():
    s = os.statvfs("/")
    return {
        "utc": utc(),
        "total_bytes": s.f_blocks * s.f_frsize,
        "available_bytes": s.f_bavail * s.f_frsize,
        "percent": 100 * (s.f_blocks - s.f_bavail) / s.f_blocks,
    }


def sql(query):
    cmd = [
        "docker",
        "exec",
        "-i",
        "lecturelens-demo-l2-mysql-1",
        "sh",
        "-c",
        'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -u root --batch --raw --skip-column-names',
    ]
    p = subprocess.run(
        cmd, input=query, text=True, capture_output=True, timeout=25, check=False
    )
    if p.returncode:
        raise RuntimeError("SQL query failed: " + redact(p.stderr)[:500])
    return [json.loads(x) for x in p.stdout.splitlines() if x.strip()]


def admin():
    # Same previously authorized local administrator authentication bridge.
    # It selects only JWT_ACCESS_SECRET, never a provider key; token is memory-only.
    path = ROOT / ".data/system-model-management/deepseek-20261016/live.py"
    spec = importlib.util.spec_from_file_location("existing_local_admin_bridge", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def mq(args, timeout=30):
    cmd = [
        "docker",
        "exec",
        "lecturelens-demo-l2-rocketmq-broker-1",
        "sh",
        "/home/rocketmq/rocketmq-5.3.4/bin/mqadmin",
        *args,
    ]
    p = subprocess.run(
        cmd, text=True, capture_output=True, timeout=timeout, check=False
    )
    return {
        "command": cmd,
        "returncode": p.returncode,
        "stdout": redact(p.stdout),
        "stderr": redact(p.stderr),
    }
