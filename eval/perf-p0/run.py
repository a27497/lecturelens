#!/usr/bin/env python3
"""Fresh loopback-only Mock stack -> closed-loop scenarios -> results -> owned cleanup."""

import argparse
import asyncio
import hashlib
import importlib.util
import json
import math
import os
import platform
import re
import resource
import secrets
import shutil
import signal
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from importlib.metadata import distributions
from pathlib import Path
from types import SimpleNamespace

import httpx
from build_cache import fingerprint as build_fingerprint
from build_cache import validate_reuse
from lecturelens_agent.retrieval import DEFAULT_QUERY_CONCURRENCY, MAX_QUERY_CONCURRENCY
from lecturelens_agent.study.runtime import DEFAULT_RUN_CONCURRENCY, MAX_RUN_CONCURRENCY
from load import SCHEMA_VERSION, Paths, outcome_delta
from load import group as run_group

HERE = Path(__file__).resolve().parent
SCENARIOS = ("S1", "S2", "S3", "S4")
FACTORY_LINE = re.compile(
    r"PERF_FACTORY hash384; retrieval_concurrency=(\d+); run_concurrency=(\d+);"
)
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "existing_smoke", ROOT / "scripts/ci/mock-study-tutor-e2e.py"
)
existing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(existing)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def process_start_ticks(pid):
    try:
        # comm may contain spaces; fields following the final ')' start at field 3.
        return Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()[19]
    except (OSError, IndexError):
        return None


def source():
    def git(*args):
        return subprocess.check_output(["git", *args], cwd=ROOT, text=True).strip()

    status = git("status", "--porcelain", "--untracked-files=all")
    return {
        "sha": git("rev-parse", "HEAD"),
        "source_dirty": bool(status),
        "status_sha256": hashlib.sha256(status.encode()).hexdigest(),
    }


def machine():
    cpuinfo = Path("/proc/cpuinfo").read_text()
    meminfo = Path("/proc/meminfo").read_text()
    result = {
        "platform": platform.platform(),
        "architecture": platform.machine(),
        "python": platform.python_version(),
        "logical_cpus": os.cpu_count(),
        "affinity_cpus": len(os.sched_getaffinity(0)),
        "cpu_model": next(
            (
                line.split(":", 1)[1].strip()
                for line in cpuinfo.splitlines()
                if line.startswith("model name")
            ),
            "unknown",
        ),
        "memory_bytes": int(
            next(
                line.split()[1]
                for line in meminfo.splitlines()
                if line.startswith("MemTotal:")
            )
        )
        * 1024,
    }
    result["cgroup_limits"] = cgroup_limits()
    result["rlimit_nofile"] = resource.getrlimit(resource.RLIMIT_NOFILE)
    result["rlimit_nproc"] = resource.getrlimit(resource.RLIMIT_NPROC)
    return result


def cgroup_limits(root=Path("/sys/fs/cgroup"), membership=Path("/proc/self/cgroup")):
    """Read visible v2 ancestors; missing/unreadable limits cannot authorize a rental run."""
    try:
        entries = membership.read_text().splitlines()
        relative = next(e[3:] for e in entries if e.startswith("0::"))
        parts = Path(relative).parts[1:]
        if ".." in parts:
            return {"verified": False}
        leaf = root.joinpath(*parts)
        # A cgroup namespace may expose the current subtree directly at the mount root.
        if not leaf.exists():
            return {"verified": False}
        cpu, memory, paths = [], [], []
        for directory in (leaf, *leaf.parents):
            if directory != root and root not in directory.parents:
                break

            # The real v2 mount root has no parent controller limit files.
            def read_limit(name, unlimited, directory=directory):
                file = directory / name
                if (
                    directory == root
                    and not file.exists()
                    and (root / "cgroup.controllers").is_file()
                ):
                    return unlimited
                return file.read_text().strip()

            quota, period = read_limit("cpu.max", "max 100000").split()
            limit = read_limit("memory.max", "max")
            if quota != "max":
                cpu.append(int(quota) / int(period))
            if limit != "max":
                memory.append(int(limit))
            paths.append(str(directory.relative_to(root)))
            if directory == root:
                break
        return {
            "verified": True,
            "cpu_limit": min(cpu) if cpu else None,
            "memory_limit": min(memory) if memory else None,
            "visible_ancestors": paths,
        }
    except (OSError, ValueError, StopIteration, ZeroDivisionError):
        return {"verified": False}


def require_rental_host(host):
    limits = host["cgroup_limits"]
    if (
        host["affinity_cpus"] < 16
        or host["memory_bytes"] < 60_000_000_000
        or not limits["verified"]
        or (limits["cpu_limit"] is not None and limits["cpu_limit"] < 16)
        or (
            limits["memory_limit"] is not None
            and limits["memory_limit"] < 60_000_000_000
        )
    ):
        raise RuntimeError(
            "Rental profile requires verified visible cgroup v2 limits, >=16 available vCPUs and >=60 GB RAM"
        )


def config(options):
    """Recorded, fingerprinted point configuration (schema v3)."""
    return {
        "profile": options.profile,
        "scenarios": options.scenarios,
        "concurrency": options.concurrency,
        "requests_per_group": options.requests,
        "admission_seconds": options.seconds,
        "operation_timeout_seconds": options.timeout,
        "mock_model_delay_ms_per_decision": options.mock_delay_ms,
        "qa_rate_limit_enabled": True,
        "qa_rate_limit_per_owner_per_minute": options.qa_per_minute,
        "embedding": "hash384/perf-p0-hash384-v1; no semantic model inference",
        "uvicorn_workers": 1,
        # Requested values; result.effective_agent_lanes records what the Agent built.
        "agent_retrieval_concurrency": options.retrieval_concurrency,
        "agent_run_concurrency": options.run_concurrency,
        "retrieval_admission": (
            "Step 6 lanes, per Uvicorn process: AGENT_RETRIEVAL_CONCURRENCY "
            "non-blocking query slots (BoundedSemaphore); full -> immediate 503 "
            "Retrieval busy + Retry-After: 1, no queue; index APPLY has its own "
            "single non-blocking lock (503 Indexing busy); PLAN/DELETE take no lock; "
            "snapshot rebuilt/deleted during search -> 409 Evidence index changed "
            "+ Retry-After: 1"
        ),
        "study_run_lanes": (
            "1 dispatcher + AGENT_RUN_CONCURRENCY worker threads; different Sessions "
            "in parallel, one Session serialized in creation order; dispatcher "
            "re-polls at most every 1 s"
        ),
        "tutor_workers": 1,
        "tutor_worker_model": (
            "real_eval TutorRuntime: one tutor-worker thread, 0.5 s idle poll; "
            "not governed by AGENT_RUN_CONCURRENCY"
        ),
        "http_client": "httpx closed loop; trust_env=false; no retries/redirects",
        "top_k": 8,
        "poll_seconds": 0.1,
        "warmup": "one excluded operation per selected scenario before the whole matrix",
        "topology": "one synthetic owner/course/revision shared by all workers; fresh Tutor/Study Session per operation",
        "llm_mode": "mock",
        "java_real_providers": False,
        "agent_non_loopback_guard": True,
        "study_enabled": True,
        "study_mock_task": "GENERATE_CARDS: two delayed Mock decisions, one Java-authorized SEARCH",
        "feedback_enabled": False,
        "offline_dependency_bootstrap": options.offline,
        "java_build_mode": "reused" if options.reuse_build_from else "fresh",
        "minio_source_build": options.build_minio,
        "run_deadline_seconds": options.run_deadline,
        "latency_contract": "v3 = v2 (operation excludes cancellation cleanup; turn timer starts before turn/Run submit; wall includes cleanup/drain) + client-observed queue_ms/execution_ms split at the first poll seeing running",
    }


def effective_lanes(log_text):
    """Read the lane sizes the Agent factory actually constructed."""
    found = FACTORY_LINE.findall(log_text)
    if len(found) != 1:
        raise RuntimeError("Agent lane configuration line missing or repeated")
    retrieval, run = (int(v) for v in found[0])
    return {"agent_retrieval_concurrency": retrieval, "agent_run_concurrency": run}


class Environment(existing.Smoke):
    def __init__(self, args):
        suffix = secrets.token_hex(6)
        existing.DEMO = f"lecturelens-perf-p0-{suffix}-infra"
        existing.AGENT = f"lecturelens-perf-p0-{suffix}-pg"
        super().__init__(SimpleNamespace(output_dir=args.output, legacy_only=False))
        self.options = args
        self.result["output_directory"] = str(self.out)
        self.result["repository_root"] = str(ROOT)
        self.result["runner_pid"] = os.getpid()
        self.result["runner_start_ticks"] = process_start_ticks(os.getpid())
        self.result["schema_version"] = SCHEMA_VERSION
        self.result["started_at_utc"] = datetime.now(timezone.utc).isoformat()
        self.result["not_run"] = [
            "rental-machine full baseline",
            "real-model Tutor quality",
            "Tutor evaluation expansion/blind review",
            "Agent full pytest (no product changes)",
        ]

    def save(self):
        self.result["owned_projects"] = list(self.owned)
        super().save()

    def spawn(self, command, name, cwd=ROOT, env=None):
        process = super().spawn(command, name, cwd, env)
        self.result.setdefault("children", []).append(
            {
                "name": name,
                "pid": process.pid,
                "start_ticks": process_start_ticks(process.pid),
            }
        )
        self.save()
        return process

    def run(self, command, name, timeout=120, cwd=ROOT):
        # Record ownership before an up command can partially create resources or be killed.
        self.save()
        super().run(command, name, timeout, cwd)

    def compose(self, project, *arguments):
        if project == existing.AGENT:
            files = ["-f", str(HERE / "compose.yaml")]
        else:
            files = ["-f", str(ROOT / "compose.yaml")]
            if self.options.build_minio:
                files += ["-f", str(ROOT / "compose.ci-minio.yml")]
            files += ["-f", str(self.out / "loopback.compose.yaml")]
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

    def preflight(self):
        super().preflight()
        self.env.update(
            PERF_MOCK_MODEL_DELAY_MS=str(self.options.mock_delay_ms),
            AGENT_RETRIEVAL_CONCURRENCY=str(self.options.retrieval_concurrency),
            AGENT_RUN_CONCURRENCY=str(self.options.run_concurrency),
            COURSELINGO_QA_RATE_LIMIT_ENABLED="true",
            COURSELINGO_QA_RATE_LIMIT_PER_MINUTE=str(self.options.qa_per_minute),
        )
        self.env["PYTHONPATH"] += os.pathsep + str(HERE)
        self.result["source"] = source()
        if self.result["source"]["source_dirty"] and not self.options.allow_dirty:
            raise RuntimeError(
                "Refuse dirty source; commit first, or use --allow-dirty for diagnostic runs only"
            )
        self.result["label"] = (
            "DEV_SMOKE_NOT_RESUME"
            if self.options.profile == "dev"
            else "RENTAL_MOCK_BASELINE"
        )
        self.result["machine"] = machine()
        if self.options.profile == "rental":
            require_rental_host(self.result["machine"])
            self.result["not_run"].remove("rental-machine full baseline")
        self.result["config"] = config(self.options)
        self.result["python_distributions"] = sorted(
            (d.metadata["Name"], d.version) for d in distributions()
        )
        files = (
            list(HERE.glob("*.py"))
            + list(HERE.glob("*.yaml"))
            + list(HERE.glob("*.sh"))
            + list((HERE / "java").glob("*.java"))
        )
        files += [
            ROOT / f
            for f in (
                "compose.yaml",
                "compose.ci-minio.yml",
                ".env.demo.example",
                "agent-service/uv.lock",
                "backend/pom.xml",
                "scripts/ci/mock-study-tutor-e2e.py",
                "infra/rocketmq/broker.conf",
                "infra/rocketmq/rmq-proxy.json",
                "infra/minio/Dockerfile.ci",
            )
        ]
        self.result["file_sha256"] = {
            str(p.relative_to(ROOT)): digest(p) for p in sorted(files)
        }
        self.result["config_sha256"] = hashlib.sha256(
            json.dumps(self.result["config"], sort_keys=True).encode()
        ).hexdigest()

    def dependencies(self):
        self.result["java_version"] = self.capture(["java", "--version"])
        self.result["javac_version"] = self.capture(["javac", "--version"])
        if self.options.reuse_build_from:
            from verify import verify

            build_dir = self.options.reuse_build_from.resolve()
            verify(build_dir, self.result["head"], check_inputs=True)
            previous = json.loads((build_dir / "result.json").read_text())
            identity = validate_reuse(
                previous,
                self.result,
                build_dir,
                self.result["java_version"],
                self.result["javac_version"],
            )
            self.result["java_build"] = {
                "mode": "reused",
                "from_directory": str(build_dir),
                "seed_result_sha256": digest(build_dir / "result.json"),
                "artifacts": identity,
            }
            self.jar = build_dir / "java-build.jar"
            self.java_classpath(build_dir)
        else:
            self.build_java()
        self.result["jar_sha256"] = digest(self.jar)
        for binary in ("docker", "uv"):
            self.result[binary + "_version"] = self.capture([binary, "--version"])
        self.result["compose_version"] = self.capture(
            ["docker", "compose", "version", "--short"]
        )
        images = set()
        for project in (existing.DEMO, existing.AGENT):
            images.update(
                self.capture(self.compose(project, "config", "--images")).splitlines()
            )
        for image in sorted(images):
            checked = subprocess.run(
                ["docker", "image", "inspect", image],
                env=self.env,
                capture_output=True,
                check=False,
            )
            if self.options.offline and checked.returncode:
                raise RuntimeError(
                    "Container image missing; omit --offline to pull/build pinned dependencies"
                )
        if self.options.build_minio and not self.options.offline:
            self.run(
                self.compose(existing.DEMO, "build", "minio", "minio-init"),
                "minio-build",
                1200,
            )

    def java_classpath(self, directory):
        with zipfile.ZipFile(self.jar) as archive:
            manifest = archive.read("META-INF/MANIFEST.MF").decode()
        self.env["PERF_APP_MAIN_CLASS"] = next(
            line.split(": ", 1)[1].strip()
            for line in manifest.splitlines()
            if line.startswith("Start-Class:")
        )
        self.classpath = os.pathsep.join(
            str(directory / name)
            for name in (
                "java-addon",
                "java-app/BOOT-INF/classes",
                "java-app/BOOT-INF/lib/*",
            )
        )

    def build_java(self):
        # Cache only artifacts built here; a target/ jar alone has no source identity.
        command = ["bash", "mvnw", "-B", "-DskipTests"]
        if self.options.offline:
            command += ["-o"]
        self.run(command + ["clean", "package"], "build", 600, ROOT / "backend")
        shutil.copyfile(self.jar, self.out / "java-build.jar")
        self.jar = self.out / "java-build.jar"
        extracted = self.out / "java-app"
        with zipfile.ZipFile(self.jar) as archive:
            for name in archive.namelist():
                if name.startswith(("BOOT-INF/classes/", "BOOT-INF/lib/")):
                    archive.extract(name, extracted)
        addon = self.out / "java-addon"
        addon.mkdir()
        self.java_classpath(self.out)
        self.run(
            [
                "javac",
                "-cp",
                self.classpath,
                "-d",
                str(addon),
                *[str(p) for p in sorted((HERE / "java").glob("*.java"))],
            ],
            "compile-delay-wrapper",
            60,
        )
        self.result["java_build"] = {
            "mode": "fresh",
            "artifacts": build_fingerprint(self.out),
        }

    def java(self):
        self.free_port(self.result["ports"]["APP_PORT"])
        process = self.spawn(
            [
                "java",
                f"-Djava.io.tmpdir={self.out / 'tmp'}",
                "-cp",
                self.classpath,
                "perf.PerfMain",
            ],
            "java",
            ROOT / "backend",
        )
        self.health(process, self.base, "/actuator/health")
        assert "PERF_MOCK_QA_WRAPPER" in (self.out / "java.log").read_text(), (
            "QA delay wrapper not installed"
        )
        assert (
            self.sql("SELECT COUNT(*) FROM flyway_schema_history WHERE success=0")
            == "0"
        )

    def start_agent(self):
        self.free_port(self.result["ports"]["AGENT_HTTP_PORT"])
        process = self.spawn(
            [
                str(ROOT / "agent-service/.venv/bin/python"),
                "-m",
                "uvicorn",
                "perf_app:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--workers",
                "1",
                "--port",
                str(self.result["ports"]["AGENT_HTTP_PORT"]),
            ],
            "agent",
            ROOT / "agent-service",
        )
        self.health(process, self.agent_base, "/healthz")
        # The log drain thread may trail the health probe by a line.
        text = self.wait(
            lambda: (self.out / "agent.log").read_text(),
            FACTORY_LINE.search,
            10,
            "Agent lane configuration log",
        )
        lanes = effective_lanes(text)
        configured = {
            k: self.result["config"][k]
            for k in ("agent_retrieval_concurrency", "agent_run_concurrency")
        }
        if lanes != configured:
            raise RuntimeError("Agent lanes differ from the requested configuration")
        self.result["effective_agent_lanes"] = lanes
        self.save()
        return process

    def fingerprints(self):
        images = {}
        for project in self.owned:
            ids = self.capture(self.compose(project, "ps", "-aq")).splitlines()
            for container in ids:
                ports = json.loads(
                    self.capture(
                        [
                            "docker",
                            "inspect",
                            "--format",
                            "{{json .HostConfig.PortBindings}}",
                            container,
                        ]
                    )
                )
                if any(
                    binding["HostIp"] != "127.0.0.1"
                    for bindings in (ports or {}).values()
                    for binding in bindings or []
                ):
                    raise RuntimeError("Refuse a non-loopback published container port")
                line = self.capture(
                    [
                        "docker",
                        "inspect",
                        "--format",
                        "{{.Config.Image}} {{.Image}}",
                        container,
                    ]
                )
                name, image = line.split()
                images[name] = image
        self.result["docker_image_ids"] = images
        self.result["corpus"] = {
            "source": "generated two-second sample video + existing DemoMock ASR/translation",
            "video_sha256": digest(ROOT / ".demo/lecturelens-sample.mp4"),
            "evidence_count": len(self.canonical),
            "vector_chunk_count": int(
                self.sql(
                    f"SELECT count(*) FROM evidence_vector WHERE owner_id={self.owner} AND course_id='{self.task}'",
                    pg=True,
                )
            ),
            "normalized_text_sha256": hashlib.sha256(
                json.dumps(
                    sorted(e["normalizedText"] for e in self.canonical.values()),
                    ensure_ascii=False,
                ).encode()
            ).hexdigest(),
            "synthetic_owner": int(self.owner),
            "course_id": self.task,
            "revision": self.api("GET", f"/api/tasks/{self.task}/study/status")[
                "revision"
            ],
        }
        self.save()

    async def matrix(self):
        paths = Paths(
            self.base,
            self.agent_base,
            self.token,
            self.env["AGENT_SERVICE_SECRET"],
            int(self.owner),
            self.task,
            self.result["corpus"]["revision"],
            sorted(self.canonical),
        )
        self.result["warmups"] = []
        self.result["groups"] = []
        control = httpx.AsyncClient(trust_env=False, timeout=10, follow_redirects=False)

        async def group(*args, **kwargs):
            # Groups are sequential and drained, so the counter delta is this group's
            # server-side retrieval traffic (snapshots are outside its wall time).
            before = await paths.retrieval_outcomes(control)
            result = await run_group(*args, **kwargs)
            result["agent_retrieval_outcomes"] = outcome_delta(
                before, await paths.retrieval_outcomes(control)
            )
            return result

        async with control:
            await self.measure(paths, group)

    async def measure(self, paths, group):
        with (self.out / "requests.jsonl").open("w") as raw:
            for scenario in self.options.scenarios:
                result = await group(
                    paths,
                    scenario,
                    1,
                    requests=1,
                    timeout=self.options.timeout,
                    raw=raw,
                    warmup=True,
                    provenance={
                        "label": self.result["label"],
                        "source_sha": self.result["head"],
                    },
                )
                self.result["warmups"].append(result)
                self.save()
                if result["failed"]:
                    raise RuntimeError(
                        f"{scenario} low-concurrency warmup failed; refusing to report a healthy load path"
                    )
            for scenario in self.options.scenarios:
                for concurrency in self.options.concurrency:
                    result = await group(
                        paths,
                        scenario,
                        concurrency,
                        requests=self.options.requests,
                        seconds=self.options.seconds,
                        timeout=self.options.timeout,
                        raw=raw,
                        provenance={
                            "label": self.result["label"],
                            "source_sha": self.result["head"],
                        },
                    )
                    self.result["groups"].append(result)
                    self.save()
                    classes = result["failure_classes"]
                    print(
                        f"{self.result['label']} {scenario} c={concurrency} attempted={result['attempted']} failed={result['failed']} busy503={classes['retrieval_busy_503']} changed409={classes['evidence_index_changed_409']} other={classes['other_unexpected']} server={result['agent_retrieval_outcomes']}",
                        flush=True,
                    )
                    if result["undrained_tutor"]:
                        raise RuntimeError(
                            "Undrained Tutor/Study work; refusing subsequent groups"
                        )

    def attest(self):
        build_dir = self.options.reuse_build_from or self.out
        if build_fingerprint(build_dir) != self.result["java_build"]["artifacts"]:
            raise RuntimeError("Java build artifacts changed during the run")
        self.result["java_build"]["unchanged_at_end"] = True
        assert (self.out / "guard-active.log").exists(), "Agent network guard missing"
        assert not (self.out / "denied-network.log").exists(), (
            "Non-loopback Agent connection attempted"
        )
        assert self.sql("SELECT count(*) FROM agent_model_connection", pg=True) == "0"
        assert (
            self.sql(
                "SELECT count(*) FROM study_run WHERE model_mode<>'mock' OR model_config IS NOT NULL",
                pg=True,
            )
            == "0"
        )
        if "S2" in self.options.scenarios:
            assert "PERF_MOCK_QA_DECIDE" in (self.out / "java.log").read_text()
        if "S3" in self.options.scenarios:
            assert "PERF_MOCK_TUTOR_DECIDE" in (self.out / "agent.log").read_text()
        if "S4" in self.options.scenarios:
            assert "PERF_MOCK_STUDY_DECIDE" in (self.out / "agent.log").read_text()
        self.result["external_models"] = {
            "configured_calls": 0,
            "agent_socket_guard": "active, no denied attempts",
            "java": "DemoMock type enforced; real flags disabled; no OS packet attribution",
        }
        self.result["end_source"] = source()
        assert self.result["source"] == self.result["end_source"], (
            "Source changed during run"
        )
        self.result["valid_clean_source_evidence"] = not self.result["source"][
            "source_dirty"
        ]

    def report(self):
        lines = [
            f"# {self.result.get('label', 'FAILED_PREFLIGHT')}",
            "",
            f"SHA: `{self.result.get('head', 'unknown')}`",
            f"Success: `{self.result.get('success', False)}`; clean source: `{self.result.get('valid_clean_source_evidence', False)}`",
            "",
            "Mock mechanisms only; no real-model quality or production/resume throughput claim.",
            "",
            f"Agent lanes (effective): `{self.result.get('effective_agent_lanes', 'not started')}`",
            "",
            (
                "Client failure classes: busy = direct S1 `503 Retrieval busy`; changed = direct S1 "
                "`409 Evidence index changed`; other = every other failure, including Java-mediated "
                "retrieval failures. Server columns count Python `Retriever.search` outcomes for all paths."
            ),
            "",
            "| Scenario | C | Attempts | Failed | Busy 503 | Changed 409 | Other | Server busy/changed | P50/P95 all (ms) | P50/P95 success (ms) | Queue P50/P95 (ms) | Exec P50/P95 (ms) | Successful ops/s |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|",
        ]
        for item in self.result.get("groups", []):
            lat, good = item["latency_ms"]["all"], item["latency_ms"]["success"]
            classes = item["failure_classes"]
            server = item["agent_retrieval_outcomes"]
            queue, execution = item["queue_ms"], item["execution_ms"]
            lines.append(
                f"| {item['scenario']} | {item['concurrency']} | {item['attempted']} | {item['failed']} "
                f"| {classes['retrieval_busy_503']} | {classes['evidence_index_changed_409']} | {classes['other_unexpected']} "
                f"| {server['busy_503']}/{server['index_changed_409']} | {lat['p50']}/{lat['p95']} | {good['p50']}/{good['p95']} "
                f"| {queue['p50']}/{queue['p95']} | {execution['p50']}/{execution['p95']} | {item['successful_per_second']:.3f} |"
            )
        lines += [
            "",
            "NOT_RUN: " + "; ".join(self.result["not_run"]),
            "",
            "See result.json for fingerprints, success/failure percentiles, error codes and stop conditions; requests.jsonl includes warmup markers.",
        ]
        (self.out / "REPORT.md").write_text("\n".join(lines) + "\n")

    def cleanup(self):
        signal.alarm(0)
        failures = []
        log_failures = []
        for process, _ in reversed(self.children):
            try:
                self.stop(process)
            except Exception as error:  # noqa: BLE001 -- still visit all owned resources
                failures.append(type(error).__name__)
        for project in reversed(self.owned):
            try:
                self.run(
                    self.compose(project, "logs", "--no-color"),
                    f"{project}-services",
                    20,
                )
            except Exception as error:  # noqa: BLE001 -- log failure must never suppress teardown
                log_failures.append({"project": project, "error": type(error).__name__})
            try:
                self.run(
                    self.compose(
                        project, "down", "-v", "--remove-orphans", "--timeout", "5"
                    ),
                    f"{project}-down",
                    45,
                )
            except Exception as error:  # noqa: BLE001 -- still visit the other project
                failures.append(type(error).__name__)
            for kind in ("container", "volume", "network"):
                try:
                    if self.capture(
                        [
                            "docker",
                            kind,
                            "ls",
                            "-q",
                            "--filter",
                            f"label=com.docker.compose.project={project}",
                        ]
                    ):
                        failures.append(f"Remaining_{kind}")
                except Exception as error:  # noqa: BLE001 -- retain inspection failure and finish teardown
                    failures.append(type(error).__name__)
        self.result["cleanup_log_errors"] = log_failures
        (self.out / "docker-end.txt").write_text(
            json.dumps(
                {
                    "owned_projects": self.owned,
                    "failures": failures,
                    "log_errors": log_failures,
                },
                indent=2,
            )
            + "\n"
        )
        if failures:
            raise RuntimeError(f"Owned cleanup failed: {failures}")

    def execute(self):
        def interrupted(*_):
            raise KeyboardInterrupt("Harness interrupted; owned cleanup follows")

        signal.signal(signal.SIGTERM, interrupted)
        signal.signal(signal.SIGALRM, interrupted)
        signal.alarm(self.options.run_deadline)
        success = False
        try:
            with self.stage("preflight"):
                self.preflight()
            with self.stage("build"):
                self.dependencies()
            with self.stage("isolated-infrastructure"):
                self.infrastructure()
                self.free_port(self.result["ports"]["AGENT_POSTGRES_PORT"])
                self.owned.append(existing.AGENT)
                self.run(
                    self.compose(
                        existing.AGENT, "up", "-d", "--wait", "--wait-timeout", "90"
                    ),
                    "pg-up",
                    120,
                )
            with self.stage("Java-and-Agent"):
                self.java()
                self.start_agent()
            with self.stage("synthetic-course"):
                self.course()
                self.fingerprints()
            with self.stage("load-matrix"):
                asyncio.run(self.matrix())
            with self.stage("attestation"):
                self.attest()
            success = True
        except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- always retain failure and clean owned resources
            self.result["failure"] = self.redact(str(error))
        finally:
            signal.alarm(0)
            try:
                with self.stage("cleanup"):
                    self.cleanup()
            except (Exception, KeyboardInterrupt) as error:  # noqa: BLE001 -- always retain failure and clean owned resources
                self.result["cleanup_failure"] = self.redact(str(error))
                success = False
            self.result["success"] = success
            self.save()
            self.report()
            print(f"Results: {self.out / 'result.json'}; success={success}", flush=True)
        return 0 if success else 1


def arguments(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--profile", choices=("dev", "rental"), default="dev")
    parser.add_argument(
        "--output", required=True, type=Path, help="New private result directory"
    )
    parser.add_argument("--scenarios", default="S1,S2,S3")
    parser.add_argument("--concurrency", default="1")
    stop = parser.add_mutually_exclusive_group()
    stop.add_argument("--requests", type=int)
    stop.add_argument("--seconds", type=float)
    parser.add_argument("--timeout", type=float, default=60)
    parser.add_argument("--mock-delay-ms", type=int, default=25)
    parser.add_argument("--qa-per-minute", type=int, default=10)
    parser.add_argument(
        "--retrieval-concurrency",
        type=int,
        default=DEFAULT_QUERY_CONCURRENCY,
        help=f"AGENT_RETRIEVAL_CONCURRENCY for this point (1-{MAX_QUERY_CONCURRENCY})",
    )
    parser.add_argument(
        "--run-concurrency",
        type=int,
        default=DEFAULT_RUN_CONCURRENCY,
        help=f"AGENT_RUN_CONCURRENCY for this point (1-{MAX_RUN_CONCURRENCY})",
    )
    parser.add_argument(
        "--run-deadline",
        type=int,
        default=1200,
        help="Total runner execution deadline; cleanup runs after this deadline",
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Use cached Maven/Python/container dependencies",
    )
    parser.add_argument(
        "--reuse-build-from",
        type=Path,
        help="Reuse verified Java artifacts from a successful fresh-build run in this checkout",
    )
    parser.add_argument(
        "--build-minio",
        action="store_true",
        help="Use existing CI source-pinned MinIO builds instead of release images",
    )
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Diagnostic only; never clean-source acceptance",
    )
    args = parser.parse_args(argv)
    if args.reuse_build_from and (not args.offline or args.allow_dirty):
        parser.error("--reuse-build-from requires --offline and clean committed source")
    args.scenarios = args.scenarios.split(",")
    try:
        args.concurrency = [int(c) for c in args.concurrency.split(",")]
    except ValueError:
        parser.error("Concurrency must be comma-separated integers")
    if (
        not args.scenarios
        or any(s not in SCENARIOS for s in args.scenarios)
        or len(set(args.scenarios)) != len(args.scenarios)
    ):
        parser.error("Scenarios must be a unique selection of S1,S2,S3,S4")
    if args.requests is None and args.seconds is None:
        args.requests = 3 if args.profile == "dev" else None
        args.seconds = 60 if args.profile == "rental" else None
    if (
        not args.concurrency
        or min(args.concurrency) < 1
        or max(args.concurrency) > 1024
        or len(set(args.concurrency)) != len(args.concurrency)
        or not math.isfinite(args.timeout)
        or args.timeout <= 0
        or args.qa_per_minute < 1
        or not 1 <= args.run_deadline <= 86400
        or not 0 <= args.mock_delay_ms <= 5000
    ):
        parser.error("Invalid positive limits/delay/concurrency")
    # Same ranges as the product's startup validation; out-of-range never reaches a stack.
    if not 1 <= args.retrieval_concurrency <= MAX_QUERY_CONCURRENCY:
        parser.error(f"--retrieval-concurrency must be 1-{MAX_QUERY_CONCURRENCY}")
    if not 1 <= args.run_concurrency <= MAX_RUN_CONCURRENCY:
        parser.error(f"--run-concurrency must be 1-{MAX_RUN_CONCURRENCY}")
    if (
        args.requests is not None
        and args.requests < 1
        or args.seconds is not None
        and (not math.isfinite(args.seconds) or args.seconds <= 0)
    ):
        parser.error("Stopping condition must be positive")
    if args.profile == "dev" and (
        max(args.concurrency) > 32
        or (args.requests or 0) > 200
        or (args.seconds or 0) > 10
    ):
        parser.error("Dev smoke cap: concurrency<=32, requests<=200 or admission<=10s")
    return args


if __name__ == "__main__":
    sys.exit(Environment(arguments()).execute())
