"""Use the frozen socket-fenced interpreter and an isolated acceptance PG only."""

import argparse
import os
import sys
from pathlib import Path

import pytest

if os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
    raise SystemExit("FROZEN_SOCKET_FENCE_REQUIRED")
root = Path.cwd()
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
output = args.output.resolve()
if not output.is_relative_to(root / ".data/phase1a"):
    raise SystemExit("PRIVATE_PHASE1A_OUTPUT_REQUIRED")
output.mkdir(parents=True, exist_ok=False)
os.environ["TUTOR_SELECTION_OUTPUT"] = str(output)
os.environ["AGENT_TEST_DATABASE_URL"] = (
    "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
)
sys.path.insert(0, str(root / "agent-service/tests"))
raise SystemExit(
    pytest.main(
        [
            "-q",
            "agent-service/tests/test_tutor_v19.py",
            "agent-service/tests/test_tutor_v19_closeout.py",
            str(Path(__file__).with_name("test_readiness.py")),
            str(Path(__file__).with_name("test_quality_gate.py")),
            str(Path(__file__).with_name("test_launch.py")),
            "-k",
            "not historical and not replays_original_response_bodies",
            "--junitxml=" + str(output / "results.xml"),
            "--basetemp=" + str(output / "pytest"),
        ]
    )
)
