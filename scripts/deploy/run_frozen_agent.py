#!/usr/bin/env python3
"""Run a frozen Agent using the deployment's existing opaque environment loader."""

import argparse
import os
from pathlib import Path
import runpy
import sys


def frozen_command(release, argv, environment):
    release = Path(release).resolve()
    command = list(argv)
    if command[1:4] != ["-m", "uvicorn", "lecturelens_agent.app:create_app"]:
        raise RuntimeError("The legacy loader did not select the Agent command")
    command[0] = str(release / "agent-service/.venv/bin/python")
    forwarded = dict(environment)
    forwarded["PYTHONPATH"] = str(release / "agent-service/src")
    forwarded["STUDY_FEEDBACK_ENABLED"] = "true"
    return command, forwarded


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--release", required=True, type=Path)
    parser.add_argument("--legacy-launcher", required=True, type=Path)
    args = parser.parse_args()
    release = args.release.resolve()
    if not (release / "agent-service/uv.lock").is_file():
        raise RuntimeError("The frozen release has no lockfile")
    original_execve = os.execve

    def launch(_executable, argv, environment):
        command, forwarded = frozen_command(release, argv, environment)
        os.chdir(release / "agent-service")
        original_execve(command[0], command, forwarded)

    # Preserve credential loading and all existing feature values without inspecting
    # them. Only the frozen source/interpreter and explicit feedback opt-in differ.
    os.execve = launch
    sys.argv = [str(args.legacy_launcher), "agent"]
    runpy.run_path(str(args.legacy_launcher), run_name="__main__")
    raise RuntimeError("The legacy loader returned without starting the Agent")


if __name__ == "__main__":
    main()
