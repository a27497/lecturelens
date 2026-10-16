#!/usr/bin/env python3
"""Record process metadata and allowlisted historical execution markers only."""
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = Path(__file__).resolve().parent
SESSION = Path("/home/dev/.codex/sessions/2026/10/16/rollout-2026-10-16T12-16-07-01a144a4-1902-7a03-b82e-82ce996effd0.jsonl")


def texts(value):
    if isinstance(value, str):
        yield value
        if value.lstrip().startswith(("{", "[")):
            try:
                yield from texts(json.loads(value))
            except ValueError:
                pass
    elif isinstance(value, list):
        for item in value:
            yield from texts(item)
    elif isinstance(value, dict):
        for item in value.values():
            yield from texts(item)


def main():
    output = PUBLIC / "process-evidence.json"
    assert not output.exists()
    processes = []
    initial = {7522: 6069, 1633403: 2082559, 1634090: 2082764, 1634092: 2082766}
    boot = next(int(line.split()[1]) for line in Path("/proc/stat").read_text().splitlines() if line.startswith("btime "))
    for pid, start in initial.items():
        path = Path(f"/proc/{pid}")
        stat = (path / "stat").read_text().rsplit(")", 1)[1].split()
        status = dict(line.split(":", 1) for line in (path / "status").read_text().splitlines() if ":" in line)
        row = {"pid": pid, "ppid": int(stat[1]), "pgid": int(stat[2]), "sid": int(stat[3]),
               "state": stat[0], "tty_nr": int(stat[4]), "start_ticks": int(stat[19]),
               "same_identity_as_initial_observation": int(stat[19]) == start,
               "started_at_utc": dt.datetime.fromtimestamp(boot + int(stat[19]) / os.sysconf("SC_CLK_TCK"), dt.timezone.utc).isoformat(),
               "signal_metadata": {name: status[name].strip() for name in ("SigPnd", "ShdPnd", "SigBlk")},
               "stdio_targets": {}}
        for fd in ("0", "1", "2"):
            try:
                row["stdio_targets"][fd] = os.readlink(path / "fd" / fd)
            except PermissionError:
                row["stdio_targets"][fd] = "not readable without privilege"
        if stat[0] == "Z":
            row["raw_wait_status"] = int(stat[49])
            row["decoded_exit_code"] = os.waitstatus_to_exitcode(int(stat[49]))
        processes.append(row)
    pipe_owners = []
    for path in Path("/proc/7522/fd").iterdir():
        try:
            target = os.readlink(path)
            if target in ("pipe:[7328215]", "pipe:[7328216]"):
                pipe_owners.append({"pid": 7522, "fd": path.name, "pipe": target})
        except OSError:
            pass
    calls = []
    wanted = {"call_e9858e4b91fa446f9e3a60ef732cb023", "call_a7bb505a9f08456ba7c60291d367a4ce"}
    for line_no, line in enumerate(SESSION.open(), 1):
        row = json.loads(line)
        item = row.get("payload", {})
        if item.get("call_id") not in wanted:
            continue
        data = item.get("input", item.get("output", ""))
        flat = "\n".join(texts(data))
        entry = {"line": line_no, "timestamp": row["timestamp"], "type": item["type"],
                 "call_id": item["call_id"], "payload_sha256": hashlib.sha256(json.dumps(data).encode()).hexdigest()}
        if item["type"] == "custom_tool_call":
            entry["features"] = {value: value in flat for value in ("sudo -n", "nohup", "timeout", "SIGSTOP", "SIGINT", "SIGCONT")}
            entry["signal_source"] = re.findall(r"os\.kill\(pid,signal\.SIG[A-Z]+\)", flat)
            entry["target_measurement_script"] = "cmd='eval/p2-1-pipeline-20261016T073754Z/measure_runtime.py'" in flat
        else:
            entry["safe_execution_markers"] = sorted(set(re.findall(
                r'driver_interrupt\s*\[[0-9, ]*\]|session_id[^0-9]{0,8}[0-9]+|exit_code[^0-9-]{0,8}-?[0-9]+', flat)))
        calls.append(entry)
    service = subprocess.check_output(["systemctl", "show", "lecturelens-live-backend.service",
        "--property=Id,ActiveState,SubState,MainPID,ExecMainStartTimestampMonotonic"], text=True)
    memory = {line.split(":")[0]: int(line.split()[1]) for line in Path("/proc/meminfo").read_text().splitlines()
              if line.split(":")[0] in ("MemTotal", "MemAvailable")}
    record = {"at_utc": dt.datetime.now(dt.timezone.utc).isoformat(), "processes": processes,
              "codex_pipe_readers": pipe_owners,
              "historical_session_path": str(SESSION), "sanitized_historical_calls": calls,
              "live_backend_readonly_identity": dict(line.split("=", 1) for line in service.splitlines()),
              "resource_sample": {"load_average": os.getloadavg(), "cpu_count": os.cpu_count(),
                                  "memory_KiB": memory, "uptime_seconds": time.clock_gettime(time.CLOCK_BOOTTIME)},
              "process_arguments_or_environments_read": False,
              "existing_processes_signaled": False, "service_control_actions": [], "container_actions": []}
    output.write_text(json.dumps(record, indent=2) + "\n")
    print(json.dumps({"record": str(output.relative_to(ROOT)), "existing_chain_preserved": all(row["same_identity_as_initial_observation"] for row in processes)}))


if __name__ == "__main__":
    main()
