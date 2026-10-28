#!/usr/bin/env python3
"""Isolated real Java -> mock Tutor/Study -> PostgreSQL smoke; no model quality claim.

See mock-study-tutor-e2e.md for prerequisites, offline weight preparation and evidence limits.
Secrets exist only in child environments/memory. Only these two fresh Compose projects are owned.
"""

import argparse
import hashlib
import json
import os
import re
import secrets
import shutil
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import zipfile
from contextlib import contextmanager
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
DEMO = "lecturelens-demo-pr49smoke"
AGENT = "lecturelens-agent-pr49smoke"
PORTS = {
    "APP_PORT": 18180,
    "MYSQL_HOST_PORT": 23406,
    "REDIS_HOST_PORT": 16479,
    "MINIO_API_HOST_PORT": 19100,
    "MINIO_CONSOLE_HOST_PORT": 19101,
    "ROCKETMQ_NAMESRV_HOST_PORT": 19976,
    "ROCKETMQ_PROXY_HOST_PORT": 18181,
    "ROCKETMQ_BROKER_FAST_HOST_PORT": 21009,
    "ROCKETMQ_BROKER_MAIN_HOST_PORT": 21011,
    "ROCKETMQ_BROKER_HA_HOST_PORT": 21012,
    "AGENT_POSTGRES_PORT": 15539,
    "AGENT_HTTP_PORT": 8092,
}
STAGES = [
    "preflight",
    "build-and-offline-dependencies",
    "demo-infrastructure",
    "Java",
    "Agent-PostgreSQL",
    "Tutor-Agent",
    "synthetic-course-and-index",
    "Tutor-create",
    "Tutor-complete",
    "Tutor-cancel",
    "Tutor-restart-recovery",
    "flashcards-full-flow",
    "cross-account",
    "ownership",
    "zero-external-model",
    "legacy-alone",
    "cleanup",
]
# Audit only the Agent interpreter, including threads. No replacement Java, providers or authority.
NETWORK_GUARD = """import ipaddress, os, sys

def guard(event, args):
    if event == "socket.connect":
        address = args[1]
        if not isinstance(address, tuple):
            return
        try:
            local = ipaddress.ip_address(address[0]).is_loopback
        except ValueError:
            local = address[0] == "localhost"
        if not local:
            with open(os.environ["SMOKE_DENIED_NETWORK_LOG"], "a") as log:
                log.write("DENIED_NON_LOOPBACK_CONNECT\\n")
            raise OSError("Smoke forbids non-loopback Agent connections")

sys.addaudithook(guard)
with open(os.environ["SMOKE_GUARD_ACTIVE_LOG"], "a") as log:
    log.write("ACTIVE\\n")
"""


class Smoke:
    def __init__(self, args):
        self.args = args
        self.out = args.output_dir.resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.out.chmod(0o700)
        self.start = time.monotonic()
        self.result = {
            "projects": [DEMO, AGENT],
            "stages": {},
            "cross_account": {},
            "not_run": [
                "Vue/Playwright FOLLOW_UP",
                "real-model task quality",
                "process-level database write attribution (heuristic + not proven)",
            ],
        }
        self.children = []
        self.owned = []
        self.private = []
        self.token = ""
        # Do not inherit provider credentials, proxies, JAVA_TOOL_OPTIONS, or application config.
        self.env = {
            k: os.environ[k]
            for k in (
                "PATH",
                "HOME",
                "USER",
                "LANG",
                "JAVA_HOME",
                "UV_CACHE_DIR",
                "UV_PYTHON_INSTALL_DIR",
            )
            if k in os.environ
        }
        self.env.update(
            HF_HUB_OFFLINE="1",
            HF_HUB_DISABLE_IMPLICIT_TOKEN="1",
            HF_HUB_DISABLE_TELEMETRY="1",
            DO_NOT_TRACK="1",
        )
        self.http = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def redact(self, text):
        for value in self.private:
            text = text.replace(value, "[REDACTED]")
        return re.sub(
            r"\beyJ[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+",
            "[JWT REDACTED]",
            text,
        )

    def save(self):
        self.result["elapsed_seconds"] = round(time.monotonic() - self.start, 2)
        (self.out / "result.json").write_text(json.dumps(self.result, indent=2) + "\n")

    @contextmanager
    def stage(self, name):
        started = time.monotonic()
        self.result["stages"][name] = {"status": "RUNNING"}
        print(f"START {name}", flush=True)
        try:
            yield
        except BaseException as error:
            self.result["stages"][name] = {
                "status": "FAIL",
                "seconds": round(time.monotonic() - started, 2),
                "error": self.redact(str(error)),
            }
            print(f"FAIL {name}: {self.redact(str(error))}; logs={self.out}", flush=True)
            raise
        else:
            elapsed = round(time.monotonic() - started, 2)
            self.result["stages"][name] = {"status": "PASS", "seconds": elapsed}
            print(f"PASS {name} ({elapsed}s)", flush=True)
        finally:
            self.save()

    def spawn(self, command, name, cwd=ROOT, env=None):
        log = (self.out / f"{name}.log").open("a")
        process = subprocess.Popen(
            command,
            cwd=cwd,
            env=env or self.env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            start_new_session=True,
        )

        def drain():
            try:
                for line in process.stdout:
                    log.write(self.redact(line))
                    log.flush()
            finally:
                process.stdout.close()
                log.close()

        thread = threading.Thread(target=drain, daemon=True)
        thread.start()
        self.children.append((process, thread))
        return process

    def stop(self, process, kill=False):
        if process.poll() is None:
            os.killpg(process.pid, signal.SIGKILL if kill else signal.SIGTERM)
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait(timeout=5)
        for child, thread in self.children:
            if child is process:
                thread.join(timeout=5)

    def run(self, command, name, timeout=120, cwd=ROOT):
        process = self.spawn(command, name, cwd)
        try:
            code = process.wait(timeout=timeout)
        except BaseException:
            self.stop(process, kill=True)
            raise
        self.stop(process)
        assert code == 0, f"{name} exited {code}; inspect {name}.log"

    def capture(self, command):
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env=self.env,
            text=True,
            capture_output=True,
            timeout=30,
            check=False,
        )
        assert completed.returncode == 0, "Inspection command failed (output withheld to protect credentials)"
        return completed.stdout.strip()

    def compose(self, project, *arguments):
        compose_file = ROOT / ("compose.agent.yml" if project == AGENT else "compose.yaml")
        files = ["-f", str(compose_file)]
        if project == DEMO:
            files += ["-f", str(self.out / "loopback.compose.yaml")]
        else:
            files += ["-f", str(self.out / "postgres.compose.yaml")]
        return [
            "docker",
            "compose",
            *files,
            "-p",
            project,
            "--env-file",
            str(self.out / "public.env"),
            *arguments,
        ]

    def sql(self, query, pg=False):
        if pg:
            cmd = self.compose(
                AGENT,
                "exec",
                "-T",
                "postgres",
                "psql",
                "-U",
                "lecturelens",
                "-d",
                "lecturelens_agent",
                "-At",
                "-c",
                query,
            )
        else:
            cmd = self.compose(
                DEMO,
                "exec",
                "-T",
                "mysql",
                "sh",
                "-c",
                'MYSQL_PWD="$MYSQL_PASSWORD" mysql --batch --skip-column-names '
                '-u"$MYSQL_USER" "$MYSQL_DATABASE" -e "$1"',
                "smoke-sql",
                query,
            )
        return self.capture(cmd)

    @staticmethod
    def free_port(port):
        with socket.socket() as sock:
            # Match uvicorn rebind semantics after SIGKILL (accepted sockets can be TIME_WAIT).
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            sock.bind(("127.0.0.1", port))
            return sock.getsockname()[1]

    def preflight(self):
        self.result["head"] = self.capture(["git", "rev-parse", "HEAD"])
        self.result["harness_sha256"] = hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
        for project in (DEMO, AGENT):
            for resource in ("container", "volume", "network"):
                found = self.capture(
                    [
                        "docker",
                        resource,
                        "ls",
                        "-q",
                        "--filter",
                        f"label=com.docker.compose.project={project}",
                    ]
                )
                assert not found, f"Refuse existing {resource} in {project}"
        ports = {}
        for key, requested in PORTS.items():
            try:
                port = self.free_port(requested)
            except OSError:
                port = self.free_port(0)
            while port in ports.values():
                port = self.free_port(0)
            ports[key] = port
        self.result["ports"] = ports
        public = {}
        for line in (ROOT / ".env.demo.example").read_text().splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                public[key] = value
        public.update({k: str(v) for k, v in ports.items()})
        # Proxy port is also used inside the container; override published ports instead
        # of embedding an IP in a variable reused as the container target port.
        mappings = {
            "mysql": [("MYSQL_HOST_PORT", 3306)],
            "redis": [("REDIS_HOST_PORT", 6379)],
            "minio": [("MINIO_API_HOST_PORT", 9000), ("MINIO_CONSOLE_HOST_PORT", 9001)],
            "rocketmq-namesrv": [("ROCKETMQ_NAMESRV_HOST_PORT", 9876)],
            "rocketmq-broker": [
                ("ROCKETMQ_BROKER_FAST_HOST_PORT", 10909),
                ("ROCKETMQ_BROKER_MAIN_HOST_PORT", 10911),
                ("ROCKETMQ_BROKER_HA_HOST_PORT", 10912),
                ("ROCKETMQ_PROXY_HOST_PORT", ports["ROCKETMQ_PROXY_HOST_PORT"]),
            ],
        }
        override = "services:\n"
        for service, bindings in mappings.items():
            override += f"  {service}:\n    ports: !override\n"
            for key, target in bindings:
                override += f'      - "127.0.0.1:{ports[key]}:{target}"\n'
        (self.out / "loopback.compose.yaml").write_text(override)
        java = f"http://127.0.0.1:{ports['APP_PORT']}"
        agent = f"http://127.0.0.1:{ports['AGENT_HTTP_PORT']}"
        public.update(
            LECTURELENS_DEMO_INSTANCE="pr49smoke",
            SERVER_ADDRESS="127.0.0.1",
            COURSE_LINGO_BASE_URL=java,
            MYSQL_PORT=str(ports["MYSQL_HOST_PORT"]),
            MYSQL_JDBC_URL=f"jdbc:mysql://127.0.0.1:{ports['MYSQL_HOST_PORT']}/courselingo?"
            "useUnicode=true&characterEncoding=utf8&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC",
            REDIS_HOST="127.0.0.1",
            REDIS_PORT=str(ports["REDIS_HOST_PORT"]),
            MINIO_ENDPOINT=f"http://127.0.0.1:{ports['MINIO_API_HOST_PORT']}",
            STORAGE_MINIO_ENDPOINT=f"http://127.0.0.1:{ports['MINIO_API_HOST_PORT']}",
            ROCKETMQ_NAME_SERVER=f"127.0.0.1:{ports['ROCKETMQ_NAMESRV_HOST_PORT']}",
            ROCKETMQ_ENDPOINT=f"127.0.0.1:{ports['ROCKETMQ_PROXY_HOST_PORT']}",
            ROCKETMQ_SEND_TIMEOUT_MS="10000",
            AGENT_SERVICE_URL=agent,
            AGENT_JAVA_BASE_URL=java,
            STUDY_AGENT_ENABLED=str(not self.args.legacy_only).lower(),
            DENSE_RETRIEVAL_ENABLED=str(not self.args.legacy_only).lower(),
            TUTOR_ENABLED="true",
            AGENT_LLM_MODE="mock",
            AGENT_CACHE_DIR=str(self.out / "agent-cache"),
            AGENT_DATABASE_URL=f"postgresql://lecturelens:lecturelens-local-only@127.0.0.1:"
            f"{ports['AGENT_POSTGRES_PORT']}/lecturelens_agent",
        )
        # Replace example passwords in memory, never put secrets in env files or command arguments.
        pg_password = secrets.token_hex(32)
        self.private.append(pg_password)
        self.env["SMOKE_POSTGRES_PASSWORD"] = pg_password
        (self.out / "postgres.compose.yaml").write_text(
            "services:\n  postgres:\n    environment:\n"
            '      POSTGRES_PASSWORD: "${SMOKE_POSTGRES_PASSWORD:?required}"\n'
        )
        dsn = public.pop("AGENT_DATABASE_URL").replace("lecturelens-local-only", pg_password)
        sensitive = [
            k for k in public if any(part in k for part in ("PASSWORD", "SECRET", "ACCESS_KEY", "API_KEY"))
        ]
        for key in sensitive:
            public.pop(key)
        (self.out / "public.env").write_text("".join(f"{k}={v}\n" for k, v in public.items()))
        self.env.update(public)
        self.env["AGENT_DATABASE_URL"] = dsn
        for key in sensitive + ["AGENT_SERVICE_SECRET"]:
            value = secrets.token_hex(32) if not key.endswith("API_KEY") else ""
            self.env[key] = value
            if value:
                self.private.append(value)
        self.env["STORAGE_MINIO_ACCESS_KEY"] = self.env["MINIO_ROOT_USER"]
        self.env["STORAGE_MINIO_SECRET_KEY"] = self.env["MINIO_ROOT_PASSWORD"]
        # Fail before starting any service if the public demo template ever enables a real provider.
        for key in ("MOCK_ASR_ENABLED", "DEMO_MOCK_LLM_ENABLED"):
            assert self.env[key] == "true", f"{key} must be true"
        for key in (
            "SILICONFLOW_ASR_ENABLED",
            "OPENAI_COMPATIBLE_ENABLED",
            "LANGCHAIN4J_OPENAI_ENABLED",
            "COURSELINGO_VISION_ANALYSIS_ENABLED",
        ):
            assert self.env[key] == "false", f"{key} must be false"
        self.env["AGENT_FEEDBACK_ENABLED"] = "false"
        self.env["HF_HOME"] = str(self.out / "hf-home")
        self.env["TMPDIR"] = str(self.out / "tmp")
        (self.out / "tmp").mkdir()
        guard = self.out / "network-guard"
        guard.mkdir()
        (guard / "sitecustomize.py").write_text(NETWORK_GUARD)
        self.env["PYTHONPATH"] = str(guard)
        self.env["SMOKE_DENIED_NETWORK_LOG"] = str(self.out / "denied-network.log")
        self.env["SMOKE_GUARD_ACTIVE_LOG"] = str(self.out / "guard-active.log")
        self.base = java
        self.agent_base = agent
        self.jar = ROOT / "backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar"
        print("PORTS " + json.dumps(ports, sort_keys=True), flush=True)

    def wait(self, action, predicate, seconds, description):
        deadline = time.monotonic() + seconds
        while True:
            value = action()
            if predicate(value):
                return value
            assert time.monotonic() < deadline, f"Timeout: {description}"
            time.sleep(0.3)

    def health(self, process, base, path):
        def probe():
            assert process.poll() is None, f"Child exited before {path}; inspect service logs"
            try:
                with self.http.open(base + path, timeout=2) as response:
                    return response.status == 200
            except (OSError, urllib.error.URLError):
                return False

        self.wait(probe, bool, 150, path)

    def api(self, method, path, body=None, expected=200, content_type="application/json"):
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": content_type}
        if self.token:
            headers["Authorization"] = "Bearer " + self.token
        request = urllib.request.Request(self.base + path, data=data, headers=headers, method=method)
        try:
            response = self.http.open(request, timeout=45)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            raw = response.read()
            try:
                payload = json.loads(raw)
            except ValueError:
                raise AssertionError(f"{method} {path}: non-JSON HTTP {response.status}") from None
            if expected != 200:
                label = body.get("operation", method) if isinstance(body, dict) else method
                self.result["cross_account"][f"{label} {path}"] = response.status
                self.save()
            assert response.status == expected, (
                f"{method} {path}: HTTP {response.status}, expected {expected}, code={payload.get('code')}"
            )
            if expected == 200:
                assert str(payload["code"]) == "0", f"{method} {path}: code={payload.get('code')}"
            return payload.get("data")

    def login(self):
        credentials = {
            "email": f"smoke-{secrets.token_hex(8)}@example.com",
            "password": secrets.token_hex(16) + "A1",
        }
        self.private.append(credentials["password"])
        self.api("POST", "/api/auth/register", credentials)
        self.token = self.api("POST", "/api/auth/login", credentials)["accessToken"]
        self.private.append(self.token)

    def dependencies(self):
        if not self.jar.exists():
            self.run(
                ["bash", "mvnw", "-o", "-DskipTests", "package"],
                "build",
                180,
                ROOT / "backend",
            )
        if not self.args.legacy_only:
            assert self.args.embedding_cache_source, (
                "--embedding-cache-source required; see sibling documentation"
            )
            shutil.copytree(self.args.embedding_cache_source, self.out / "agent-cache/models")
            self.run(
                ["uv", "sync", "--offline", "--frozen"],
                "uv-sync",
                90,
                ROOT / "agent-service",
            )

    def infrastructure(self):
        # Recheck immediately before bind; refuse a race instead of connecting to another service.
        for key, port in self.result["ports"].items():
            if key.endswith("_HOST_PORT"):
                self.free_port(port)
        self.capture(self.compose(DEMO, "config", "--quiet"))
        self.owned.append(DEMO)
        self.run(self.compose(DEMO, "up", "-d"), "demo-up", 180)
        for service in (
            "mysql",
            "redis",
            "minio",
            "minio-init",
            "rocketmq-store-init",
            "rocketmq-namesrv",
            "rocketmq-broker",
        ):

            def state(service=service):
                container = self.capture(self.compose(DEMO, "ps", "-aq", service))
                assert container, f"Missing isolated container: {service}"
                return self.capture(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{.State.Status}}:{{.State.ExitCode}}:{{if .State.Health}}{{.State.Health.Status}}{{end}}",
                        container,
                    ]
                )

            if service.endswith("-init"):
                predicate = lambda value: value.startswith("exited:0:")
            elif service in ("mysql", "redis", "minio"):
                predicate = lambda value: value.endswith(":healthy")
            else:
                predicate = lambda value: value.startswith("running:")
            self.wait(state, predicate, 120, f"{service} readiness")
        command = self.compose(
            DEMO,
            "exec",
            "-T",
            "rocketmq-broker",
            "sh",
            "-lc",
            "/home/rocketmq/rocketmq-5.3.4/bin/mqadmin updateTopic -n rocketmq-namesrv:9876 "
            "-b 127.0.0.1:10911 -t courselingo-analysis-task 2>/dev/null",
        )
        self.run(
            command[:-1]
            + [
                "for attempt in $(seq 1 35); do "
                + command[-1]
                + ' | grep -Fq "create topic to 127.0.0.1:10911 success." && exit 0; sleep 2; done; exit 1'
            ],
            "mq-topic",
            100,
        )
        libs = self.out / "mq-libs"
        libs.mkdir()
        with zipfile.ZipFile(self.jar) as archive:
            for entry in archive.infolist():
                if entry.filename.startswith("BOOT-INF/lib/") and entry.filename.endswith(".jar"):
                    (libs / Path(entry.filename).name).write_bytes(archive.read(entry))
        self.run(
            [
                "java",
                "--class-path",
                str(libs / "*"),
                str(ROOT / "scripts/ci/RocketMqReadiness.java"),
                self.env["ROCKETMQ_ENDPOINT"],
                self.env["ROCKETMQ_ANALYSIS_TOPIC"],
                "false",
                "10000",
            ],
            "mq-readiness",
            120,
        )

    def java(self):
        self.free_port(self.result["ports"]["APP_PORT"])
        process = self.spawn(
            ["java", f"-Djava.io.tmpdir={self.out / 'tmp'}", "-jar", str(self.jar)],
            "java",
            ROOT / "backend",
        )
        self.health(process, self.base, "/actuator/health")
        assert self.sql("SELECT COUNT(*) FROM flyway_schema_history WHERE success=0") == "0"

    def start_agent(self):
        self.free_port(self.result["ports"]["AGENT_HTTP_PORT"])
        process = self.spawn(
            [
                "uv",
                "run",
                "--offline",
                "--no-sync",
                "uvicorn",
                "lecturelens_real_eval.tutor.app:create_app",
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

    def course(self):
        self.run(
            ["bash", str(ROOT / "scripts/demo/generate-sample-video.sh")],
            "sample-video",
            30,
        )
        video = (ROOT / ".demo/lecturelens-sample.mp4").read_bytes()
        self.login()
        self.owner_token = self.token
        upload = self.api(
            "POST",
            "/api/uploads/sessions",
            {
                "filename": "synthetic.mp4",
                "sizeBytes": len(video),
                "chunkSizeBytes": len(video),
                "totalChunks": 1,
                "fileMd5": hashlib.md5(video).hexdigest(),
            },
        )["uploadId"]
        boundary = "smoke-" + secrets.token_hex(16)
        body = (
            (
                f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.bin"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n"
            ).encode()
            + video
            + f"\r\n--{boundary}--\r\n".encode()
        )
        self.api(
            "POST",
            f"/api/uploads/sessions/{upload}/chunks/0",
            body,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        self.api("POST", f"/api/uploads/sessions/{upload}/complete")
        self.task = self.api(
            "POST",
            "/api/tasks",
            {"uploadId": upload, "sourceLanguage": "en", "targetLanguage": "zh-CN"},
        )["taskId"]
        assert re.fullmatch(r"task_[a-f0-9]{32}", self.task)
        self.result["task_id"] = self.task

        def state():
            result = self.api("GET", f"/api/tasks/{self.task}")
            assert result["status"] not in ("FAILED", "CANCELED"), (
                f"Pipeline failed: {result.get('errorCode')}"
            )
            return result

        self.wait(state, lambda r: r["status"] == "SUCCEEDED", 180, "media preparation")
        self.api("POST", f"/api/tasks/{self.task}/chapters/generate")
        self.wait(
            lambda: self.api("GET", f"/api/tasks/{self.task}/evidence/index-status"),
            lambda r: r["status"] == "READY",
            120,
            "real dense index",
        )
        evidence = self.api("GET", f"/api/tasks/{self.task}/evidence")
        self.canonical = {item["evidenceId"]: item for item in evidence["items"]}
        assert self.canonical, "Synthetic evidence missing"
        self.tutor = f"/api/tasks/{self.task}/tutor/sessions"
        self.study = f"/api/tasks/{self.task}/study/command"
        self.owner = self.sql(f"SELECT user_id FROM analysis_task WHERE id='{self.task}'")
        assert self.owner.isdigit()

    def ask(self, key):
        return self.api(
            "POST",
            self.session_path + "/turns",
            {
                "client_turn_id": key,
                "text": "Explain the asynchronous course video learning pipeline.",
                "socratic": False,
            },
        )

    def turn(self, key, status):
        def read():
            turns = self.api("GET", self.session_path)["turns"]
            value = next(t for t in turns if t["client_turn_id"] == key)
            assert value["status"] not in {"failed", "cancelled", "completed"} - {status}, (
                f"Tutor {key}: status={value['status']} error={value.get('error_code')}"
            )
            return value

        return self.wait(read, lambda t: t["status"] == status, 30, f"Tutor {key} {status}")

    def answer(self, turn):
        assert turn["answer"] and turn["status"] == "completed"
        if turn["outcome"] == "insufficient_evidence":
            assert (
                turn["answer"]
                == "I don't know from this course. Try asking about a topic covered in this lecture."
            )
            assert turn["citations"] == [] and not turn["evaluation"]
        else:
            assert turn["outcome"] == "answered" and turn["citations"], "Supported answer requires citations"
            for citation in turn["citations"]:
                source = self.canonical[citation["evidence_id"]]
                assert f"[{citation['evidence_id']}]" in turn["answer"]
                assert citation["text"] == source["normalizedText"][:1200]
        self.result.setdefault("tutor_outcomes", []).append(turn["outcome"])

    def study_command(self, operation, **body):
        return self.api("POST", self.study, {"operation": operation, **body})

    def flashcards(self):
        self.study_session = self.study_command("CREATE_SESSION", request_key="study-create")["session_id"]
        generated = self.study_command(
            "GENERATE_CARDS",
            session_id=self.study_session,
            request_key="cards-generate",
        )
        self.run_id = generated["run"]["run_id"]

        def read():
            run = self.study_command("READ", session_id=self.study_session, run_id=self.run_id)["run"]
            assert run["status"] not in ("failed", "cancelled", "budget_exceeded"), (
                f"Flashcards status={run['status']} error={run.get('error_code')}"
            )
            return run

        self.wait(read, lambda r: r["status"] == "succeeded", 100, "flashcard Run succeeded")
        before = self.study_command("DUE_CARDS")
        assert before["due_count"] >= 1 and before["cards"]
        self.card_id = before["cards"][0]["card_id"]
        card = self.study_command("READ_CARD", card_id=self.card_id)["card"]
        assert card["front"] and card["back"] and card["citations"]
        for citation in card["citations"]:
            assert citation["evidence_id"] in self.canonical
        review = self.study_command(
            "REVIEW_CARD",
            card_id=self.card_id,
            request_key="review-good",
            expected_version=card["version"],
            rating="Good",
        )
        assert not review["replayed"] and review["review"]["rating"] == "Good"
        after = self.study_command("DUE_CARDS")
        updated = self.study_command("READ_CARD", card_id=self.card_id)["card"]
        assert updated["version"] == card["version"] + 1 and updated["due_at"] > card["due_at"]
        assert updated["schedule"] != card["schedule"]
        assert after["due_count"] == before["due_count"] - 1
        assert all(c["card_id"] != self.card_id for c in after["cards"])
        assert after["reviewed_today"] == before["reviewed_today"] + 1 and after["next_due_at"]
        self.result["flashcards"] = {
            "due_before": before["due_count"],
            "due_after": after["due_count"],
            "version_before": card["version"],
            "version_after": updated["version"],
            "due_at_before": card["due_at"],
            "due_at_after": updated["due_at"],
        }

    def cross_account(self):
        self.token = ""
        self.login()
        cases = [
            ("POST", self.tutor, {"request_key": "stranger-create"}),
            ("GET", self.tutor, None),
            ("GET", self.session_path, None),
            (
                "POST",
                self.session_path + "/turns",
                {
                    "client_turn_id": "stranger-turn",
                    "text": "pipeline",
                    "socratic": False,
                },
            ),
            ("POST", self.session_path + "/turns/first/cancel", None),
        ]
        cases += [
            ("POST", self.study, payload)
            for payload in [
                {"operation": "DUE_CARDS"},
                {"operation": "READ_CARD", "card_id": self.card_id},
                {
                    "operation": "GENERATE_CARDS",
                    "session_id": self.study_session,
                    "request_key": "stranger-generate",
                },
            ]
        ]
        try:
            for method, path, body in cases:
                # Baseline Java TASK_NOT_FOUND is HTTP 404. Never accept an arbitrary error as denial.
                self.api(method, path, body, expected=404)
                label = (body or {}).get("operation", method)
                self.result["cross_account"][f"{label} {path}"] = 404
                print(f"HTTP cross-account {label} {path} = 404", flush=True)
        finally:
            self.token = self.owner_token

    def ownership(self):
        tables = self.sql("SHOW TABLES").splitlines()
        forbidden = [t for t in tables if re.match(r"^(tutor|study|agent_model|checkpoint)(_|$)", t)]
        assert not forbidden, f"Agent tables in MySQL: {forbidden}"
        counts = {}
        for table in ("tutor_session", "study_session"):
            assert (
                self.sql(
                    f"SELECT count(*) FROM {table} WHERE owner_id<>{self.owner} OR course_id<>'{self.task}'",
                    pg=True,
                )
                == "0"
            )
            counts[table] = int(self.sql(f"SELECT count(*) FROM {table}", pg=True))
            assert counts[table] == 1
        counts["tutor_turn"] = int(
            self.sql(
                "SELECT count(*) FROM tutor_turn t JOIN tutor_session s USING(session_id) "
                f"WHERE s.owner_id={self.owner} AND s.course_id='{self.task}'",
                pg=True,
            )
        )
        assert counts["tutor_turn"] == 3
        assert (
            self.sql(
                "SELECT string_agg(status,',' ORDER BY ordinal) FROM tutor_turn",
                pg=True,
            )
            == "completed,cancelled,completed"
        )
        for table, join in [
            ("study_run", "JOIN study_session s USING(session_id)"),
            (
                "study_deck",
                "JOIN study_run r USING(run_id) JOIN study_session s USING(session_id)",
            ),
            (
                "study_card",
                "JOIN study_deck d USING(deck_id) JOIN study_run r USING(run_id) JOIN study_session s USING(session_id)",
            ),
            (
                "study_review_log",
                (
                    "JOIN study_card c USING(card_id) JOIN study_deck d USING(deck_id) "
                    "JOIN study_run r USING(run_id) JOIN study_session s USING(session_id)"
                ),
            ),
        ]:
            counts[table] = int(
                self.sql(
                    f"SELECT count(*) FROM {table} x {join} "
                    f"WHERE s.owner_id={self.owner} AND s.course_id='{self.task}'",
                    pg=True,
                )
            )
            assert counts[table] >= 1
            assert counts[table] == int(self.sql(f"SELECT count(*) FROM {table}", pg=True))
        self.result["ownership"] = {
            "rows": counts,
            "mysql_agent_tables": forbidden,
            "depth": "schema + owner/course joins + gateway denials; heuristic + not proven process-level writes",
        }

    def zero_models(self):
        assert self.env["AGENT_LLM_MODE"] == "mock"
        for key in ("MOCK_ASR_ENABLED", "DEMO_MOCK_LLM_ENABLED"):
            assert self.env[key] == "true"
        for key in (
            "SILICONFLOW_ASR_ENABLED",
            "OPENAI_COMPATIBLE_ENABLED",
            "LANGCHAIN4J_OPENAI_ENABLED",
            "COURSELINGO_VISION_ANALYSIS_ENABLED",
        ):
            assert self.env[key] == "false"
        assert (
            self.sql(
                "SELECT count(*) FROM study_run WHERE model_mode<>'mock' OR model_config IS NOT NULL",
                pg=True,
            )
            == "0"
        )
        assert self.sql("SELECT count(*) FROM agent_model_connection", pg=True) == "0"
        assert len((self.out / "guard-active.log").read_text().splitlines()) >= 2, (
            "Agent network guard not active across restart"
        )
        assert not (self.out / "denied-network.log").exists(), "Agent attempted a non-loopback connection"
        self.result["external_models"] = {
            "calls": 0,
            "evidence": "mock-only factories, disabled Java real providers, "
            "no inherited API keys, offline weights, Agent socket audit guard, PG mock mode/no model connections",
            "limit": "Java egress is configuration-based; no OS-level packet attribution",
        }

    def cleanup(self):
        signal.alarm(0)
        failures = []
        for process, _ in reversed(self.children):
            try:
                self.stop(process)
            except Exception as error:  # noqa: BLE001 -- teardown must still visit the other owned project
                failures.append(type(error).__name__)
        for project in reversed(self.owned):
            try:
                self.run(
                    self.compose(project, "logs", "--no-color"),
                    f"{project}-services",
                    20,
                )
                self.run(
                    self.compose(project, "down", "-v", "--remove-orphans", "--timeout", "5"),
                    f"{project}-down",
                    45,
                )
            except Exception as error:  # noqa: BLE001 -- teardown must still visit the other owned project
                failures.append(type(error).__name__)
        lines = []
        for project in (DEMO, AGENT):
            lines.append(
                project
                + ": "
                + self.capture(
                    [
                        "docker",
                        "ps",
                        "-a",
                        "--filter",
                        f"label=com.docker.compose.project={project}",
                        "--format",
                        "{{.Names}} {{.Status}} {{.Ports}}",
                    ]
                )
            )
        (self.out / "docker-end.txt").write_text("\n".join(lines) + "\n")
        assert not failures, f"Cleanup errors: {failures}"
        if self.owned:
            for project in self.owned:
                assert (
                    self.capture(
                        [
                            "docker",
                            "container",
                            "ls",
                            "-aq",
                            "--filter",
                            f"label=com.docker.compose.project={project}",
                        ]
                    )
                    == ""
                ), f"{project} remains"

    def execute(self):
        def timeout_handler(_signum, _frame):
            raise TimeoutError("Smoke exceeded 720-second execution budget; cleanup follows")

        signal.signal(signal.SIGALRM, timeout_handler)
        signal.signal(signal.SIGTERM, lambda *_: timeout_handler(None, None))
        signal.alarm(720)
        success = False
        try:
            with self.stage("preflight"):
                self.preflight()
            with self.stage("build-and-offline-dependencies"):
                self.dependencies()
            with self.stage("demo-infrastructure"):
                self.infrastructure()
            if self.args.legacy_only:
                with self.stage("legacy-alone"):
                    self.run(
                        [
                            sys.executable,
                            str(ROOT / "scripts/ci/mock-e2e.py"),
                            "--env-file",
                            str(self.out / "public.env"),
                            "--project",
                            DEMO,
                        ],
                        "legacy",
                        450,
                    )
            else:
                with self.stage("Java"):
                    self.java()
                with self.stage("Agent-PostgreSQL"):
                    self.free_port(self.result["ports"]["AGENT_POSTGRES_PORT"])
                    self.owned.append(AGENT)
                    self.run(
                        self.compose(AGENT, "up", "-d", "--wait", "--wait-timeout", "90"),
                        "pg-up",
                        100,
                    )
                with self.stage("Tutor-Agent"):
                    agent = self.start_agent()
                with self.stage("synthetic-course-and-index"):
                    self.course()
                with self.stage("Tutor-create"):
                    session = self.api("POST", self.tutor, {"request_key": "tutor-create"})["session"]
                    self.session_path = self.tutor + "/" + session["session_id"]
                    assert self.api("GET", self.tutor)["sessions"][0]["session_id"] == session["session_id"]
                with self.stage("Tutor-complete"):
                    self.ask("first")
                    self.answer(self.turn("first", "completed"))
                with self.stage("Tutor-cancel"):
                    self.ask("cancel-now")
                    self.api("POST", self.session_path + "/turns/cancel-now/cancel")
                    self.turn("cancel-now", "cancelled")
                with self.stage("Tutor-restart-recovery"):
                    before = self.api("GET", self.session_path)["turns"]
                    self.stop(agent, kill=True)
                    agent = self.start_agent()
                    after = self.api("GET", self.session_path)["turns"]
                    assert after == before, "Persisted history changed across SIGKILL/restart"
                    self.ask("after-restart")
                    self.answer(self.turn("after-restart", "completed"))
                    assert len(self.api("GET", self.session_path)["turns"]) == 3
                    self.result["restart_recovery"] = (
                        "SIGKILL process group; identical two-turn history; new turn completed"
                    )
                with self.stage("flashcards-full-flow"):
                    self.flashcards()
                with self.stage("cross-account"):
                    self.cross_account()
                with self.stage("ownership"):
                    self.ownership()
                with self.stage("zero-external-model"):
                    self.zero_models()
            success = True
        except Exception as error:  # noqa: BLE001 -- retain a safe report and always tear down owned services
            self.result["failure"] = self.redact(str(error))
        finally:
            try:
                with self.stage("cleanup"):
                    self.cleanup()
            except Exception:  # noqa: BLE001 -- cleanup failure must override successful assertions
                success = False
            for name in STAGES:
                self.result["stages"].setdefault(name, {"status": "NOT_RUN"})
            self.result["success"] = success
            self.save()
            print(f"Result: {self.out / 'result.json'}", flush=True)
        return 0 if success else 1


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        required=True,
        type=Path,
        help="New private directory for retained redacted logs",
    )
    parser.add_argument(
        "--embedding-cache-source",
        type=Path,
        help="Public pinned HF cache copied into isolated cache",
    )
    parser.add_argument(
        "--legacy-only",
        action="store_true",
        help="Run original mock-e2e.py alone with fresh demo infra",
    )
    args = parser.parse_args()
    return Smoke(args).execute()


if __name__ == "__main__":
    sys.exit(main())
