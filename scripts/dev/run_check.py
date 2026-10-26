"""Run a local check with a durable log, timeout and process-group cleanup."""
import argparse
import json
import os
import signal
import subprocess
import time
from pathlib import Path

p = argparse.ArgumentParser()
p.add_argument('--name', required=True)
p.add_argument('--timeout', type=int, default=1200)
p.add_argument('--output', default='.data/p7/checks')
p.add_argument('command', nargs=argparse.REMAINDER)
a = p.parse_args()
command = a.command[1:] if a.command[:1] == ['--'] else a.command
out = Path(a.output)
out.mkdir(parents=True, exist_ok=True)
started = time.monotonic()
with (out / (a.name + '.log')).open('w') as log:
    process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        code = process.wait(timeout=a.timeout)
    except (subprocess.TimeoutExpired, KeyboardInterrupt):
        os.killpg(process.pid, signal.SIGTERM)
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            os.killpg(process.pid, signal.SIGKILL)
            process.wait()
        code = 124
result = dict(name=a.name, command=command, code=code, seconds=round(time.monotonic()-started, 3))
(out / (a.name + '.json')).write_text(json.dumps(result, indent=2)+'\n')
print(json.dumps(result))
raise SystemExit(code)
