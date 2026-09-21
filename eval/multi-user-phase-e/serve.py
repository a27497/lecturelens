"""Isolated 8094 API; the Phase E driver dispatches only its own newly created Runs."""

import json
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def configure():
    runtime = json.loads((ROOT / ".data/phase-completion-20260920/runtime.local.json").read_text())
    if runtime.get("APP_PORT") != "8084" or "lecturelens_learning_loop" not in runtime.get(
        "MYSQL_JDBC_URL", ""
    ):
        raise RuntimeError("Phase E requires the isolated learning-loop profile")
    os.environ.update({k: str(v) for k, v in runtime.items()})
    os.environ.update(AGENT_JAVA_BASE_URL="http://127.0.0.1:8084", AGENT_COURSE_TOOL_TRANSPORT="internal")


if __name__ == "__main__":
    configure()
    import uvicorn

    from lecturelens_agent.study.runtime import StudyRuntime

    StudyRuntime.start = lambda self: None
    uvicorn.run("lecturelens_agent.app:create_app", factory=True, host="127.0.0.1", port=8094)
