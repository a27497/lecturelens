"""Supervised, fenced v14 retained-response diagnosis; never a live sender."""

import argparse
import json
import os
import sys
from pathlib import Path

import v14_delivery_diagnosis as D


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    assert args.output.is_dir() and not (args.output / "diagnosis.json").exists()
    os.environ["AGENT_TEST_DATABASE_URL"] = (
        "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
    )
    os.environ["V14_DIAGNOSIS_OUTPUT"] = str(args.output.resolve())
    analysis = D.analyze()
    (args.output / "diagnosis.json").write_text(json.dumps(analysis, indent=2) + "\n")
    import pytest

    pytest_args = [
        "-q",
        str(D.ROOT / "scripts/dev/test_v14_delivery_diagnosis.py"),
        "--junitxml=" + str(args.output / "results.xml"),
        "--basetemp=" + str(args.output / "pytest"),
    ]
    if args.collect_only:
        pytest_args.append("--collect-only")
    return pytest.main(pytest_args)


if __name__ == "__main__":
    sys.exit(main())
