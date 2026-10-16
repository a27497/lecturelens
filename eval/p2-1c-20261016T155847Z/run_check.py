#!/usr/bin/env python3
"""Bound local checks with disk monitoring; no deployment/provider credential access."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import signal
import subprocess
import time
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent
PRIVATE = ROOT / ".data" / PUBLIC.name / "checks"


def disk():
    stat = os.statvfs(ROOT)
    used = (stat.f_blocks - stat.f_bfree) * stat.f_frsize
    available = stat.f_bavail * stat.f_frsize
    headroom = .85 * (used + available) - used
    return {"used_bytes": used, "available_bytes": available,
            "usage_percent": 100 * used / (used + available),
            "headroom_to_85_bytes": headroom,
            "allowed": used / (used + available) <= .85 and headroom >= 2 * 1024**3}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--cwd", choices=["backend", "frontend", "agent-service"], default="backend")
    parser.add_argument("--seconds", type=int, default=600)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.name.replace("-", "").isalnum():
        raise SystemExit("invalid check name")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    PRIVATE.mkdir(parents=True, exist_ok=True, mode=0o700)
    record_file = PUBLIC / (args.name + ".json")
    log_file = PRIVATE / (args.name + ".log")
    if record_file.exists() or log_file.exists():
        raise SystemExit("existing evidence must not be overwritten")
    before = disk()
    if not before["allowed"]:
        raise SystemExit("DISK_GATE_STOP")
    started = time.time()
    record = {"command": command, "cwd": args.cwd, "disk_before": before,
              "started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(),
              "runtime_services_started": False, "real_model_quality": False}
    with log_file.open("x") as log:
        os.chmod(log_file, 0o600)
        # Provider/deployment variables are never inspected or forwarded to deterministic checks.
        environment = {name: os.environ[name] for name in (
            "PATH", "HOME", "USER", "LOGNAME", "JAVA_HOME", "LANG", "LC_ALL",
            "SYSTEM_MODEL_TEST_JDBC_URL", "SYSTEM_MODEL_TEST_MYSQL_USER", "SYSTEM_MODEL_TEST_MYSQL_PASSWORD",
            "AGENT_TEST_DATABASE_URL"
        ) if name in os.environ}
        process = subprocess.Popen(command, cwd=ROOT / args.cwd, stdout=log,
                                   stderr=subprocess.STDOUT, start_new_session=True, env=environment)
        record["pid"] = process.pid
        record["start_ticks"] = Path(f"/proc/{process.pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
        deadline = time.monotonic() + args.seconds
        peak = before["usage_percent"]
        while process.poll() is None:
            sample = disk()
            peak = max(peak, sample["usage_percent"])
            if not sample["allowed"] or time.monotonic() >= deadline:
                record["stop_reason"] = "DISK_GATE" if not sample["allowed"] else "TIMEOUT"
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                break
            time.sleep(1)
        record["exit_code"] = process.wait()
    record["disk_peak_percent"] = peak
    record["disk_after"] = disk()
    record["log_path"] = str(log_file.relative_to(ROOT))
    record["log_sha256"] = hashlib.sha256(log_file.read_bytes()).hexdigest()
    reports = []
    if args.cwd == "backend":
        destination = PRIVATE / (args.name + "-reports")
        destination.mkdir()
        for path in sorted((ROOT / "backend/target/surefire-reports").glob("TEST-*.xml")):
            if path.stat().st_mtime < started:
                continue
            raw = path.read_bytes()
            (destination / path.name).write_bytes(raw)
            suite = ET.fromstring(raw)
            reports.append({"suite": suite.attrib["name"],
                            **{key: int(suite.attrib.get(key, 0)) for key in ("tests", "failures", "errors", "skipped")},
                            "sha256": hashlib.sha256(raw).hexdigest()})
    record["suites"] = reports
    record["total"] = {key: sum(suite[key] for suite in reports) for key in ("tests", "failures", "errors", "skipped")}
    external = PRIVATE / (args.name + "-junit.xml")
    if args.cwd != "backend" and external.exists():
        raw=external.read_bytes()
        suites=list(ET.fromstring(raw).iter("testsuite"))
        record["total"]={key:sum(int(suite.attrib.get(key,0)) for suite in suites) for key in ("tests","failures","errors","skipped")}
        record["external_junit"]={"path":str(external.relative_to(ROOT)),"sha256":hashlib.sha256(raw).hexdigest()}
    record_file.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"record": str(record_file.relative_to(ROOT)), "exit_code": record["exit_code"], "total": record["total"]}))
    raise SystemExit(record["exit_code"] if "stop_reason" not in record else 88)


if __name__ == "__main__":
    main()
