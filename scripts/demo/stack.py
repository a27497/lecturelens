#!/usr/bin/env python3
"""One-command local LectureLens stack: infrastructure, Java, Agent, Vue and a demo course.

Usage (from a clean clone):
    scripts/demo/up.sh              # Mock mode, no API key, no external model calls
    scripts/demo/up.sh --real       # your own OpenAI-compatible key (see README)
    scripts/demo/down.sh            # stop processes and containers, keep volumes
    scripts/demo/down.sh --purge    # also delete this instance's volumes and state

Ownership: only the Compose projects ``lecturelens-demo-<instance>`` and
``lecturelens-demoagent-<instance>`` and the processes recorded in
``.demo/stack-<instance>/state.json`` are started or stopped. Every container and volume
created here carries this checkout's owner ID (``OWNER_LABEL``). Before ``up`` and ``down`` the
exact container and volume names Compose would use (and the project labels) are checked; if
anything there lacks this checkout's owner ID, both refuse, change nothing and exit non-zero.
Up/down of one instance name are serialized across clones by a lock in ``LOCK_DIR``.
Projects with other names (for example a ``lecturelens-dev`` stack) are never touched.
Requested ports that are busy are replaced by free ones and printed. Every listener binds 127.0.0.1.

Generated local passwords live in ``.demo/stack-<instance>/secrets.json`` (mode 0600,
ignored by Git). A real-mode API key is read from the environment at start-up, passed only
to child processes and never written to disk or logs in plain text. The Agent itself stores
an encrypted copy of the key in each real Study Run's frozen model configuration
(PostgreSQL); ``down --purge`` deletes that volume.
"""

import argparse
import fcntl
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
import urllib.parse
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
# Memory caps keep the whole demo near 3 GB, aimed at running next to a browser on an 8 GB laptop.
# Each container value is a hard cgroup cap (memswap equal, so it cannot spill into swap);
# sizes are the usage measured on the demo course plus headroom (eval/demo-stack/README.md).
# The RocketMQ images otherwise size their JVM heap from host memory.
CONTAINER_MEMORY = {
    "mysql": "640m",
    "redis": "64m",
    "minio": "384m",
    "minio-init": "64m",
    "rocketmq-namesrv": "384m",
    "rocketmq-store-init": "64m",
    "rocketmq-broker": "896m",
    "postgres": "256m",
}
NAMESRV_JAVA_OPTS = "-Xms128m -Xmx256m -Xmn64m"
# The broker also runs the gRPC proxy; with a 384m heap its off-heap use (pre-touched G1 heap,
# Netty, threads) reached a 768m cap at start-up and was OOM-killed, so heap is 256m.
BROKER_JAVA_OPTS = "-Xms256m -Xmx256m -Xmn96m -XX:MaxDirectMemorySize=128m"
JAVA_BACKEND_HEAP = ["-Xms256m", "-Xmx768m"]
# Below this much available memory the stack is likely to push the host into swap or OOM.
MIN_AVAILABLE_MB = 4096
HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
# `ports: !override` in the generated Compose overrides needs Compose 2.24.4.
MIN_COMPOSE = (2, 24, 4)
# Before Engine 28, hosts on the same layer-2 network could reach ports published on 127.0.0.1.
MIN_ENGINE = (28, 0, 0)
# Every container and volume this checkout creates carries its owner ID. `up` and `down` refuse
# to adopt or delete resources of the same Compose project without it, such as a Quick Start
# stack (scripts/demo/start-infrastructure.sh uses the same project names) or another clone.
OWNER_LABEL = "io.lecturelens.demo.owner"
PROJECT_PREFIXES = ("lecturelens-demo-", "lecturelens-demoagent-")
INFRA_SERVICES = (
    "mysql",
    "redis",
    "minio",
    "minio-init",
    "rocketmq-namesrv",
    "rocketmq-store-init",
    "rocketmq-broker",
)
AGENT_SERVICES = ("postgres",)
INFRA_VOLUMES = ("mysql_data", "redis_data", "minio_data", "rocketmq_store")
AGENT_VOLUMES = ("agent-postgres",)
# One lock per instance name for every clone of this user: the Compose project names are
# shared by all clones on the Docker daemon, so a lock inside one clone cannot serialize them.
LOCK_DIR = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "lecturelens-demo"


def model_identity(real):
    """What produced the course material: Java generates translation, notes and chapters."""
    if not real:
        return {"mode": "mock"}
    base = os.environ.get("LECTURELENS_LLM_BASE_URL", REAL_DEFAULTS["LECTURELENS_LLM_BASE_URL"]).rstrip("/")
    return {
        "mode": "real",
        "model": os.environ.get("LECTURELENS_LLM_MODEL", REAL_DEFAULTS["LECTURELENS_LLM_MODEL"]),
        "java_base_url": os.environ.get("LECTURELENS_JAVA_LLM_BASE_URL", base),
    }


def describe_identity(identity):
    if not identity:
        return "an unrecorded model"
    if identity.get("mode") == "mock":
        return "the Mock providers"
    return f"{identity.get('model')} at {identity.get('java_base_url')}"


def memory_limit(service):
    limit = CONTAINER_MEMORY[service]
    return f"    mem_limit: {limit}\n    memswap_limit: {limit}\n"


def version_tuple(text):
    parsed = tuple(int(part) for part in re.findall(r"\d+", text or "")[:3])
    return parsed if len(parsed) == 3 else None


def log(message):
    print(f"[demo] {message}", flush=True)


def fail(message):
    print(f"[demo] FAIL {message}", file=sys.stderr, flush=True)
    sys.exit(1)


class Stack:
    fixture = FIXTURE
    fixture_filename = "binary-search-demo.mp4"
    def __init__(self, instance):
        if not re.fullmatch(r"[a-z0-9-]{1,32}", instance):
            fail("instance must match [a-z0-9-]{1,32}")
        self.instance = instance
        self.infra_project = f"lecturelens-demo-{instance}"
        self.agent_project = f"lecturelens-demoagent-{instance}"
        self.dir = ROOT / ".demo" / f"stack-{instance}"
        self.state_file = self.dir / "state.json"
        self.secrets_file = self.dir / "secrets.json"
        # Shared by all clones and outside self.dir, so `--purge` cannot delete a held lock.
        self.lock_file = LOCK_DIR / f"{instance}.lock"
        self.state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}
        # Always explicit: LECTURELENS_DEMO_INSTANCE in the caller's shell would otherwise redirect it.
        self.stop_command = f"scripts/demo/down.sh --instance {instance}"
        # Popen handles of this invocation, kept before their PID record exists so a rollback
        # interrupted between spawn and registration can still stop them.
        self.children = []

    def lock(self):
        """Serialize up/down for one instance; concurrent runs would overwrite each other's credentials."""
        self.lock_file.parent.mkdir(parents=True, exist_ok=True)
        handle = self.lock_file.open("a")
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            fail(f"another up/down for instance {self.instance} is running (possibly from another clone)")
        self._lock_handle = handle
        # Re-read under the lock: the state may have changed while we waited.
        self.state = json.loads(self.state_file.read_text()) if self.state_file.exists() else {}

    # ---------- helpers ----------
    def save(self):
        self.dir.mkdir(parents=True, exist_ok=True)
        temporary = self.state_file.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.state, indent=2, sort_keys=True) + "\n")
        temporary.replace(self.state_file)

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
        return subprocess.run(
            command, cwd=ROOT, env=env, text=True, capture_output=True, check=False
        ).stdout.strip()

    def docker_query(self, command):
        """Run a read-only docker command; an error must not look like an empty result."""
        try:
            done = subprocess.run(command, cwd=ROOT, text=True, capture_output=True, timeout=60, check=False)
        except (OSError, subprocess.TimeoutExpired) as error:
            raise RuntimeError(f"{' '.join(command[:3])} failed: {error}") from error
        if done.returncode != 0:
            detail = (done.stderr or done.stdout).strip().splitlines()
            raise RuntimeError(
                f"{' '.join(command[:3])} exited {done.returncode}: {detail[-1] if detail else ''}"
            )
        return done.stdout.strip()

    def check_project(self, project):
        if not project.startswith(PROJECT_PREFIXES) or project not in (
            self.infra_project,
            self.agent_project,
        ):
            raise RuntimeError(f"refusing to manage Compose project {project}")

    def expected_names(self, project):
        """Exact container and volume names Compose uses for `project` (it mounts and removes by name)."""
        self.check_project(project)
        services, volumes = (
            (INFRA_SERVICES, INFRA_VOLUMES)
            if project == self.infra_project
            else (AGENT_SERVICES, AGENT_VOLUMES)
        )
        return (
            {f"{project}-{service}-1" for service in services},
            {f"{project}_{volume}" for volume in volumes},
        )

    def docker_resources(self, kind):
        """(name, owner label, Compose project label) of every container or volume on the daemon."""
        labels = "\t".join(
            "{{.Label " + json.dumps(key) + "}}" for key in (OWNER_LABEL, "com.docker.compose.project")
        )
        command = (
            ["docker", "ps", "-a", "--format", "{{.Names}}\t" + labels]
            if kind == "container"
            else ["docker", "volume", "ls", "--format", "{{.Name}}\t" + labels]
        )
        rows = []
        for line in self.docker_query(command).splitlines():
            name, owner, project = (line.split("\t") + ["", ""])[:3]
            rows.append((name, owner, project))
        return rows

    def foreign_resources(self, project):
        """Containers and volumes of `project` that this checkout did not create.

        A resource belongs to `project` if it carries the project's Compose label or has one of the
        exact names Compose would use; an unlabelled volume with the expected name is still mounted
        by `up` and deleted by `down -v`, so it counts. Without an owner ID everything is foreign.
        """
        owner = self.state.get("owner")
        containers, volumes = self.expected_names(project)
        found = []
        for kind, expected in (("container", containers), ("volume", volumes)):
            for name, label, compose_project in self.docker_resources(kind):
                if (compose_project == project or name in expected) and (not owner or label != owner):
                    found.append(f"{kind} {name}")
        return found

    def ownership_problems(self):
        problems = []
        for project in (self.agent_project, self.infra_project):
            try:
                foreign = self.foreign_resources(project)
            except RuntimeError as error:
                problems.append(f"{project}: ownership check failed ({error})")
                continue
            if foreign:
                problems.append(
                    f"{project} has resources this checkout did not create ({', '.join(foreign[:4])}"
                    f"{', ...' if len(foreign) > 4 else ''})"
                )
        return problems

    def remaining_volumes(self):
        expected = set()
        for project in (self.agent_project, self.infra_project):
            expected |= self.expected_names(project)[1]
        return sorted(name for name, _, _ in self.docker_resources("volume") if name in expected)

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
        self.children.append(process)
        self.state.setdefault("pids", {})[name] = {
            "pid": process.pid,
            "started": self.start_time(process.pid),
        }
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
        missing = [
            tool
            for tool in ("docker", "java", "uv", "node", "npm", "ffmpeg", "ffprobe")
            if not shutil.which(tool)
        ]
        if missing:
            fail("missing tools: " + ", ".join(missing) + " (see README: one-command demo)")
        version = self.capture(["docker", "compose", "version", "--short"])
        parsed = version_tuple(version)
        if not parsed or parsed < MIN_COMPOSE:
            fail(
                f"Docker Compose >= {'.'.join(map(str, MIN_COMPOSE))} is required (found {version or 'none'})"
            )
        try:
            engine = self.docker_query(["docker", "version", "--format", "{{.Server.Version}}"])
        except RuntimeError as error:
            fail(f"cannot reach the Docker daemon: {error}")
        if not version_tuple(engine) or version_tuple(engine) < MIN_ENGINE:
            fail(
                f"Docker Engine >= {'.'.join(map(str, MIN_ENGINE))} is required so that ports published "
                f"on 127.0.0.1 stay local (found {engine or 'none'})"
            )
        java = subprocess.run(["java", "-version"], capture_output=True, text=True, check=False).stderr
        match = re.search(r'version "(\d+)', java)
        if not match or int(match.group(1)) < 21:
            fail("Java 21 is required")
        available = self.available_mb()
        if (
            available is not None
            and available < MIN_AVAILABLE_MB
            and os.environ.get("LECTURELENS_DEMO_IGNORE_MEMORY") != "1"
        ):
            fail(
                f"only {available} MB memory available; the demo needs {MIN_AVAILABLE_MB} MB "
                "(stop other stacks, or set LECTURELENS_DEMO_IGNORE_MEMORY=1)"
            )
        if real and not os.environ.get("LECTURELENS_LLM_API_KEY"):
            fail("--real needs LECTURELENS_LLM_API_KEY in the environment (see README: real-model mode)")
        if real:
            for key in ("LECTURELENS_LLM_BASE_URL", "LECTURELENS_JAVA_LLM_BASE_URL"):
                url = urllib.parse.urlsplit(os.environ.get(key, REAL_DEFAULTS["LECTURELENS_LLM_BASE_URL"]))
                # The key travels in an Authorization header, so never in clear text, not even on loopback.
                if url.scheme != "https" or not url.hostname:
                    fail(f"{key} must be an https URL")
        self.check_projects_free()
        for name, record in self.state.get("pids", {}).items():
            if self.owned(record):
                fail(
                    f"recorded process {name} (pid {record['pid']}) is still running; run {self.stop_command} first"
                )

    def check_projects_free(self):
        """Refuse to start if either project holds anything this checkout did not create, or runs."""
        for project in (self.infra_project, self.agent_project):
            try:
                running = self.docker_query(
                    ["docker", "ps", "-q", "--filter", f"label=com.docker.compose.project={project}"]
                )
                foreign = self.foreign_resources(project)
            except RuntimeError as error:
                fail(str(error))
            if foreign:
                fail(
                    f"Compose project {project} has resources this checkout did not create "
                    f"({', '.join(foreign[:4])}{', ...' if len(foreign) > 4 else ''}); stop them from the "
                    "checkout that started them, or use another --instance"
                )
            if running:
                fail(f"{project} is already running; run {self.stop_command} first")

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
        values = {
            key: secrets.token_hex(24)
            for key in (
                "MYSQL_ROOT_PASSWORD",
                "MYSQL_PASSWORD",
                "REDIS_PASSWORD",
                "MINIO_ROOT_PASSWORD",
                "JWT_ACCESS_SECRET",
                "AGENT_SERVICE_SECRET",
                "AGENT_POSTGRES_PASSWORD",
            )
        }
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
        owner = f"    labels:\n      {OWNER_LABEL}: {json.dumps(self.state['owner'])}\n"
        text = "services:\n"
        for service in ("minio-init", "rocketmq-store-init"):
            text += f"  {service}:\n" + memory_limit(service) + owner
        for service, bindings in loopback.items():
            text += f"  {service}:\n" + memory_limit(service) + owner + "    ports: !override\n"
            for key, target in bindings:
                text += f'      - "127.0.0.1:{ports[key]}:{target}"\n'
            if service == "rocketmq-namesrv":
                text += f'    environment:\n      JAVA_OPT_EXT: "{NAMESRV_JAVA_OPTS}"\n'
            if service == "rocketmq-broker":
                text += (
                    "    environment:\n"
                    '      JAVA_OPT_EXT: "-Dcom.rocketmq.proxy.configPath=/tmp/rmq-proxy.json '
                    f'{BROKER_JAVA_OPTS}"\n'
                )
        text += "volumes:\n" + "".join(f"  {volume}:\n" + owner for volume in INFRA_VOLUMES)
        (self.dir / "infra.override.yaml").write_text(text)
        (self.dir / "agent.override.yaml").write_text(
            "services:\n  postgres:\n" + memory_limit("postgres") + owner + "    environment:\n"
            '      POSTGRES_PASSWORD: "${AGENT_POSTGRES_PASSWORD:?required}"\n'
            "    ports: !override\n"
            f'      - "127.0.0.1:{ports["AGENT_POSTGRES_PORT"]}:5432"\n'
            "volumes:\n" + "".join(f"  {volume}:\n" + owner for volume in AGENT_VOLUMES)
        )

    def base_env(self):
        keep = (
            "PATH",
            "HOME",
            "USER",
            "LANG",
            "LC_ALL",
            "JAVA_HOME",
            "UV_CACHE_DIR",
            "UV_PYTHON_INSTALL_DIR",
            "NPM_CONFIG_CACHE",
            "XDG_CACHE_HOME",
            "DOCKER_HOST",
            "DOCKER_CONTEXT",
            "DOCKER_CONFIG",
            "TMPDIR",
        )
        return {key: os.environ[key] for key in keep if key in os.environ}

    def compose_env(self, secret):
        env = self.base_env()
        env.update(
            {
                k: secret[k]
                for k in (
                    "MYSQL_ROOT_PASSWORD",
                    "MYSQL_PASSWORD",
                    "REDIS_PASSWORD",
                    "MINIO_ROOT_USER",
                    "MINIO_ROOT_PASSWORD",
                    "AGENT_POSTGRES_PASSWORD",
                )
            }
        )
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
            # The 8K default sends the 2.5-minute transcript through map/reduce notes, which the
            # deterministic demo provider does not implement; one direct request fits both modes.
            LEARNING_PACKAGE_CONTEXT_LIMIT="65536",
        )
        if real:
            model = os.environ.get("LECTURELENS_LLM_MODEL", REAL_DEFAULTS["LECTURELENS_LLM_MODEL"])
            base = os.environ.get(
                "LECTURELENS_LLM_BASE_URL", REAL_DEFAULTS["LECTURELENS_LLM_BASE_URL"]
            ).rstrip("/")
            env.update(
                # 16-second Evidence windows let a citation land near the sentence it quotes. Mock
                # mode keeps the 60-second default: its fixed learning-package text only passes the
                # quality gate for a few long segments.
                COURSELINGO_ASR_EMBEDDED_SUBTITLE_SEGMENT_DURATION="16s",
                MOCK_ASR_ENABLED="false",
                DEMO_MOCK_LLM_ENABLED="false",
                # Java requires an ASR provider. The demo course has embedded subtitles, so ASR is
                # never called; the unreachable placeholder makes an accidental call fail closed.
                SILICONFLOW_ASR_ENABLED="true",
                SILICONFLOW_API_KEY="unused-placeholder",
                SILICONFLOW_ASR_BASE_URL="http://127.0.0.1:9",
                OPENAI_COMPATIBLE_ENABLED="true",
                OPENAI_COMPATIBLE_API_KEY=os.environ["LECTURELENS_LLM_API_KEY"],
                # Same base as the Agent; Java itself adds /v1 only when the URL has no path.
                OPENAI_COMPATIBLE_BASE_URL=os.environ.get("LECTURELENS_JAVA_LLM_BASE_URL", base),
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
                AGENT_LLM_BASE_URL=os.environ.get(
                    "LECTURELENS_LLM_BASE_URL", REAL_DEFAULTS["LECTURELENS_LLM_BASE_URL"]
                ),
                AGENT_LLM_MODEL=os.environ.get(
                    "LECTURELENS_LLM_MODEL", REAL_DEFAULTS["LECTURELENS_LLM_MODEL"]
                ),
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
            self.run(
                ["bash", "mvnw", "-q", "-DskipTests", "package"], cwd=ROOT / "backend", name="build-java"
            )
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
            self.run(
                [
                    str(ROOT / "agent-service/.venv/bin/python"),
                    "-c",
                    script,
                    EMBEDDING_REPO,
                    EMBEDDING_REVISION,
                    str(cache),
                ],
                env=env,
                name="build-embedding",
            )
            marker.write_text("ok\n")
        models = self.dir / "agent-cache/models"
        if not models.exists():
            # Publish by rename so an interrupted copy is never mistaken for a complete cache.
            partial = models.with_name("models.partial")
            shutil.rmtree(partial, ignore_errors=True)
            partial.parent.mkdir(parents=True, exist_ok=True)
            shutil.copytree(cache, partial, ignore=shutil.ignore_patterns("*.ok"))
            partial.rename(models)

    def infrastructure(self, secret):
        env = self.compose_env(secret)
        log("starting MySQL, Redis, MinIO and RocketMQ (Compose project %s)" % self.infra_project)
        self.run(
            self.compose(
                self.infra_project, "up", "-d", "--wait", "--wait-timeout", "300", "mysql", "redis", "minio"
            ),
            env=env,
            name="infra",
            timeout=1800,
        )
        self.run(
            self.compose(
                self.infra_project,
                "up",
                "-d",
                "minio-init",
                "rocketmq-store-init",
                "rocketmq-namesrv",
                "rocketmq-broker",
            ),
            env=env,
            name="infra",
            timeout=600,
        )
        topic = (
            "for attempt in $(seq 1 40); do /home/rocketmq/rocketmq-5.3.4/bin/mqadmin updateTopic "
            "-n rocketmq-namesrv:9876 -b 127.0.0.1:10911 -t courselingo-analysis-task 2>/dev/null "
            '| grep -Fq "create topic to 127.0.0.1:10911 success." && exit 0; sleep 3; done; exit 1'
        )
        self.run(
            self.compose(self.infra_project, "exec", "-T", "rocketmq-broker", "sh", "-lc", topic),
            env=env,
            name="infra",
            timeout=200,
        )
        log("starting PostgreSQL/pgvector (Compose project %s)" % self.agent_project)
        self.run(
            self.compose(self.agent_project, "up", "-d", "--wait", "--wait-timeout", "120"),
            env=env,
            name="infra",
            timeout=600,
        )
        self.mq_ready(secret)

    def mq_ready(self, secret):
        # The proxy accepts gRPC a little after the topic exists; probe it like CI does.
        libs = self.dir / "mq-libs"
        if not libs.exists():
            partial = libs.with_name("mq-libs.partial")
            shutil.rmtree(partial, ignore_errors=True)
            partial.mkdir()
            with zipfile.ZipFile(JAR) as archive:
                for entry in archive.infolist():
                    if entry.filename.startswith("BOOT-INF/lib/") and entry.filename.endswith(".jar"):
                        (partial / Path(entry.filename).name).write_bytes(archive.read(entry))
            partial.rename(libs)
        endpoint = f"127.0.0.1:{self.state['ports']['ROCKETMQ_PROXY_HOST_PORT']}"
        self.run(
            [
                "java",
                "--class-path",
                str(libs / "*"),
                str(ROOT / "scripts/ci/RocketMqReadiness.java"),
                endpoint,
                "courselingo-analysis-task",
                "false",
                "10000",
            ],
            name="infra",
            timeout=180,
        )

    def agent_factory(self, real):
        return "lecturelens_agent.app:create_app" if real else "lecturelens_real_eval.tutor.app:create_app"

    def web_env(self):
        return self.base_env()

    def web_args(self):
        return []

    def services(self, secret, real):
        ports = self.state["ports"]
        java = self.spawn(
            "java",
            ["java", *JAVA_BACKEND_HEAP, f"-Djava.io.tmpdir={self.dir / 'tmp'}", "-jar", str(JAR)],
            ROOT / "backend",
            self.java_env(ports, secret, real),
        )
        (self.dir / "tmp").mkdir(exist_ok=True)
        log("waiting for Java health")
        self.wait_http("java", f"http://127.0.0.1:{ports['APP_PORT']}/actuator/health", 240, java)
        factory = self.agent_factory(real)
        agent = self.spawn(
            "agent",
            [
                str(ROOT / "agent-service/.venv/bin/uvicorn"),
                factory,
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports["AGENT_HTTP_PORT"]),
            ],
            ROOT / "agent-service",
            self.agent_env(ports, secret, real),
        )
        log("waiting for Agent health")
        self.wait_http("agent", f"http://127.0.0.1:{ports['AGENT_HTTP_PORT']}/healthz", 180, agent)
        web_env = self.web_env()
        web_env["VITE_BACKEND_PROXY_TARGET"] = f"http://127.0.0.1:{ports['APP_PORT']}"
        web = self.spawn(
            "web",
            [
                str(ROOT / "frontend/node_modules/.bin/vite"),
                "preview",
                "--host",
                "127.0.0.1",
                "--port",
                str(ports["WEB_PORT"]),
                "--strictPort",
                *self.web_args(),
            ],
            ROOT / "frontend",
            web_env,
        )
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
        saved = self.state.get("task_id")
        if saved:
            # Never start a second (possibly paid) import while the saved one may still finish, and
            # never reuse material prepared by another model. Only FAILED/CANCELED is replaced.
            retry = (
                f"No new upload was started. Run up again later; if it keeps failing, "
                f"`scripts/demo/down.sh --purge --instance {self.instance}` deletes this instance's data."
            )
            try:
                status = self.api("GET", f"/api/tasks/{saved}", token=token)["status"]
            except (RuntimeError, OSError, KeyError, TypeError, ValueError) as error:
                fail(f"cannot read the status of the saved demo course {saved} ({error}). {retry}")
            if status == "SUCCEEDED":
                prepared, active = self.state.get("course_identity"), self.state.get("model_identity")
                if prepared != active:
                    fail(
                        f"the saved demo course was prepared with {describe_identity(prepared)}, but this start "
                        f"uses {describe_identity(active)}; its material is not reused and no new import is "
                        f"started. Use another --instance, or the same mode and model as before."
                    )
                log("demo course already imported; checking its Evidence index")
                self.wait_index(saved, token)
                return
            if status not in ("FAILED", "CANCELED"):
                fail(f"the saved demo course {saved} is still {status}. {retry}")
            log(f"the saved demo course ended {status}; importing it again")
        log("uploading the synthetic demo course and running the media pipeline")
        def record_course(task):
            self.state.update(task_id=task, course_identity=self.state["model_identity"])
            self.save()

        self.import_course(token, record_course)

    def import_course(self, token, record_course):
        video = self.fixture.read_bytes()
        upload = self.api(
            "POST",
            "/api/uploads/sessions",
            {
                "filename": self.fixture_filename,
                "sizeBytes": len(video),
                "chunkSizeBytes": len(video),
                "totalChunks": 1,
                "fileMd5": hashlib.md5(video).hexdigest(),
            },
            token,
        )["uploadId"]
        boundary = "demo-" + secrets.token_hex(12)
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
            token,
            content_type=f"multipart/form-data; boundary={boundary}",
        )
        self.api("POST", f"/api/uploads/sessions/{upload}/complete", token=token)
        task = self.api(
            "POST",
            "/api/tasks",
            {"uploadId": upload, "sourceLanguage": "en", "targetLanguage": "zh-CN"},
            token,
        )["taskId"]
        record_course(task)
        deadline = time.monotonic() + 600
        while True:
            status = self.api("GET", f"/api/tasks/{task}", token=token)
            if status["status"] == "SUCCEEDED":
                break
            if status["status"] in ("FAILED", "CANCELED") or time.monotonic() > deadline:
                fail(
                    f"demo course status {status['status']} {status.get('errorCode')}; see {self.dir / 'java.log'}"
                )
            time.sleep(2)
        try:
            self.api("POST", f"/api/tasks/{task}/chapters/generate", token=token)
        except RuntimeError as error:
            log(f"chapter generation skipped: {error}")
        self.wait_index(task, token)
        return task

    def wait_index(self, task, token):
        deadline = time.monotonic() + 300
        while self.api("GET", f"/api/tasks/{task}/evidence/index-status", token=token)["status"] != "READY":
            if time.monotonic() > deadline:
                fail("Evidence index did not become READY; see agent.log")
            time.sleep(2)

    # ---------- commands ----------
    def up(self, real):
        started = time.monotonic()
        if not self.fixture.exists():
            fail(f"missing {self.fixture}")
        self.lock()
        self.prerequisites(real)
        self.dir.mkdir(parents=True, exist_ok=True)
        self.dir.chmod(0o700)
        secret = self.load_secrets()
        ports = self.choose_ports()
        model = (
            os.environ.get("LECTURELENS_LLM_MODEL", REAL_DEFAULTS["LECTURELENS_LLM_MODEL"]) if real else None
        )
        # Labels every container and volume this checkout creates (see OWNER_LABEL).
        self.state.setdefault("owner", secrets.token_hex(16))
        self.state.update(
            mode="real" if real else "mock", model=model, model_identity=model_identity(real), pids={}
        )
        self.save()
        self.write_compose_files(ports, secret)
        self.build()
        # From here on this invocation owns containers and processes; a failure tears them down
        # (volumes and logs stay) so the next `up` is not blocked by a half-started stack.
        try:
            self.infrastructure(secret)
            self.services(secret, real)
            self.seed(secret)
        except BaseException:
            log("start-up failed; stopping what this attempt started (volumes and logs are kept)")
            for failure in self.teardown(purge=False):
                log(f"cleanup failed: {failure}; run {self.stop_command}")
            raise
        self.state["ready_seconds"] = round(time.monotonic() - started, 1)
        self.save()

        self.report_ready(real)

    def report_ready(self, real):
        url = f"http://127.0.0.1:{ports['WEB_PORT']}/tasks/{self.state['task_id']}"
        mode = (
            "REAL: model calls are billed to your key"
            if real
            else "MOCK: deterministic providers, no API key, no external model calls"
        )
        # The password stays out of terminal scrollback and CI logs; it is only in the 0600 secrets file.
        print(
            f"""
LectureLens demo is ready in {self.state["ready_seconds"]}s ({mode})
  Open:     {url}
  Account:  {DEMO_EMAIL} (password: DEMO_PASSWORD in {self.secrets_file})
  Logs:     {self.dir}
  Stop:     {self.stop_command}
""",
            flush=True,
        )

    @staticmethod
    def available_mb():
        """MemAvailable on Linux; None elsewhere (macOS has no cheap equivalent, so no check)."""
        try:
            for line in Path("/proc/meminfo").read_text().splitlines():
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) // 1024
        except OSError:
            return None
        return None

    @staticmethod
    def start_time(pid):
        """A start-time identity for `pid` that does not depend on the caller's time zone or locale.

        Linux: boot ID plus the start tick from /proc/<pid>/stat. Elsewhere: `ps -o lstart=`
        rendered in UTC with the C locale. None if the process is gone.
        """
        try:
            stat = Path(f"/proc/{pid}/stat").read_text()
            boot = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
            # The command name may contain spaces or parentheses; fields resume after the last ')'.
            return f"linux:{boot}:{stat.rsplit(')', 1)[1].split()[19]}"
        except (OSError, IndexError):
            if Path("/proc/self/stat").exists():
                return None  # Linux, and the process is gone
        env = dict(os.environ, TZ="UTC", LC_ALL="C")
        out = subprocess.run(
            ["ps", "-o", "lstart=", "-p", str(pid)], capture_output=True, text=True, env=env, check=False
        )
        return out.stdout.strip() or None

    def owned(self, record):
        # A PID alone can be reused by an unrelated process; require the recorded start time too.
        if not isinstance(record, dict):
            return False
        started = self.start_time(record["pid"])
        return started is not None and started == record.get("started")

    @staticmethod
    def stop_group(pid, alive):
        """SIGTERM the process group, wait up to 15 s, then SIGKILL it."""
        try:
            os.killpg(pid, signal.SIGTERM)
            for _ in range(30):
                if not alive():
                    return
                time.sleep(0.5)
            os.killpg(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass

    def teardown(self, purge):
        failures = []
        for name, record in reversed(list(self.state.get("pids", {}).items())):
            if self.owned(record):
                log(f"stopping {name} (pid {record['pid']})")
                self.stop_group(record["pid"], lambda record=record: self.owned(record))
        # Children of this invocation whose PID record may not have been written yet. A Popen
        # handle that has not been reaped cannot refer to a reused PID.
        for process in self.children:
            if process.poll() is None:
                log(f"stopping pid {process.pid}")
                self.stop_group(process.pid, lambda process=process: process.poll() is None)
        self.state["pids"] = {}
        if self.dir.exists():
            self.save()
        if (self.dir / "compose.env").exists():
            # Any resource this checkout did not create stops the whole removal: nothing is removed
            # from either project, and the caller reports it instead of resolving it.
            problems = self.ownership_problems()
            if problems:
                return [f"{problem}; nothing removed" for problem in problems]
            env = self.compose_env(self.load_secrets())
            extra = ["-v"] if purge else []
            # Try both projects even if the first fails or hangs, then report every failure.
            for project in (self.agent_project, self.infra_project):
                log(f"removing containers of {project}{' and its volumes' if purge else ''}")
                try:
                    with (self.dir / "down.log").open("a") as out:
                        code = subprocess.run(
                            self.compose(project, "down", "--remove-orphans", "--timeout", "10", *extra),
                            cwd=ROOT,
                            env=env,
                            stdout=out,
                            stderr=subprocess.STDOUT,
                            timeout=300,
                            check=False,
                        ).returncode
                except (OSError, subprocess.TimeoutExpired) as error:
                    failures.append(f"{project} ({error})")
                    continue
                if code != 0:
                    failures.append(f"{project} (compose down exited {code})")
            if purge and not failures:
                # Compose can warn about a volume in use and still exit 0; keep the owner ID until
                # every expected volume is really gone so a later purge can finish the job.
                try:
                    remaining = self.remaining_volumes()
                except RuntimeError as error:
                    remaining = [f"(volume check failed: {error})"]
                if remaining:
                    failures.append(f"volumes still present: {', '.join(remaining)}")
        return failures

    def down(self, purge):
        self.lock()
        if (self.dir / "compose.env").exists():
            # Checked before any process is stopped, so a refusal changes nothing.
            problems = self.ownership_problems()
            if problems:
                fail(
                    "refusing to stop or remove anything: "
                    + "; ".join(problems)
                    + ". Remove them from the checkout that created them, or by hand."
                )
        failures = self.teardown(purge)
        if failures:
            fail(f"could not remove {'; '.join(failures)}; see {self.dir / 'down.log'}; local state kept")
        if purge and self.dir.exists():
            shutil.rmtree(self.dir)
        log("stopped")

    def status(self):
        print(json.dumps({k: v for k, v in self.state.items()}, indent=2, sort_keys=True))
        for name, record in self.state.get("pids", {}).items():
            print(f"{name}: pid {record['pid']} {'running' if self.owned(record) else 'stopped'}")


def main():
    parser = argparse.ArgumentParser(description="LectureLens one-command demo stack")
    parser.add_argument("command", choices=["up", "down", "status"])
    parser.add_argument("--instance", default=os.environ.get("LECTURELENS_DEMO_INSTANCE", "default"))
    parser.add_argument(
        "--real", action="store_true", help="use LECTURELENS_LLM_API_KEY instead of Mock providers"
    )
    parser.add_argument("--purge", action="store_true", help="down: also delete volumes and generated state")
    args = parser.parse_args()
    stack = Stack(args.instance)
    if args.command == "up":
        try:
            stack.up(args.real)
        except KeyboardInterrupt:
            fail(f"interrupted; run {stack.stop_command} if anything is left running")
    elif args.command == "down":
        stack.down(args.purge)
    else:
        stack.status()


if __name__ == "__main__":
    main()
