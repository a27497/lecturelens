"""Prepare once, then run independent local fixtures with bounded concurrency."""
import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

from langgraph.checkpoint.postgres import PostgresSaver
from lecturelens_agent.study.store import StudyStore


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--label", required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--workers", type=int, default=4)
    args = parser.parse_args()
    if args.samples % args.workers or not 1 <= args.workers <= 4 or args.output.exists():
        raise SystemExit("Use 1-4 workers, divisible samples and a new output file")
    dsn = os.environ["AGENT_TEST_DATABASE_URL"]
    if "fault_test" not in dsn.rsplit("/", 1)[-1]:
        raise SystemExit("Use the dedicated fault_test database")
    store = StudyStore(dsn)
    store.initialize()
    with PostgresSaver.from_conn_string(dsn) as saver:
        saver.setup()
    script = Path(__file__).with_name("run.py")
    per_worker = args.samples // args.workers
    jobs, logs, files = [], [], []
    try:
        for worker in range(args.workers):
            output = args.output.with_name(f"{args.output.stem}-worker-{worker}.jsonl")
            log = output.with_suffix(".log").open("x")
            logs.append(log)
            files.append(output)
            jobs.append(subprocess.Popen([sys.executable, str(script), "--label", args.label,
                "--output", str(output), "--samples", str(per_worker), "--trial-offset", str(worker * per_worker),
                "--prepared-database"], stdout=log, stderr=subprocess.STDOUT, env=os.environ.copy()))
        for worker, job in enumerate(jobs):
            code = job.wait()
            if code:
                raise SystemExit(f"Worker {worker} failed ({code}); raw partial files retained")
            print(f"{args.label}: worker {worker + 1}/{args.workers} complete", flush=True)
        rows = [json.loads(line) for file in files for line in file.read_text().splitlines()]
        assert len({(r["trial"], r["scenario"]) for r in rows}) == len(rows)
        assert all(len([r for r in rows if r["scenario"] == s]) == args.samples for s in {r["scenario"] for r in rows})
        with args.output.open("x") as out:
            for row in sorted(rows, key=lambda r: (r["trial"], r["scenario"])):
                out.write(json.dumps(row, ensure_ascii=False) + "\n")
        manifest = {"workers": args.workers, "samples_per_scenario": args.samples,
                    "rows": len(rows), "script_sha256": hashlib.sha256(script.read_bytes()).hexdigest(),
                    "raw_files": {str(f.name): hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
        args.output.with_suffix(".manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    finally:
        for job in jobs:
            if job.poll() is None:
                job.terminate()
                job.wait()
        for log in logs:
            log.close()


if __name__ == "__main__":
    main()
