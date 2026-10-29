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
import secrets
import signal
import subprocess
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from types import SimpleNamespace

from load import Paths, group

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
spec = importlib.util.spec_from_file_location(
    "existing_smoke", ROOT / "scripts/ci/mock-study-tutor-e2e.py"
)
existing = importlib.util.module_from_spec(spec)
spec.loader.exec_module(existing)


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


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
    for key, file in (
        ("cgroup_cpu_max", "/sys/fs/cgroup/cpu.max"),
        ("cgroup_memory_max", "/sys/fs/cgroup/memory.max"),
    ):
        if Path(file).exists():
            result[key] = Path(file).read_text().strip()
    return result


class Environment(existing.Smoke):
    def __init__(self, args):
        suffix = secrets.token_hex(6)
        existing.DEMO = f"lecturelens-perf-p0-{suffix}-infra"
        existing.AGENT = f"lecturelens-perf-p0-{suffix}-pg"
        super().__init__(SimpleNamespace(output_dir=args.output, legacy_only=False))
        self.options = args
        self.result["schema_version"] = 1
        self.result["started_at_utc"] = datetime.now(timezone.utc).isoformat()
        self.result["not_run"] = [
            "rental-machine full baseline",
            "real-model Tutor quality",
            "Tutor evaluation expansion/blind review",
            "Agent full pytest (no product changes)",
        ]

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
            host = self.result["machine"]
            quota = host.get("cgroup_cpu_max", "max").split()
            constrained = quota[0] != "max" and int(quota[0]) / int(quota[1]) < 16
            limit = host.get("cgroup_memory_max", "max")
            if (
                host["affinity_cpus"] < 16
                or host["memory_bytes"] < 60_000_000_000
                or constrained
                or (limit != "max" and int(limit) < 60_000_000_000)
            ):
                raise RuntimeError(
                    "Rental profile requires at least 16 available vCPUs / 60 GB RAM"
                )
            self.result["not_run"].remove("rental-machine full baseline")
        self.result["config"] = {
            "profile": self.options.profile,
            "scenarios": self.options.scenarios,
            "concurrency": self.options.concurrency,
            "requests_per_group": self.options.requests,
            "admission_seconds": self.options.seconds,
            "operation_timeout_seconds": self.options.timeout,
            "mock_model_delay_ms_per_decision": self.options.mock_delay_ms,
            "qa_rate_limit_enabled": True,
            "qa_rate_limit_per_owner_per_minute": self.options.qa_per_minute,
            "embedding": "hash384/perf-p0-hash384-v1; no semantic model inference",
            "uvicorn_workers": 1,
            "tutor_workers": 1,
            "retriever_lock": "original nonblocking single in-process lock",
            "http_client": "httpx closed loop; trust_env=false; no retries/redirects",
            "top_k": 8,
            "poll_seconds": 0.1,
            "warmup": "one excluded operation per selected scenario before the whole matrix",
            "topology": "one synthetic owner/course/revision shared by all workers; fresh Tutor Session per operation",
            "llm_mode": "mock",
            "java_real_providers": False,
            "agent_non_loopback_guard": True,
            "study_enabled": True,
            "feedback_enabled": False,
            "offline_dependency_bootstrap": self.options.offline,
            "minio_source_build": self.options.build_minio,
        }
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
        # Always package this checkout; never reuse a jar built at an unrecorded SHA.
        command = ["bash", "mvnw", "-B", "-DskipTests"]
        if self.options.offline:
            command += ["-o"]
        self.run(command + ["package"], "build", 600, ROOT / "backend")
        self.result["jar_sha256"] = digest(self.jar)
        extracted = self.out / "java-app"
        with zipfile.ZipFile(self.jar) as archive:
            for name in archive.namelist():
                if name.startswith(("BOOT-INF/classes/", "BOOT-INF/lib/")):
                    archive.extract(name, extracted)
            manifest = archive.read("META-INF/MANIFEST.MF").decode()
        self.main_class = next(
            line.split(": ", 1)[1].strip()
            for line in manifest.splitlines()
            if line.startswith("Start-Class:")
        )
        self.env["PERF_APP_MAIN_CLASS"] = self.main_class
        classes = extracted / "BOOT-INF/classes"
        libs = extracted / "BOOT-INF/lib/*"
        addon = self.out / "java-addon"
        addon.mkdir()
        self.classpath = os.pathsep.join((str(addon), str(classes), str(libs)))
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
        for binary in ("java", "docker"):
            command = [binary, "--version"]
            self.result[binary + "_version"] = self.capture(command)
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
                    print(
                        f"{self.result['label']} {scenario} c={concurrency} attempted={result['attempted']} failed={result['failed']} busy503={result['retrieval_busy_503']}",
                        flush=True,
                    )
                    if result["undrained_tutor"]:
                        raise RuntimeError(
                            "Undrained Tutor work; refusing subsequent groups"
                        )

    def attest(self):
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
            "| Scenario | C | Attempts | Failed | Busy 503 | P50/P95 all (ms) | Successful ops/s |",
            "|---|---:|---:|---:|---:|---:|---:|",
        ]
        for item in self.result.get("groups", []):
            lat = item["latency_ms"]["all"]
            lines.append(
                f"| {item['scenario']} | {item['concurrency']} | {item['attempted']} | {item['failed']} | {item['retrieval_busy_503']} | {lat['p50']}/{lat['p95']} | {item['successful_per_second']:.3f} |"
            )
        lines += [
            "",
            "NOT_RUN: " + "; ".join(self.result["not_run"]),
            "",
            "See result.json for fingerprints, success/failure percentiles, error codes and stop conditions; requests.jsonl includes warmup markers.",
        ]
        (self.out / "REPORT.md").write_text("\n".join(lines) + "\n")

    def execute(self):
        def interrupted(*_):
            raise KeyboardInterrupt("Harness interrupted; owned cleanup follows")

        signal.signal(signal.SIGTERM, interrupted)
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
            try:
                with self.stage("cleanup"):
                    self.cleanup()
                    for project in self.owned:
                        for kind in ("container", "volume", "network"):
                            assert not self.capture(
                                [
                                    "docker",
                                    kind,
                                    "ls",
                                    "-q",
                                    "--filter",
                                    f"label=com.docker.compose.project={project}",
                                ]
                            ), f"Owned {kind} remains"
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
        "--offline",
        action="store_true",
        help="Use cached Maven/Python/container dependencies",
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
    args.scenarios = args.scenarios.split(",")
    try:
        args.concurrency = [int(c) for c in args.concurrency.split(",")]
    except ValueError:
        parser.error("Concurrency must be comma-separated integers")
    if (
        not args.scenarios
        or any(s not in ("S1", "S2", "S3") for s in args.scenarios)
        or len(set(args.scenarios)) != len(args.scenarios)
    ):
        parser.error("Scenarios must be a unique selection of S1,S2,S3")
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
        or not 0 <= args.mock_delay_ms <= 5000
    ):
        parser.error("Invalid positive limits/delay/concurrency")
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
