"""Run/resume a new serial batch without overwriting the saved baseline."""

import argparse
import importlib.util
import sys
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--batch", type=Path, required=True)
    parser.add_argument("--trials", type=int, default=2)
    args = parser.parse_args()
    baseline = Path(__file__).resolve().parent / "batch-v2"
    if args.batch.resolve() == baseline:
        raise ValueError("Use a new output directory; do not overwrite baseline")
    spec = importlib.util.spec_from_file_location(
        "asr_baseline_driver", Path(__file__).with_name("run-final.py")
    )
    driver = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(driver)
    driver.BATCH = args.batch.resolve()
    sys.argv = [sys.argv[0], "--trials", str(args.trials)]
    driver.main()


if __name__ == "__main__":
    main()
