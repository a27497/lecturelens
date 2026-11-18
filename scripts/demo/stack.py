#!/usr/bin/env python3
"""One-command local LectureLens stack: infrastructure, Java, Agent, Vue and a demo course.

Usage (from a clean clone):
    scripts/demo/up.sh              # Mock mode, no API key, no external model calls
    scripts/demo/up.sh --real       # your own OpenAI-compatible key (see README)
    scripts/demo/down.sh            # stop processes and containers, keep volumes
    scripts/demo/down.sh --purge    # also delete this instance's volumes and state

Ownership: only the Compose projects ``lecturelens-demo-<instance>`` and
``lecturelens-demoagent-<instance>`` and the processes recorded in
``.demo/stack-<instance>/state.json`` are started or stopped. Existing projects with
other names (for example a ``lecturelens-dev`` stack) are never touched. Requested ports
that are busy are replaced by free ones and printed. Every listener binds 127.0.0.1.

Generated local passwords live in ``.demo/stack-<instance>/secrets.json`` (mode 0600,
ignored by Git). A real-mode API key is read from the environment at start-up, passed only
to child processes and never written to disk or logs.
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
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIXTURE = ROOT / "fixtures/demo/binary-search-demo.mp4"
JAR = ROOT / "backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar"
EMBEDDING_REPO = "qdrant/paraphrase-multilingual-MiniLM-L12-v2-onnx-Q"
EMBEDDING_REVISION = "faf4aa4225822f3bc6376869cb1164e8e3feedd0"
DEMO_EMAIL = "demo@example.com"
# Defaults avoid the ports of the plain Quick Start demo and common local services.
DEFAULT_PORTS = {
    "WEB_PORT": 5180,
    "APP_PORT": 18280,
    "AGENT_HTTP_PORT": 18290,
    "MYSQL_HOST_PORT": 23506,
    "REDIS_HOST_PORT": 16579,
    "MINIO_API_HOST_PORT": 19200,
    "MINIO_CONSOLE_HOST_PORT": 19201,
    "ROCKETMQ_NAMESRV_HOST_PORT": 20076,
    "ROCKETMQ_PROXY_HOST_PORT": 18381,
    "ROCKETMQ_BROKER_FAST_HOST_PORT": 21109,
    "ROCKETMQ_BROKER_MAIN_HOST_PORT": 21111,
    "ROCKETMQ_BROKER_HA_HOST_PORT": 21112,
    "AGENT_POSTGRES_PORT": 15639,
}
# Real mode: these are read from the caller's environment; only the key is required.
REAL_DEFAULTS = {
    "LECTURELENS_LLM_BASE_URL": "https://api.deepseek.com",
    "LECTURELENS_LLM_MODEL": "deepseek-flash",
}
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def log(message):
    print(f"[demo] {message}", flush=True)


def fail(message):
    print(f"[demo] FAIL {message}", file=sys.stderr, flush=True)
    sys.exit(1)


class Stack:
    def __init__(self, instance):
        if not re.fullmatch(r"[a-z0-9-]{1,32}", instance):
            fail("instance must match [a-z0-9-]{1,32}")
        self.instance = instance
        self.infra_project = f"lecturelens-demo-{instance}"
        self.agent_project = f"lecturelens-demoagent-{instance}"
        self.dir = ROOT / ".demo" / f"stack-{instance}"
        self.state_file = self.dir / "state.json"
        self.secrets_file = self.dir / "secrets.json"
        self.state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}

    # ---------- helpers ----------
    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n")

    def compose(self, project, *args):
        if project == self.infra_project:
            files = [ROOT / "compose.yaml", ROOT / "compose.ci-minio.yml", self.dir / "infra.override.yaml"]
        else:
            files = [ROOT / "compose.agent.yml", self.dir / "agent.override.yaml"]
        command = ["docker", "compose", "-p", project, "--env-file", str(self.dir / "compose.env")]
        for path in files:
            command += ["-f", str(path)]
        return command + list(args)

    def run(self, command, *, cwd=ROOT, env=None, timeout=900, quiet=False, name=None):
        out = None
        if name:
            out = (self.dir / f"{name}.log").open("a")
        try:
            completed = subprocess.run(
                command,
                cwd=cwd,
                env=env,
                stdout=out if out else (subprocess.DEVNULL if quiet else None),
                stderr=subprocess.STDOUT if out else (subprocess.DEVNULL if quiet else None),
                timeout=timeout,
                check=False,
            )
        finally:
            if out:
                out.close()
        if completed.returncode != 0:
            where = f"; see {self.dir / (name + '.log')}" if name else ""
            fail(f"{command[0]} {' '.join(command[1:3])} exited {completed.returncode}{where}")

    def capture(self, command, env=None):
        return subprocess.run(command, cwd=ROOT, env=env, text=True, capture_output=True, check=False).stdout.strip()

    @staticmethod
    def port_free(port):
        with socket.socket() as sock:
            sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                sock.bind(("127.0.0.1", port))
            except OSError:
                return False
            return True

    @staticmethod
    def any_port():
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            return sock.getsockname()[1]

    def spawn(self, name, command, cwd, env):
        logfile = (self.dir / f"{name}.log").open("a")
        process = subprocess.Popen(
            command, cwd=cwd, env=env, stdout=logfile, stderr=subprocess.STDOUT, start_new_session=True
        )
        self.state.setdefault("pids", {})[name] = process.pid
        self.save()
        return process

    def wait_http(self, name, url, seconds, process=None):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if process is not None and process.poll() is not None:
                fail(f"{name} exited early; see {self.dir / (name + '.log')}")
            try:
                with HTTP.open(url, timeout=3) as response:
                    if response.status == 200:
                        return
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(1)
        fail(f"{name} not healthy at {url} within {seconds}s; see {self.dir / (name + '.log')}")

    # ---------- configuration ----------
    def prerequisites(self, real):
        missing = [tool for tool in ("docker", "java", "uv", "node", "npm", "ffmpeg", "ffprobe") if not shutil.which(tool)]
        if missing:
            fail("missing tools: " + ", ".join(missing) + " (see README: one-command demo)")
        version = self.capture(["docker", "compose", "version", "--short"])
        if not version:
            fail("docker compose v2 is required")
        java = subprocess.run(["java", "-version"], capture_output=True, text=True).stderr
        match = re.search(r'version "(\d+)', java)
        if not match or int(match.group(1)) < 21:
            fail("Java 21 is required")
        if real and not os.environ.get("LECTURELENS_LLM_API_KEY"):
            fail("--real needs LECTURELENS_LLM_API_KEY in the environment (see README: real-model mode)")
        for project in (self.infra_project, self.agent_project):
            if self.capture(["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}"]):
                fail(f"{project} is already running; run scripts/demo/down.sh first")
        for name, pid in self.state.get("pids", {}).items():
            if self.alive(pid):
                fail(f"recorded process {name} (pid {pid}) is still running; run scripts/demo/down.sh first")

    def choose_ports(self):
        ports, previous = {}, self.state.get("ports", {})
        for key, default in DEFAULT_PORTS.items():
            port = previous.get(key, default)
            if not self.port_free(port) or port in ports.values():
                replacement = self.any_port()
                while replacement in ports.values():
                    replacement = self.any_port()
                log(f"port {port} for {key} is busy; using {replacement}")
                port = replacement
            ports[key] = port
        self.state["ports"] = ports
        return ports

    def load_secrets(self):
        if self.secrets_file.exists():
            return json.loads(self.secrets_file.read_text())
        values = {key: secrets.token_hex(24) for key in (
            "MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "REDIS_PASSWORD", "MINIO_ROOT_PASSWORD",
            "JWT_ACCESS_SECRET", "AGENT_SERVICE_SECRET", "AGENT_POSTGRES_PASSWORD",
        )}
        values["MINIO_ROOT_USER"] = "demo-" + secrets.token_hex(6)
        values["DEMO_PASSWORD"] = "Demo-" + secrets.token_hex(6) + "a1"
        self.dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.secrets_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w") as handle:
            json.dump(values, handle, indent=2)
        return values

    def write_compose_files(self, ports, secret):
        public = {key: str(value) for key, value in ports.items()}
        (self.dir / "compose.env").write_text("".join(f"{k}={v}\n" for k, v in public.items()))
        loopback = {
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
        # Passwords reach Compose through the child environment (${VAR:?}), never through files.
        text = "services:\n"
        for service, bindings in loopback.items():
            text += f"  {service}:\n    ports: !override\n"
            for key, target in bindings:
                text += f'      - "127.0.0.1:{ports[key]}:{target}"\n'
            # RocketMQ images size their heap from host memory; the demo needs far less.
            if service == "rocketmq-namesrv":
                text += '    environment:\n      JAVA_OPT_EXT: "-Xms128m -Xmx256m -Xmn64m"\n'
            if service == "rocketmq-broker":
                text += (
                    "    environment:\n"
                    '      JAVA_OPT_EXT: "-Dcom.rocketmq.proxy.configPath=/tmp/rmq-proxy.json '
                    '-Xms512m -Xmx512m -Xmn256m -XX:MaxDirectMemorySize=256m"\n'
                )
        (self.dir / "infra.override.yaml").write_text(text)
        (self.dir / "agent.override.yaml").write_text(
            "services:\n  postgres:\n    environment:\n"
            '      POSTGRES_PASSWORD: "${AGENT_POSTGRES_PASSWORD:?required}"\n'
            "    ports: !override\n"
            f'      - "127.0.0.1:{ports["AGENT_POSTGRES_PORT"]}:5432"\n'
        )

    def base_env(self):
        keep = ("PATH", "HOME", "USER", "LANG", "LC_ALL", "JAVA_HOME", "UV_CACHE_DIR", "UV_PYTHON_INSTALL_DIR",
                "NPM_CONFIG_CACHE", "XDG_CACHE_HOME", "DOCKER_HOST", "DOCKER_CONFIG", "TMPDIR")
        return {key: os.environ[key] for key in keep if key in os.environ}

    def compose_env(self, secret):
        env = self.base_env()
        env.update({k: secret[k] for k in (
            "MYSQL_ROOT_PASSWORD", "MYSQL_PASSWORD", "REDIS_PASSWORD", "MINIO_ROOT_USER",
            "MINIO_ROOT_PASSWORD", "AGENT_POSTGRES_PASSWORD")})
        env["MYSQL_USERNAME"] = "courselingo"
        env["MYSQL_DATABASE"] = "courselingo"
        return env

    def java_env(self, ports, secret, real):
        env = self.base_env()
        for line in (ROOT / ".env.demo.example").read_text().splitlines():
            if line and not line.startswith("#"):
                key, value = line.split("=", 1)
                env[key] = value
        java = f"http://127.0.0.1:{ports['APP_PORT']}"
        env.update(
            APP_PORT=str(ports["APP_PORT"]),
            SERVER_ADDRESS="127.0.0.1",
            COURSE_LINGO_BASE_URL=java,
            MYSQL_PORT=str(ports["MYSQL_HOST_PORT"]),
            MYSQL_JDBC_URL=f"jdbc:mysql://127.0.0.1:{ports['MYSQL_HOST_PORT']}/courselingo?useUnicode=true"
            "&characterEncoding=utf8&useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC",
            MYSQL_ROOT_PASSWORD=secret["MYSQL_ROOT_PASSWORD"],
            MYSQL_PASSWORD=secret["MYSQL_PASSWORD"],
            REDIS_HOST="127.0.0.1",
            REDIS_PORT=str(ports["REDIS_HOST_PORT"]),
            REDIS_PASSWORD=secret["REDIS_PASSWORD"],
            MINIO_ROOT_USER=secret["MINIO_ROOT_USER"],
            MINIO_ROOT_PASSWORD=secret["MINIO_ROOT_PASSWORD"],
            STORAGE_MINIO_ACCESS_KEY=secret["MINIO_ROOT_USER"],
            STORAGE_MINIO_SECRET_KEY=secret["MINIO_ROOT_PASSWORD"],
            MINIO_ENDPOINT=f"http://127.0.0.1:{ports['MINIO_API_HOST_PORT']}",
            STORAGE_MINIO_ENDPOINT=f"http://127.0.0.1:{ports['MINIO_API_HOST_PORT']}",
            ROCKETMQ_NAME_SERVER=f"127.0.0.1:{ports['ROCKETMQ_NAMESRV_HOST_PORT']}",
            ROCKETMQ_ENDPOINT=f"127.0.0.1:{ports['ROCKETMQ_PROXY_HOST_PORT']}",
            ROCKETMQ_SEND_TIMEOUT_MS="10000",
            JWT_ACCESS_SECRET=secret["JWT_ACCESS_SECRET"],
            UPLOAD_CHUNK_STAGING_DIR=str(self.dir / "upload-chunks"),
            AGENT_SERVICE_URL=f"http://127.0.0.1:{ports['AGENT_HTTP_PORT']}",
            AGENT_SERVICE_SECRET=secret["AGENT_SERVICE_SECRET"],
            DENSE_RETRIEVAL_ENABLED="true",
            DENSE_RETRIEVAL_TIMEOUT="120s",
            STUDY_AGENT_ENABLED="true",
            COURSELINGO_ASR_TRANSCRIPT_STRATEGY="EMBEDDED_SUBTITLE_FIRST",
            # Fusion needs visual evidence; the synthetic slides add nothing for the demo.
            COURSELINGO_FUSION_VIDEO_SEGMENT_ENABLED="false",
            COURSELINGO_VISION_KEYFRAME_ENABLED="false",
        )
        if real:
            model = os.environ.get("LECTURELENS_LLM_MODEL", REAL_DEFAULTS["LECTURELENS_LLM_MODEL"])
            base = os.environ.get("LECTURELENS_LLM_BASE_URL", REAL_DEFAULTS["LECTURELENS_LLM_BASE_URL"]).rstrip("/")
            env.update(
                MOCK_ASR_ENABLED="false",
                DEMO_MOCK_LLM_ENABLED="false",
                # Java requires an ASR provider. The demo course has embedded subtitles, so ASR is
                # never called; the unreachable placeholder makes an accidental call fail closed.
                SILICONFLOW_ASR_ENABLED="true",
                SILICONFLOW_API_KEY="unused-placeholder",
                SILICONFLOW_ASR_BASE_URL="http://127.0.0.1:9",
                OPENAI_COMPATIBLE_ENABLED="true",
                OPENAI_COMPATIBLE_API_KEY=os.environ["LECTURELENS_LLM_API_KEY"],
                OPENAI_COMPATIBLE_BASE_URL=os.environ.get("LECTURELENS_JAVA_LLM_BASE_URL", base + "/v1"),
                OPENAI_COMPATIBLE_MODEL=model,
                OPENAI_COMPATIBLE_MAX_TOKENS="4096",
                COURSELINGO_AI_MODEL_TRANSLATION=model,
                COURSELINGO_AI_MODEL_LEARNING_PACKAGE=model,
                COURSELINGO_AI_MODEL_QA=model,
                COURSELINGO_AI_MODEL_CHAPTER=model,
                COURSELINGO_AI_MODEL_FUSION=model,
            )
        return env

    def agent_env(self, ports, secret, real):
        env = self.base_env()
        env.update(
            AGENT_SERVICE_SECRET=secret["AGENT_SERVICE_SECRET"],
            AGENT_DATABASE_URL=f"postgresql://lecturelens:{secret['AGENT_POSTGRES_PASSWORD']}@127.0.0.1:"
            f"{ports['AGENT_POSTGRES_PORT']}/lecturelens_agent",
            AGENT_CACHE_DIR=str(self.dir / "agent-cache"),
            AGENT_JAVA_BASE_URL=f"http://127.0.0.1:{ports['APP_PORT']}",
            AGENT_COURSE_TOOL_TRANSPORT="internal",
            STUDY_AGENT_ENABLED="true",
            STUDY_FEEDBACK_ENABLED="true",
            AGENT_RUN_DEADLINE_SECONDS="90",
            AGENT_RUN_CONCURRENCY="1",
            HF_HUB_OFFLINE="1",
            HF_HUB_DISABLE_TELEMETRY="1",
        )
        if real:
            env.update(
                AGENT_LLM_MODE="real",
                AGENT_LLM_BASE_URL=os.environ.get("LECTURELENS_LLM_BASE_URL", REAL_DEFAULTS["LECTURELENS_LLM_BASE_URL"]),
                AGENT_LLM_MODEL=os.environ.get("LECTURELENS_LLM_MODEL", REAL_DEFAULTS["LECTURELENS_LLM_MODEL"]),
                AGENT_LLM_API_KEY=os.environ["LECTURELENS_LLM_API_KEY"],
                TUTOR_ENABLED="false",
            )
        else:
            # The course Tutor panel is a mock-only experiment; it is enabled only in mock mode.
            env.update(AGENT_LLM_MODE="mock", TUTOR_ENABLED="true")
        return env

    # ---------- steps ----------
    def build(self):
        if not JAR.exists():
            log("building the Java backend (first run downloads Maven dependencies)")
            self.run(["bash", "mvnw", "-q", "-DskipTests", "package"], cwd=ROOT / "backend", name="build-java")
        log("syncing agent-service dependencies (uv.lock)")
        self.run(["uv", "sync", "--frozen"], cwd=ROOT / "agent-service", name="build-agent")
        if not (ROOT / "frontend/node_modules").exists():
            log("installing frontend dependencies (npm ci)")
            self.run(["npm", "ci", "--no-audit", "--no-fund"], cwd=ROOT / "frontend", name="build-frontend")
        if not (ROOT / "frontend/dist/index.html").exists():
            log("building the frontend")
            self.run(["npm", "run", "build"], cwd=ROOT / "frontend", name="build-frontend")
        cache = ROOT / ".demo/cache/embedding"
        marker = cache / f"{EMBEDDING_REVISION}.ok"
        if not marker.exists():
            log(f"downloading the public embedding model {EMBEDDING_REPO}@{EMBEDDING_REVISION[:8]}")
            script = (
                "import sys\nfrom huggingface_hub import snapshot_download\n"
                "snapshot_download(sys.argv[1], revision=sys.argv[2], cache_dir=sys.argv[3],"
                " allow_patterns=['*.json', 'model_optimized.onnx'], token=False)\n"
            )
            env = self.base_env()
            env.update(HF_HUB_DISABLE_IMPLICIT_TOKEN="1", HF_HUB_DISABLE_TELEMETRY="1")
            self.run([str(ROOT / "agent-service/.venv/bin/python"), "-c", script, EMBEDDING_REPO,
                      EMBEDDING_REVISION, str(cache)], env=env, name="build-embedding")
            marker.write_text("ok\n")
        models = self.dir / "agent-cache/models"
        if not models.exists():
            models.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache, models, ignore=shutil.ignore_patterns("*.ok"))

    def infrastructure(self, secret):
        env = self.compose_env(secret)
        log("starting MySQL, Redis, MinIO and RocketMQ (Compose project %s)" % self.infra_project)
        self.run(self.compose(self.infra_project, "up", "-d", "--wait", "--wait-timeout", "300",
                              "mysql", "redis", "minio"), env=env, name="infra", timeout=1800)
        self.run(self.compose(self.infra_project, "up", "-d", "minio-init", "rocketmq-store-init",
                              "rocketmq-namesrv", "rocketmq-broker"), env=env, name="infra", timeout=600)
        topic = (
            "for attempt in $(seq 1 40); do /home/rocketmq/rocketmq-5.3.4/bin/mqadmin updateTopic "
            "-n rocketmq-namesrv:9876 -b 127.0.0.1:10911 -t courselingo-analysis-task 2>/dev/null "
            '| grep -Fq "create topic to 127.0.0.1:10911 success." && exit 0; sleep 3; done; exit 1'
        )
        self.run(self.compose(self.infra_project, "exec", "-T", "rocketmq-broker", "sh", "-lc", topic),
                 env=env, name="infra", timeout=200)
        log("starting PostgreSQL/pgvector (Compose project %s)" % self.agent_project)
        self.run(self.compose(self.agent_project, "up", "-d", "--wait", "--wait-timeout", "120"),
                 env=env, name="infra", timeout=600)
        self.mq_ready(secret)

    def mq_ready(self, secret):
        # The proxy accepts gRPC a little after the topic exists; probe it like CI does.
        libs = self.dir / "mq-libs"
        if not libs.exists():
            libs.mkdir()
            with zipfile.ZipFile(JAR) as archive:
                for entry in archive.infolist():
                    if entry.filename.startswith("BOOT-INF/lib/") and entry.filename.endswith(".jar"):
                        (libs / Path(entry.filename).name).write_bytes(archive.read(entry))
        endpoint = f"127.0.0.1:{self.state['ports']['ROCKETMQ_PROXY_HOST_PORT']}"
        self.run(["java", "--class-path", str(libs / "*"), str(ROOT / "scripts/ci/RocketMqReadiness.java"),
                  endpoint, "courselingo-analysis-task", "false", "10000"], name="infra", timeout=180)

    def services(self, secret, real):
        ports = self.state["ports"]
        java = self.spawn("java", ["java", "-Xms256m", "-Xmx1024m", f"-Djava.io.tmpdir={self.dir / 'tmp'}",
                                   "-jar", str(JAR)], ROOT / "backend", self.java_env(ports, secret, real))
        (self.dir / "tmp").mkdir(exist_ok=True)
        log("waiting for Java health")
        self.wait_http("java", f"http://127.0.0.1:{ports['APP_PORT']}/actuator/health", 240, java)
        factory = "lecturelens_agent.app:create_app" if real else "lecturelens_real_eval.tutor.app:create_app"
        agent = self.spawn("agent", [str(ROOT / "agent-service/.venv/bin/uvicorn"), factory, "--factory",
                                     "--host", "127.0.0.1", "--port", str(ports["AGENT_HTTP_PORT"])],
                           ROOT / "agent-service", self.agent_env(ports, secret, real))
        log("waiting for Agent health")
        self.wait_http("agent", f"http://127.0.0.1:{ports['AGENT_HTTP_PORT']}/healthz", 180, agent)
        web_env = self.base_env()
        web_env["VITE_BACKEND_PROXY_TARGET"] = f"http://127.0.0.1:{ports['APP_PORT']}"
        web = self.spawn("web", [str(ROOT / "frontend/node_modules/.bin/vite"), "preview", "--host", "127.0.0.1",
                                 "--port", str(ports["WEB_PORT"]), "--strictPort"], ROOT / "frontend", web_env)
        self.wait_http("web", f"http://127.0.0.1:{ports['WEB_PORT']}/", 60, web)

    def api(self, method, path, body=None, token=None, content_type="application/json"):
        base = f"http://127.0.0.1:{self.state['ports']['APP_PORT']}"
        data = body if isinstance(body, bytes) else json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": content_type}
        if token:
            headers["Authorization"] = "Bearer " + token
        request = urllib.request.Request(base + path, data=data, headers=headers, method=method)
        try:
            response = HTTP.open(request, timeout=60)
        except urllib.error.HTTPError as error:
            response = error
        with response:
            payload = json.loads(response.read() or b"{}")
        if response.status != 200 or str(payload.get("code")) != "0":
            raise RuntimeError(f"{method} {path}: HTTP {response.status} code={payload.get('code')}")
        return payload.get("data")

    def seed(self, secret):
        credentials = {"email": DEMO_EMAIL, "password": secret["DEMO_PASSWORD"]}
        try:
            self.api("POST", "/api/auth/register", credentials)
        except RuntimeError:
            pass  # already registered on a previous start of this instance
        token = self.api("POST", "/api/auth/login", credentials)["accessToken"]
        if self.state.get("task_id"):
            try:
                if self.api("GET", f"/api/tasks/{self.state['task_id']}", token=token)["status"] == "SUCCEEDED":
                    log("demo course already prepared")
                    return
            except RuntimeError:
                pass
        log("uploading the synthetic demo course and running the media pipeline")
        video = FIXTURE.read_bytes()
        upload = self.api("POST", "/api/uploads/sessions", {
            "filename": "binary-search-demo.mp4", "sizeBytes": len(video), "chunkSizeBytes": len(video),
            "totalChunks": 1, "fileMd5": hashlib.md5(video).hexdigest()}, token)["uploadId"]
        boundary = "demo-" + secrets.token_hex(12)
        body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="chunk.bin"\r\n'
                "Content-Type: application/octet-stream\r\n\r\n").encode() + video + f"\r\n--{boundary}--\r\n".encode()
        self.api("POST", f"/api/uploads/sessions/{upload}/chunks/0", body, token,
                 content_type=f"multipart/form-data; boundary={boundary}")
        self.api("POST", f"/api/uploads/sessions/{upload}/complete", token=token)
        task = self.api("POST", "/api/tasks", {"uploadId": upload, "sourceLanguage": "en",
                                               "targetLanguage": "zh-CN"}, token)["taskId"]
        self.state["task_id"] = task
        self.save()
        deadline = time.monotonic() + 600
        while True:
            status = self.api("GET", f"/api/tasks/{task}", token=token)
            if status["status"] == "SUCCEEDED":
                break
            if status["status"] in ("FAILED", "CANCELED") or time.monotonic() > deadline:
                fail(f"demo course status {status['status']} {status.get('errorCode')}; see {self.dir / 'java.log'}")
            time.sleep(2)
        try:
            self.api("POST", f"/api/tasks/{task}/chapters/generate", token=token)
        except RuntimeError as error:
            log(f"chapter generation skipped: {error}")
        deadline = time.monotonic() + 300
        while self.api("GET", f"/api/tasks/{task}/evidence/index-status", token=token)["status"] != "READY":
            if time.monotonic() > deadline:
                fail("Evidence index did not become READY; see agent.log")
            time.sleep(2)

    # ---------- commands ----------
    def up(self, real):
        started = time.monotonic()
        if not FIXTURE.exists():
            fail(f"missing {FIXTURE}")
        self.prerequisites(real)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dir.chmod(0o700)
        secret = self.load_secrets()
        ports = self.choose_ports()
        self.state.update(mode="real" if real else "mock", pids={})
        self.save()
        self.write_compose_files(ports, secret)
        self.build()
        self.infrastructure(secret)
        self.services(secret, real)
        self.seed(secret)
        self.state["ready_seconds"] = round(time.monotonic() - started, 1)
        self.save()
        url = f"http://127.0.0.1:{ports['WEB_PORT']}/tasks/{self.state['task_id']}"
        mode = ("REAL: model calls are billed to your key" if real
                else "MOCK: deterministic providers, no API key, no external model calls")
        print(f"""
LectureLens demo is ready in {self.state['ready_seconds']}s ({mode})
  Open:     {url}
  Email:    {DEMO_EMAIL}
  Password: {secret['DEMO_PASSWORD']}
  Logs:     {self.dir}
  Stop:     scripts/demo/down.sh{'' if self.instance == 'default' else ' --instance ' + self.instance}
""", flush=True)

    @staticmethod
    def alive(pid):
        try:
            os.kill(pid, 0)
        except (ProcessLookupError, PermissionError):
            return False
        return True

    def down(self, purge):
        for name, pid in reversed(list(self.state.get("pids", {}).items())):
            if not self.alive(pid):
                continue
            log(f"stopping {name} (pid {pid})")
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                continue
            for _ in range(30):
                if not self.alive(pid):
                    break
                time.sleep(0.5)
            else:
                os.killpg(pid, signal.SIGKILL)
        self.state["pids"] = {}
        if self.dir.exists():
            self.save()
        if (self.dir / "compose.env").exists():
            secret = self.load_secrets()
            env = self.compose_env(secret)
            extra = ["-v"] if purge else []
            for project in (self.agent_project, self.infra_project):
                log(f"removing containers of {project}{' and its volumes' if purge else ''}")
                self.run(self.compose(project, "down", "--remove-orphans", "--timeout", "10", *extra),
                         env=env, name="down", timeout=300)
        if purge and self.dir.exists():
            shutil.rmtree(self.dir)
        log("stopped")

    def status(self):
        print(json.dumps({k: v for k, v in self.state.items()}, indent=2, sort_keys=True))
        for name, pid in self.state.get("pids", {}).items():
            print(f"{name}: pid {pid} {'running' if self.alive(pid) else 'stopped'}")


def main():
    parser = argparse.ArgumentParser(description="LectureLens one-command demo stack")
    parser.add_argument("command", choices=["up", "down", "status"])
    parser.add_argument("--instance", default=os.environ.get("LECTURELENS_DEMO_INSTANCE", "default"))
    parser.add_argument("--real", action="store_true", help="use LECTURELENS_LLM_API_KEY instead of Mock providers")
    parser.add_argument("--purge", action="store_true", help="down: also delete volumes and generated state")
    args = parser.parse_args()
    stack = Stack(args.instance)
    if args.command == "up":
        try:
            stack.up(args.real)
        except KeyboardInterrupt:
            fail("interrupted; run scripts/demo/down.sh to clean up")
    elif args.command == "down":
        stack.down(args.purge)
    else:
        stack.status()


if __name__ == "__main__":
    main()
