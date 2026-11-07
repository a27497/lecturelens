"""Offline audit launcher. No live mode, provider credentials, or product writes."""

import argparse
import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    assert os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") == "1"
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["TUTOR_AUDIT_OUTPUT"] = str(output)
    os.environ["AGENT_TEST_DATABASE_URL"] = (
        "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
    )
    import pytest

    code = pytest.main(
        [
            "-q",
            str(ROOT / "scripts/dev/test_tutor_zero_cost_audit.py"),
            "--junitxml=" + str(output / "results.xml"),
            "--basetemp=" + str(output / "pytest"),
        ]
    )
    (output / "execution.json").write_text(
        json.dumps(
            {
                "pytest_exit": code,
                "real_model_calls": 0,
                "embedding_calls": 0,
                "reviewer_calls": 0,
                "cost_usd": "0",
                "mode": "MOCK_AND_RETAINED_ARTIFACTS_ONLY",
                "real_quality_improvement": "NOT_RUN",
            },
            indent=2,
        )
        + "\n"
    )
    return code


if __name__ == "__main__":
    raise SystemExit(main())
