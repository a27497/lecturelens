#!/usr/bin/env python3
"""Isolated loopback-only Round 3 candidate, using the existing demo stack."""
import argparse
import json
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from stack import HTTP, ROOT, Stack, log

PACK = ROOT / "fixtures/demo/round3"
COURSE = json.loads((PACK / "demo-courses.json").read_text(encoding="utf-8"))["courses"][0]
INSTANCE = "ll-p07-round3"
WEB_PORT = 5196


class Round3Stack(Stack):
    fixture = PACK / COURSE["media"]
    fixture_filename = COURSE["title"] + ".mp4"

    def choose_ports(self):
        self.state.setdefault("ports", {}).setdefault("WEB_PORT", WEB_PORT)
        return super().choose_ports()

    def java_env(self, ports, secret, real):
        env = super().java_env(ports, secret, real)
        env.update(
            COURSELINGO_ASR_EMBEDDED_SUBTITLE_SEGMENT_DURATION="5s",
            DEMO_MOCK_LLM_ENABLED="false",
            OPENAI_COMPATIBLE_ENABLED="true",
            OPENAI_COMPATIBLE_API_KEY="local-round3-fixture",
            OPENAI_COMPATIBLE_BASE_URL=f"http://127.0.0.1:{ports['AGENT_HTTP_PORT']}/v1",
            OPENAI_COMPATIBLE_MODEL="round3-fixture",
        )
        return env

    def agent_factory(self, real):
        return "candidate:create_app"

    def agent_env(self, ports, secret, real):
        env = super().agent_env(ports, secret, real)
        env.update(
            PYTHONPATH=str(HERE),
            ROUND3_DEMO_ORIGIN=f"http://127.0.0.1:{ports['WEB_PORT']}",
        )
        return env

    def web_env(self):
        env = super().web_env()
        env.update(
            VITE_ROUND3_DEMO="true",
            ROUND3_PROXY_TARGET=f"http://127.0.0.1:{self.state['ports']['AGENT_HTTP_PORT']}",
        )
        return env

    def web_args(self):
        return ["--outDir", str(self.dir / "dist")]

    def build(self):
        super().build()
        self.run(
            ["npm", "run", "build", "--", *self.web_args(), "--emptyOutDir"],
            cwd=ROOT / "frontend", env=self.web_env(), name="build-round3",
        )

    def seed(self, secret):
        port = self.state["ports"]["AGENT_HTTP_PORT"]
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/api/round3/ready", method="POST",
            headers={"X-Round3-Secret": secret["AGENT_SERVICE_SECRET"]},
        )
        log("preparing the first isolated Round 3 visitor")
        with HTTP.open(request, timeout=900) as response:
            if response.status != 200:
                raise RuntimeError("Round 3 visitor preparation failed")

    def report_ready(self, real):
        log(f"Round 3 demo ready in {self.state['ready_seconds']}s")
        print(f"http://127.0.0.1:{self.state['ports']['WEB_PORT']}/tasks", flush=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("command", choices=["up", "down", "status"])
    command = parser.parse_args().command
    stack = Round3Stack(INSTANCE)
    if command == "up":
        stack.up(False)
    elif command == "down":
        stack.down(False)
    else:
        ports = stack.state.get("ports", {})
        print(f"http://127.0.0.1:{ports.get('WEB_PORT', WEB_PORT)}/tasks")
        for name, record in stack.state.get("pids", {}).items():
            print(f"{name}: {'running' if stack.owned(record) else 'stopped'}")


if __name__ == "__main__":
    main()
