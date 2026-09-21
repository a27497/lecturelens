"""Isolated acceptance API: normal services, explicitly driven Study Runs only."""

import argparse
import os

import uvicorn

from lecturelens_agent.study.runtime import StudyRuntime

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--port", type=int, default=8094)
args = parser.parse_args()
if os.environ.get("AGENT_COURSE_TOOL_TRANSPORT") != "mcp":
    parser.error("Set AGENT_COURSE_TOOL_TRANSPORT=mcp for this acceptance server")

# Only this eval entry point pauses automatic dequeue. run.py drives its new Runs.
StudyRuntime.start = lambda self: None
uvicorn.run("lecturelens_agent.app:create_app", factory=True, host="127.0.0.1", port=args.port)
