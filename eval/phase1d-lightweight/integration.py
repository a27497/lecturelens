"""Real Java/Python/PG/Vue/Chromium with authored Mock outputs, fresh resources only."""

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "phase1d_base", ROOT / "scripts/ci/mock-study-tutor-e2e.py"
)
BASE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(BASE)
PYTHON = "/home/dev/.codex/worktrees/phase0-integration-20261108/lecturelens/agent-service/.venv/bin/python"
PHASE0 = Path("/home/dev/.codex/worktrees/phase0-integration-20261108/lecturelens")


class Smoke(BASE.Smoke):
    def preflight(self):
        super().preflight()
        self.env.update(
            TUTOR_ENGINE="light",
            PHASE1D_REQUEST_LOG=str(self.out / "authored-requests.jsonl"),
            JAVA_TOOL_OPTIONS="-Xmx512m -XX:ActiveProcessorCount=2",
            OMP_NUM_THREADS="1",
        )
        self.env["PYTHONPATH"] += (
            os.pathsep
            + str(ROOT / "agent-service/src")
            + os.pathsep
            + str(ROOT / "eval/phase1d-lightweight")
        )
        self.result["not_run"] = [
            "real-model quality",
            "paid adapter/dollar ledger integration",
            "GitHub CI PENDING",
        ]
        self.result["phase1d_candidate"] = json.loads(
            (ROOT / "eval/phase1d-lightweight/CANDIDATE.json").read_text()
        )
        for relative, digest in self.result["phase1d_candidate"][
            "modules_sha256"
        ].items():
            assert hashlib.sha256((ROOT / relative).read_bytes()).hexdigest() == digest
        self.result["phase1d_harness_sha256"] = hashlib.sha256(
            Path(__file__).read_bytes()
        ).hexdigest()

        override = self.out / "loopback.compose.yaml"
        text = override.read_text()
        for service, limit in {
            "mysql": "512m",
            "redis": "96m",
            "minio": "384m",
            "rocketmq-namesrv": "384m",
            "rocketmq-broker": "1024m",
        }.items():
            text = text.replace(
                f"  {service}:\n", f"  {service}:\n    mem_limit: {limit}\n"
            )
        text = text.replace(
            "  rocketmq-namesrv:\n",
            "  rocketmq-namesrv:\n    environment:\n      JAVA_OPT_EXT: -Xms64m -Xmx192m -Xmn32m -XX:MaxDirectMemorySize=64m -XX:ActiveProcessorCount=2\n",
        )
        text = text.replace(
            "  rocketmq-broker:\n",
            "  rocketmq-broker:\n    environment:\n      JAVA_OPT_EXT: -Dcom.rocketmq.proxy.configPath=/tmp/rmq-proxy.json -Xms64m -Xmx384m -Xmn64m -XX:MaxDirectMemorySize=256m -XX:ActiveProcessorCount=2\n",
        )
        override.write_text(text)

    def compose(self, project, *args):
        # Preserve this task's test volumes as audit assets. Never target old projects.
        return super().compose(project, *(a for a in args if a != "-v"))

    def dependencies(self):
        # Java source, resources and dependency descriptor are byte-identical to Phase 0.
        assert not self.capture(
            ["git", "diff", "17d78636cf97fcf55fe642b1ecc30c5e2ea48865", "--", "backend"]
        )
        original = PHASE0 / "backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar"
        self.jar = self.out / original.name
        shutil.copy2(original, self.jar)
        self.result["java_jar_sha256"] = hashlib.sha256(
            self.jar.read_bytes()
        ).hexdigest()
        shutil.copytree(
            self.args.embedding_cache_source, self.out / "agent-cache/models"
        )
        assert Path(PYTHON).exists()

    def start_agent(self):
        self.free_port(self.result["ports"]["AGENT_HTTP_PORT"])
        process = self.spawn(
            [
                PYTHON,
                "-m",
                "uvicorn",
                "mock_app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.result["ports"]["AGENT_HTTP_PORT"]),
            ],
            "agent",
            ROOT / "agent-service",
        )
        self.health(process, self.agent_base, "/healthz")
        return process

    def new_session(self, key):
        session = self.api("POST", self.tutor, {"request_key": key})["session"]
        assert (
            session["engine"] == "light"
            and session["max_turns"] == session["max_calls"] == 6
        )
        self.session_path = self.tutor + "/" + session["session_id"]
        return session

    def browser(self):
        self.env["VITE_BACKEND_PROXY_TARGET"] = self.base
        port = self.free_port(0)
        vite = self.spawn(
            [
                "node",
                "node_modules/vite/bin/vite.js",
                "--host",
                "127.0.0.1",
                "--port",
                str(port),
                "--strictPort",
            ],
            "vite",
            ROOT / "frontend",
        )
        self.health(vite, f"http://127.0.0.1:{port}", "/")
        process = subprocess.Popen(
            ["node", str(ROOT / "eval/phase1d-lightweight/browser.mjs")],
            cwd=ROOT,
            env=self.env,
            stdin=subprocess.PIPE,
            start_new_session=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        self.children.append(
            (process, type("Joined", (), {"join": lambda *a, **k: None})())
        )
        output, _ = process.communicate(
            json.dumps(
                {
                    "base": f"http://127.0.0.1:{port}",
                    "task": self.task,
                    "token": self.token,
                    "out": str(self.out),
                }
            ),
            timeout=180,
        )
        (self.out / "browser-process.log").write_text(self.redact(output))
        assert process.returncode == 0, (
            f"Chromium exited {process.returncode}; see browser-process.log"
        )
        self.result["browser"] = json.loads((self.out / "browser.json").read_text())

    def isolation(self):
        self.token = ""
        self.login()
        try:
            for method, path, body in [
                ("GET", self.tutor, None),
                ("GET", self.session_path, None),
                ("POST", self.tutor, {"request_key": "stranger"}),
            ]:
                self.api(method, path, body, expected=404)
                self.result["cross_account"][method + " " + path] = 404
        finally:
            self.token = self.owner_token
        # Revision changes only in this newly created synthetic course's isolated MySQL.
        self.sql(
            f"UPDATE analysis_task SET content_revision=content_revision+1 WHERE id='{self.task}'"
        )
        self.api("GET", self.session_path, expected=409)
        self.result["revision_fence"] = "HTTP 409; stale saved history not served"

    def export(self):
        forbidden = [
            t
            for t in self.sql("SHOW TABLES").splitlines()
            if re.match(r"^(tutor|study|agent_model|checkpoint)(_|$)", t)
        ]
        assert not forbidden
        assert (
            self.sql(
                f"SELECT count(*) FROM tutor_session WHERE owner_id<>{self.owner} OR course_id<>'{self.task}'",
                pg=True,
            )
            == "0"
        )
        self.result["state_ownership"] = {
            "mysql_agent_tables": forbidden,
            "all_pg_tutor_sessions_in_authorized_scope": True,
        }
        for table in ("tutor_session", "tutor_turn"):
            body = self.sql(
                f"SELECT coalesce(json_agg(row_to_json(t)), '[]') FROM {table} t",
                pg=True,
            )
            (self.out / f"{table}.json").write_text(body + "\n")
        turns = json.loads((self.out / "tutor_turn.json").read_text())
        assert all(
            t["model_calls"] <= 1 and t["reserved_tokens"] <= 64000 for t in turns
        )
        self.result["bounds"] = {
            "turns": len(turns),
            "mock_requests": sum(t["model_calls"] for t in turns),
            "max_reserved": max(t["reserved_tokens"] for t in turns),
            "real_requests": 0,
            "local_cost_usd": "0; mock only",
            "automatic_retries": 0,
        }

    def execute(self):
        signal.signal(
            signal.SIGTERM,
            lambda *_: (_ for _ in ()).throw(
                TimeoutError("Stopped; task-owned cleanup")
            ),
        )
        success = False
        try:
            for name, action in [
                ("preflight", self.preflight),
                ("dependencies", self.dependencies),
                ("infrastructure", self.infrastructure),
                ("Java", self.java),
            ]:
                with self.stage(name):
                    action()
            with self.stage("PostgreSQL"):
                self.owned.append(BASE.AGENT)
                self.run(
                    self.compose(
                        BASE.AGENT, "up", "-d", "--wait", "--wait-timeout", "90"
                    ),
                    "pg-up",
                    100,
                )
            with self.stage("Agent"):
                agent = self.start_agent()
            with self.stage("synthetic-course"):
                self.course()
            browser_passed = True
            try:
                with self.stage("browser-learning"):
                    self.browser()
            except AssertionError as error:
                browser_passed = False
                self.result["browser_error"] = self.redact(str(error))
            with self.stage("queued-cancel-and-restart"):
                session = self.new_session("cancel-session")
                hold = self.out / "queue-lock"
                locker = self.spawn(
                    [
                        PYTHON,
                        str(ROOT / "eval/phase1d-lightweight/hold_session.py"),
                        session["session_id"],
                        str(hold),
                    ],
                    "queue-lock",
                )
                try:
                    self.wait(
                        lambda: (hold / "ready").exists(),
                        bool,
                        10,
                        "own session advisory lock",
                    )
                    self.queued_cancel()
                finally:
                    (hold / "release").touch()
                    self.stop(locker)
                before = self.api("GET", self.session_path)
                self.stop(agent, kill=True)
                agent = self.start_agent()
                assert self.api("GET", self.session_path) == before
            with self.stage("running-cancel"):
                self.running_cancel()
                before = self.api("GET", self.session_path)
                self.stop(agent, kill=True)
                agent = self.start_agent()
                assert self.api("GET", self.session_path) == before
            with self.stage("zero-paid-models"):
                self.zero_models()
            with self.stage("ownership-version"):
                self.isolation()
            with self.stage("execution-budget-evidence"):
                self.export()
            success = browser_passed
        except BaseException as error:  # noqa: BLE001 -- all paths visit task-owned cleanup
            self.result["error"] = self.redact(str(error))
            print("FAIL " + self.result["error"], flush=True)
        finally:
            try:
                with self.stage("cleanup"):
                    self.cleanup()
            except BaseException:  # noqa: BLE001 -- cleanup failure must not hide the earlier failure
                success = False
            self.result["status"] = "PASS" if success else "FAIL"
            self.save()
        return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--embedding-cache-source", type=Path, required=True)
    parser.add_argument("--instance", required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"[a-z][a-z0-9-]{1,42}", args.instance):
        parser.error("Use a new lowercase task-owned instance identity")
    BASE.DEMO = f"lecturelens-{args.instance}-demo"
    BASE.AGENT = f"lecturelens-{args.instance}-agent"
    args.legacy_only = False
    raise SystemExit(Smoke(args).execute())
