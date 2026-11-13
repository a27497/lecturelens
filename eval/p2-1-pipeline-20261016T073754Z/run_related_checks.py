#!/usr/bin/env python3
"""Run a bounded local check command; never connect to model providers or load deployment secrets."""
import argparse
import datetime as dt
import json
import os
from pathlib import Path
import signal
import subprocess
import time


def disk():
    value = os.statvfs("/")
    used = (value.f_blocks - value.f_bfree) * value.f_frsize
    available = value.f_bavail * value.f_frsize
    return {"used_bytes": used, "available_bytes": available, "use_percent": 100 * used / (used + available)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", required=True)
    parser.add_argument("--timeout", type=int, default=240)
    parser.add_argument("command", nargs=argparse.REMAINDER)
    args = parser.parse_args()
    if not args.name.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("Invalid check name")
    command = args.command[1:] if args.command[:1] == ["--"] else args.command
    root = Path(__file__).resolve().parents[2]
    target = root / ".data" / Path(__file__).parent.name / "checks"
    target.mkdir(parents=True, exist_ok=True)
    output = target / f"{args.name}.log"
    if output.exists():
        raise SystemExit("Existing evidence must not be overwritten")
    before = disk()
    if before["use_percent"] > 85:
        raise SystemExit("DISK_OVER_85: no command started")
    record = {"started_at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "disk_before": before,
              "command": command, "timeout_seconds": args.timeout, "disk_peak_percent": before["use_percent"]}
    with output.open("x") as log:
        process = subprocess.Popen(command, cwd=root / "backend", stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        end = time.monotonic() + args.timeout
        while process.poll() is None:
            current = disk()
            record["disk_peak_percent"] = max(record["disk_peak_percent"], current["use_percent"])
            if current["use_percent"] > 85 or time.monotonic() >= end:
                record["stopped_reason"] = "DISK_OVER_85" if current["use_percent"] > 85 else "COMMAND_TIMEOUT"
                os.killpg(process.pid, signal.SIGTERM)
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                break
            time.sleep(1)
        record["exit_code"] = process.wait()
    record["disk_after"] = disk()
    record["finished_at_utc"] = dt.datetime.now(dt.timezone.utc).isoformat()
    (target / f"{args.name}.json").write_text(json.dumps(record, indent=2) + "\n")
    raise SystemExit(record["exit_code"] if "stopped_reason" not in record else 88)


if __name__ == "__main__":
    main()
