"""Run the frozen v14 entry and its historical suites inside safe_exec's socket fence."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    if os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
        raise SystemExit("Use eval/tutor-scale/safe_exec.py; unguarded execution forbidden")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--collect-only", action="store_true")
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    os.environ["AGENT_TEST_DATABASE_URL"] = (
        "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
    )
    # The frozen entry's live-fence test must pass the earlier opt-in check first.
    # This is only a test switch: safe_exec denies external egress and all model
    # execution uses MockTransport. A separate regression proves missing opt-in refusal.
    os.environ["LECTURELENS_REAL_EVAL"] = "1"
    for key, folder in (
        ("V14_CHECK_OUTPUT", "v14"),
        ("V12_ENTRY_CHECK_OUTPUT", "v12"),
        ("V13_CHECK_OUTPUT", "v13"),
        ("V14_FRESH_CHECK_OUTPUT", "fresh"),
        ("V14_ASSET_CHECK_OUTPUT", "assets"),
    ):
        os.environ[key] = str(output / folder)
    sys.path.insert(0, str(ROOT / "eval/tutor-v14-fresh-v1"))
    import run_fresh

    prepared = run_fresh.run(
        run_fresh.parser().parse_args(
            [
                "--agent",
                "p8-tutor-draft-repair-v14-development",
                "--model",
                "deepseek-flash",
            ]
        )
    )
    (output / "actual-entry-preflight.json").write_text(json.dumps(prepared, indent=2) + "\n")
    (output / "version.json").write_text(
        json.dumps(
            dict(
                sha=subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
                real_calls=0,
                test_live_switch_only=True,
                socket_fence_required=True,
            ),
            indent=2,
        )
        + "\n"
    )
    import pytest

    paths = [
        "eval/tutor-v14-offline-v1/test_v14.py",
        "eval/tutor-v12-rerun-v1/test_run.py",
        "eval/tutor-v13-grounding-v1/test_grounding.py",
        "agent-service/tests/test_tutor.py",
        "eval/tutor-v14-fresh-v1/test_fresh.py",
        "scripts/dev/test_v14_assets.py",
    ]
    return pytest.main(
        [
            "-q",
            *paths,
            "--junitxml=" + str(output / "results.xml"),
            "--basetemp=" + str(output / "pytest"),
            *(["--collect-only"] if args.collect_only else []),
        ]
    )


if __name__ == "__main__":
    raise SystemExit(main())
