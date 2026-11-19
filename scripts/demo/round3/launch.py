#!/usr/bin/env python3
"""Isolated loopback-only Round 3 candidate, using the existing demo stack."""
import argparse
import json
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
from stack import DEMO_EMAIL, ROOT, Stack

PACK = ROOT / "fixtures/demo/round3"
COURSE = json.loads((PACK / "demo-courses.json").read_text())["courses"][0]
INSTANCE = "ll-p06-round3"
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
            ROUND3_DEMO_STATE=str(self.state_file),
            ROUND3_DEMO_ORIGIN=f"http://127.0.0.1:{ports['WEB_PORT']}",
            ROUND3_DEMO_PASSWORD=secret["DEMO_PASSWORD"],
            ROUND3_DEMO_EMAIL=DEMO_EMAIL,
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
        super().seed(secret)
        task = self.state["task_id"]
        account = self.api(
            "POST", "/api/auth/login", {"email": DEMO_EMAIL, "password": secret["DEMO_PASSWORD"]},
        )
        self.state["round3_owner"] = str(account["user"]["userId"])
        self.save()
        token = account["accessToken"]
        tutor = f"/api/tasks/{task}/tutor/sessions"
        for conversation in reversed(COURSE["conversations"]):
            session = self.api("POST", tutor, {"request_key": "round3-" + conversation["id"]}, token)["session"]
            path = f"{tutor}/{session['session_id']}/turns"
            for index, turn in enumerate(conversation["turns"]):
                self.api("POST", path, {
                    "client_turn_id": f"round3-{conversation['id']}-{index}",
                    "text": turn["question"], "socratic": False,
                }, token)

        path = f"/api/tasks/{task}/study/command"
        session = self.api("POST", path, {"operation": "CREATE_SESSION", "request_key": "round3-practice"}, token)
        scope = {"session_id": session["session_id"]}
        response = self.api("POST", path, {
            **scope, "operation": "START", "request_key": "round3-practice",
            "goal": "复习二分查找", "practice_format": "choice",
        }, token)
        run = response["run"]["run_id"]
        deadline = time.monotonic() + 60
        while time.monotonic() < deadline:
            response = self.api("POST", path, {**scope, "operation": "READ", "run_id": run}, token)
            status = response["run"]["status"]
            if status == "succeeded":
                self.state["round3_practice"] = {"session_id": scope["session_id"], "run_id": run,
                                                  "artifact_id": response["artifact"]["artifact_id"]}
                self.save()
                return
            if status not in {"queued", "running"}:
                raise RuntimeError("Round 3 practice fixture failed")
            time.sleep(.5)
        raise RuntimeError("Round 3 practice fixture timed out")


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
