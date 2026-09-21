"""Prepare independent users/courses using the existing register/login/upload pipeline."""

import argparse
import concurrent.futures
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--users", type=int, default=50)
    parser.add_argument("--workers", type=int, default=3)
    parser.add_argument("--output", type=Path, default=ROOT / ".data/multi-user-phase-e/users")
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(parents=True, exist_ok=True)

    def prepare(i):
        folder = args.output / f"user-{i:02}"
        folder.mkdir(exist_ok=True)
        # Append logs; the existing preparation entry point resumes saved uploads.
        with (folder / "prepare.log").open("a") as log:
            result = subprocess.run(
                [
                    sys.executable,
                    str(ROOT / "scripts/eval/accept-study-agent.py"),
                    "--phase",
                    "prepare",
                    "--base-url",
                    "http://127.0.0.1:8084",
                    "--output",
                    str(folder),
                    "--video",
                    str(ROOT / ".data/l22-eval/sources/strings.mp4"),
                ],
                stdout=log,
                stderr=log,
                timeout=1100,
            )
        print(json.dumps({"user": i, "exit_code": result.returncode}), flush=True)
        return result.returncode

    with concurrent.futures.ThreadPoolExecutor(max_workers=args.workers) as pool:
        codes = list(pool.map(prepare, range(args.users)))
    if any(codes):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
