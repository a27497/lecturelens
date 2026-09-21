"""Run one isolated demo component. Runtime secrets stay in ignored local JSON."""

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("component", choices=["agent", "backend", "frontend"])
    parser.add_argument(
        "--runtime", type=Path, default=ROOT / ".data/phase-completion-20260920/runtime.local.json"
    )
    parser.add_argument("--session", type=Path, default=ROOT / ".data/recruiter-demo/session.local.json")
    parser.add_argument(
        "--jar", type=Path, default=ROOT / "backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar"
    )
    args = parser.parse_args()
    runtime = json.loads(args.runtime.read_text())
    # Fail closed if a maintainer accidentally supplies the live profile.
    if runtime.get("APP_PORT") != "8084" or "lecturelens_learning_loop" not in runtime.get(
        "MYSQL_JDBC_URL", ""
    ):
        parser.error("Use the isolated learning-loop runtime profile (Java 8084), never the online profile")
    env = {**os.environ, **{k: str(v) for k, v in runtime.items()}}
    env.update(
        SERVER_ADDRESS="127.0.0.1",
        APP_PORT="8084",
        AGENT_SERVICE_URL="http://127.0.0.1:8094",
        AGENT_JAVA_BASE_URL="http://127.0.0.1:8084",
        COURSE_LINGO_BASE_URL="http://127.0.0.1:5184",
        AGENT_COURSE_TOOL_TRANSPORT="internal",
        PYTHONPATH=str(ROOT / "agent-service/src"),
    )
    if args.component == "frontend":
        session = json.loads(args.session.read_text())
        if session["base_url"] != "http://127.0.0.1:8084":
            parser.error("Sample course must belong to the isolated Java instance")
        # This dedicated synthetic account is intentionally shared with local demo visitors.
        # Never pass an ordinary user's credentials or a model/provider key here.
        env.update(
            VITE_BACKEND_PROXY_TARGET="http://127.0.0.1:8084",
            VITE_API_BASE_URL="",
            VITE_RECRUITER_DEMO_COURSE_ID=session["task_id"],
            VITE_RECRUITER_DEMO_EMAIL=session["credentials"]["email"],
            VITE_RECRUITER_DEMO_PASSWORD=session["credentials"]["password"],
        )
        command = ["npm", "run", "dev", "--", "--host", "127.0.0.1", "--port", "5184", "--strictPort"]
        cwd = ROOT / "frontend"
    elif args.component == "agent":
        command = [
            str(ROOT / "agent-service/.venv/bin/python"),
            "-m",
            "uvicorn",
            "lecturelens_agent.app:create_app",
            "--factory",
            "--host",
            "127.0.0.1",
            "--port",
            "8094",
        ]
        cwd = ROOT
    else:
        command = ["java", "-jar", str(args.jar.resolve())]
        cwd = ROOT
    return subprocess.call(command, cwd=cwd, env=env)


if __name__ == "__main__":
    sys.exit(main())
