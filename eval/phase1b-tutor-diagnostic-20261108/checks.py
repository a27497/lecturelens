"""Outer-process tests only; no PostgreSQL or native model execution is needed."""

import argparse
import os
import sys
from pathlib import Path

import pytest

if os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
    raise SystemExit("FROZEN_SOCKET_FENCE_REQUIRED")
base = Path(__file__).resolve().parent
sys.path.insert(0, str(Path.cwd() / "agent-service/tests"))
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--output", type=Path, required=True)
output = parser.parse_args().output.resolve()
if not output.is_relative_to(Path.cwd() / ".data/phase1b"):
    raise SystemExit("PRIVATE_PHASE1B_OUTPUT_REQUIRED")
output.mkdir(parents=True, exist_ok=False, mode=0o700)
raise SystemExit(
    pytest.main(
        [
            "-q",
            str(base / "test_workflow.py"),
            str(base / "test_risk_once.py"),
            str(base.parent / "phase1a-tutor-readiness-20261108/test_quality_gate.py"),
            str(base.parent / "phase1a-tutor-readiness-20261108/test_launch.py"),
            str(base.parent / "phase1a-tutor-readiness-20261108/test_readiness.py")
            + "::test_admission_refuses_expansion_before_transport_or_secret",
            str(base.parent / "phase1a-tutor-readiness-20261108/test_readiness.py")
            + "::test_admission_checks_exact_head_and_price_age",
            str(base.parent / "phase1a-tutor-readiness-20261108/test_readiness.py")
            + "::test_single_use_claim_refuses_repeat_and_symlink",
            "--junitxml=" + str(output / "results.xml"),
            "--basetemp=" + str(output / "pytest"),
        ]
    )
)
