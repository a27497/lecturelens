"""Supervised v17 checks, with explicit isolated PG and no credential access."""

import argparse
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--stage", default="")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    args.output.mkdir(parents=True, exist_ok=False)
    os.environ["TUTOR_FOLLOWUP_OUTPUT"] = str(args.output.resolve())
    os.environ["AGENT_TEST_DATABASE_URL"] = (
        "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
    )
    import pytest

    return pytest.main(
        [
            "-q",
            "agent-service/tests/test_tutor_v17.py",
            "-k",
            args.stage,
            "--junitxml=" + str(args.output / "results.xml"),
            "--basetemp=" + str(args.output / "pytest"),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
