"""Serial, exclusive measurement windows with host/process audit; no tests here."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent


def utc():
    return datetime.now(timezone.utc).isoformat()


def cpu():
    return [int(x) for x in Path('/proc/stat').read_text().splitlines()[0].split()[1:9]]


def processes(root_pid):
    rows = {}
    for path in Path('/proc').iterdir():
        if path.name.isdecimal():
            try:
                stat = (path / 'stat').read_text().rsplit(')', 1)[1].split()
                rows[int(path.name)] = (int(stat[1]), (path / 'comm').read_text().strip(),
                                       (path / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace'))
            except (OSError, ValueError, IndexError):
                pass
    own = {root_pid}
    while True:
        children = {pid for pid, (parent, _, _) in rows.items() if parent in own}
        if children <= own:
            break
        own |= children
    unexpected = []
    for pid, (_, name, command) in rows.items():
        if pid in own or name in {'bash', 'sh', 'rg'}:
            continue
        if name == 'pytest' or (name.startswith('python') and any(x in command for x in
            ['/pytest', 'scripts/eval/', 'tool-resilience', 'lecturelens_agent.benchmark'])):
            unexpected.append({'pid': pid, 'name': name})
    return unexpected


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--phase', choices=['healthy', 'faults'], required=True)
    parser.add_argument('--baseline-source', type=Path, required=True)
    parser.add_argument('--before-source', type=Path, required=True)
    parser.add_argument('--candidate-source', type=Path, required=True)
    parser.add_argument('--output-dir', type=Path, default=ROOT)
    args = parser.parse_args()
    output_root = args.output_dir
    output_root.mkdir(parents=True, exist_ok=True)
    audit = output_root / f'{args.phase}-audit.json'
    if audit.exists():
        raise SystemExit('Use a fresh measurement directory')
    if processes(os.getpid()):
        raise SystemExit('Another evaluation or pytest process is running')
    if args.phase == 'healthy':
        labels = [('baseline', args.baseline_source), ('before', args.before_source), ('candidate', args.candidate_source)]
    else:
        labels = [('baseline', args.baseline_source), ('candidate', args.candidate_source)]
    records = []
    for label, source in labels:
        output = output_root / f'{args.phase}-{label}.jsonl'
        stopped = threading.Event()
        snapshots = []
        def sample():
            previous = cpu()
            while not stopped.wait(1):
                current = cpu()
                delta = [a-b for a, b in zip(current, previous, strict=True)]
                total = sum(delta)
                snapshots.append({'at_utc': utc(), 'cpu_busy_percent': 100*(total-delta[3]-delta[4])/total if total else None,
                                  'loadavg': Path('/proc/loadavg').read_text().split()[:3],
                                  'unexpected_eval_or_test_processes': processes(os.getpid())})
                previous = current
        watcher = threading.Thread(target=sample, daemon=True)
        started = utc()
        watcher.start()
        command = [sys.executable, str(ROOT / 'run.py'), '--label', f'{args.phase}-{label}',
                   '--output', str(output), '--samples', '20']
        if args.phase == 'healthy':
            command += ['--scenarios', 'healthy']
        try:
            with (output_root / f'{args.phase}-{label}.log').open('x') as log:
                result = subprocess.run(command, env={**os.environ, 'PYTHONPATH': str(source)},
                                        stdout=log, stderr=subprocess.STDOUT)
        finally:
            stopped.set()
            watcher.join()
        record = {'label': label, 'started_at_utc': started, 'finished_at_utc': utc(),
                  'source_root': str(source), 'returncode': result.returncode,
                  'samples_per_scenario': 20, 'serial_workers': 1, 'host_samples': snapshots,
                  'raw_sha256': hashlib.sha256(output.read_bytes()).hexdigest() if output.exists() else None}
        records.append(record)
        audit.write_text(json.dumps(records, indent=2) + '\n')
        if result.returncode or any(x['unexpected_eval_or_test_processes'] for x in snapshots):
            raise SystemExit('Measurement failed or overlapped another test/evaluation; records retained')
        print(f'{args.phase}: {label} complete', flush=True)


if __name__ == '__main__':
    main()
