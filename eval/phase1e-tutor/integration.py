"""Fresh Java/PG/Vue stack, public course packets, and offline-only Flash HTTP."""

import argparse
import importlib.util
import json
import os
import re
import signal
import sys
import tempfile
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

from diagnose import coverage, packet, read_archive, read_dataset, sha

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "phase1d_harness", ROOT / "eval/phase1d-lightweight/integration.py"
)
PHASE1D = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(PHASE1D)
BASE = PHASE1D.BASE
sys.path.insert(0, str(ROOT / "agent-service/src"))

QUESTION = "Explain the asynchronous course video learning pipeline."


class Smoke(PHASE1D.Smoke):
    def preflight(self):
        BASE.Smoke.preflight(self)
        self.env.update(
            TUTOR_ENGINE="light",
            PHASE1D_REQUEST_LOG=str(self.out / "authored-requests.jsonl"),
            PYTHONDONTWRITEBYTECODE="1",
            JAVA_TOOL_OPTIONS="-Xmx512m -XX:ActiveProcessorCount=2",
            OMP_NUM_THREADS="1",
        )
        self.env["PYTHONPATH"] += os.pathsep + os.pathsep.join(
            str(ROOT / name)
            for name in (
                "agent-service/src",
                "eval/phase1d-lightweight",
                "eval/phase1e-tutor",
            )
        )
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
        for service, opts in {
            "rocketmq-namesrv": "-Xms64m -Xmx192m -Xmn32m -XX:MaxDirectMemorySize=64m",
            "rocketmq-broker": "-Dcom.rocketmq.proxy.configPath=/tmp/rmq-proxy.json -Xms64m -Xmx384m -Xmn64m -XX:MaxDirectMemorySize=256m",
        }.items():
            text = text.replace(
                f"  {service}:\n",
                f"  {service}:\n    environment:\n      JAVA_OPT_EXT: {opts} -XX:ActiveProcessorCount=2\n",
            )
        override.write_text(text)
        self.result["not_run"] = [
            "real model quality",
            "paid reviewer",
            "paid embedding",
            "GitHub CI PENDING",
        ]

    def compose(self, project, *args):
        # Export evidence, then remove this run's disposable test volumes.
        return BASE.Smoke.compose(self, project, *args)

    def browser(self):
        previous = self.env["TMPDIR"]
        # Chromium's SingletonSocket uses a short Unix socket address.
        with tempfile.TemporaryDirectory(prefix="ll-phase1e-", dir="/tmp") as temp:
            self.env["TMPDIR"] = temp
            try:
                super().browser()
            finally:
                self.env["TMPDIR"] = previous

    def start_flash(self):
        import psycopg
        from lecturelens_real_eval.tutor.flash_ledger import (
            TARGET_SCHEMA,
            Grant,
            build_digest,
        )
        from lecturelens_real_eval.tutor.flash_provider import (
            MODEL,
            MODEL_VERSION,
            PRICE_ID,
            RESERVE_NANO_USD,
        )

        with psycopg.connect(self.env["AGENT_DATABASE_URL"]) as conn:
            conn.execute(TARGET_SCHEMA)
            (target,) = conn.execute(
                "INSERT INTO tutor_flash_target DEFAULT VALUES RETURNING target_id"
            ).fetchone()
        self.revision = int(
            self.sql(
                f"SELECT content_revision FROM analysis_task WHERE id='{self.task}'"
            )
        )
        now = datetime.now(timezone.utc)
        grant = Grant.model_validate(
            {
                "version": "lecturelens-phase1e-flash-v1",
                "mode": "offline-fake",
                "grant_id": uuid.uuid4().hex,
                "target_id": str(target),
                "build_sha256": build_digest(),
                "dataset_sha256": sha(QUESTION.encode()),
                "model": MODEL,
                "model_version": MODEL_VERSION,
                "price_id": PRICE_ID,
                "issued_at": now - timedelta(seconds=1),
                "expires_at": now + timedelta(hours=1),
                "accepts_supplier_risk": True,
                "request_limit": 1,
                "budget_nano_usd": RESERVE_NANO_USD,
                "sessions": [
                    {
                        "owner_id": int(self.owner),
                        "course_id": self.task,
                        "revision": self.revision,
                        "request_key": "frozen-offline",
                        "turns": [{"text": QUESTION}],
                        "evidence_sha256": [
                            sha(row["normalizedText"][:1200].encode())
                            for row in self.canonical.values()
                            if row["normalizedText"].strip()
                        ],
                    }
                ],
            }
        )
        grant_file = self.out / "offline-fake-grant.json"
        grant_file.write_text(grant.model_dump_json())
        grant_file.chmod(0o600)
        env = self.env | {
            "TUTOR_FLASH_EXPERIMENT": "enabled",
            "AGENT_LLM_MODE": "real",
            "STUDY_AGENT_ENABLED": "false",
            "TUTOR_FLASH_GRANT_FILE": str(grant_file),
            "TUTOR_FLASH_API_KEY": "synthetic-phase1e-http",
            "PHASE1E_FAKE_REQUEST_LOG": str(self.out / "flash-requests.jsonl"),
        }
        self.free_port(self.result["ports"]["AGENT_HTTP_PORT"])
        process = self.spawn(
            [
                PHASE1D.PYTHON,
                "-m",
                "uvicorn",
                "flash_fake:create_app",
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.result["ports"]["AGENT_HTTP_PORT"]),
            ],
            "flash-agent",
            ROOT / "agent-service",
            env=env,
        )
        self.health(process, self.agent_base, "/healthz")
        return process

    def flash_roundtrip(self):
        self.api("POST", self.tutor, {"request_key": "not-authorized"}, expected=404)
        session = self.new_session("frozen-offline")
        assert session["revision"] == self.revision
        assert len(self.api("GET", self.tutor)["sessions"]) == 1
        self.ask("frozen-turn")
        turn = self.turn("frozen-turn", "completed")
        self.answer(turn)
        assert turn["model_calls"] == 1 and turn["usage"][0]["total_tokens"] == 150
        assert self.ask("frozen-turn")["replayed"]
        logs = (self.out / "flash-requests.jsonl").read_text().splitlines()
        assert len(logs) == 1
        calls = self.sql("SELECT row_to_json(c) FROM tutor_flash_call c", pg=True)
        row = json.loads(calls)
        assert row["charged_nano_usd"] == 84120 and row["published_at"]
        assert row["request_sha256"] == json.loads(logs[0])["request_sha256"]
        (self.out / "flash-ledger.json").write_text(calls + "\n")
        self.result["flash_http"] = {
            "provider_requests": 0,
            "mock_http_requests": 1,
            "journal_calls": 1,
        }
        self.token = ""
        self.login()
        try:
            self.api("GET", self.session_path, expected=404)
        finally:
            self.token = self.owner_token
        self.result["cross_service"] = (
            "authenticated Java -> signed Python -> offline HTTP + PG -> canonical Java Evidence"
        )

    def retrieval_preflight(self):
        from lecturelens_agent.study.authority import EvidenceAuthority
        from lecturelens_real_eval.tutor.light import LightTutorRuntime
        from lecturelens_real_eval.tutor.store import TutorStore

        runtime = LightTutorRuntime(
            TutorStore(self.env["AGENT_DATABASE_URL"], engine="light"),
            EvidenceAuthority(self.base, self.env["AGENT_SERVICE_SECRET"]),
        )
        dataset = read_dataset()
        historic = read_archive(dataset, self.args.archive)
        reports = {}
        for dialogue in dataset["dialogues"]:
            excerpts = packet(dataset, dialogue["source"], historic)
            self.install_packet(excerpts)
            scope = {
                "owner_id": int(self.owner),
                "course_id": self.task,
                "revision": self.revision,
            }
            history = []
            for case in dialogue["turns"]:
                turn = {"learner_text": case["question"], "socratic": case["socratic"]}
                context = runtime.prepare(scope, turn, history)
                reports[case["id"]] = coverage(case, excerpts, context["evidence"])
                history.append(turn | {"status": "completed", "answer": None})
        (self.out / "retrieval.json").write_text(json.dumps(reports, indent=2) + "\n")
        self.result["retrieval"] = {
            key: report["coverage"] for key, report in reports.items()
        }
        assert all(
            report["coverage"] in {"FULL", "EXPECTED_GAP"}
            for report in reports.values()
        )

    def install_packet(self, excerpts):
        # The synthetic test task is ours. No product import route or write to an existing stack.
        scope = f"task_id='{self.task}' AND user_id={self.owner}"
        inserts = []
        for i, text in enumerate(excerpts.values()):
            text_hex = text.encode().hex()
            inserts.append(
                f"('{self.task}',{self.owner},{i},{i * 1000},{(i + 1) * 1000},'en',0x{text_hex})"
            )
        self.sql(
            "START TRANSACTION;"
            + "".join(
                f"DELETE FROM {table} WHERE {scope};"
                for table in (
                    "subtitle_segment",
                    "subtitle_translation_segment",
                    "video_keyframe_ocr",
                    "video_keyframe_analysis",
                )
            )
            + "INSERT INTO subtitle_segment(task_id,user_id,segment_index,start_millis,end_millis,language,text) "
            + "VALUES "
            + ",".join(inserts)
            + ";"
            + f"UPDATE analysis_task SET content_revision=content_revision+1 WHERE id='{self.task}'; COMMIT;"
        )
        page = self.api("GET", f"/api/tasks/{self.task}/evidence")
        self.revision = page["revision"]
        self.wait(
            lambda: self.api("GET", f"/api/tasks/{self.task}/evidence/index-status"),
            lambda row: (
                row["status"] == "READY" and row["indexedRevision"] == self.revision
            ),
            70,
            "fresh packet index",
        )

    def execute(self):
        def interrupted(*_):
            raise TimeoutError("phase1e integration interrupted")

        signal.signal(signal.SIGTERM, interrupted)
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
            with self.stage("ordinary-mock-and-course"):
                agent = self.start_agent()
                self.course()
            browser_passed = True
            try:
                with self.stage("ordinary-mock-browser"):
                    self.browser()
            except AssertionError:
                browser_passed = False
            self.stop(agent)
            with self.stage("flash-fake-gateway-ledger"):
                flash = self.start_flash()
                self.flash_roundtrip()
            self.stop(flash)
            with self.stage("frozen-retrieval-preflight"):
                self.start_agent()
                self.retrieval_preflight()
            with self.stage("zero-paid-models-and-ownership"):
                self.zero_models()
                self.export()
            success = browser_passed
        except Exception as error:  # noqa: BLE001 -- still run task-owned cleanup
            self.result["error"] = self.redact(str(error))
        finally:
            try:
                with self.stage("cleanup"):
                    self.cleanup()
            except Exception:  # noqa: BLE001 -- cleanup status is recorded by stage
                success = False
            self.result["status"] = "PASS" if success else "FAIL"
            self.save()
        return 0 if success else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--embedding-cache-source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    args = parser.parse_args()
    if not re.fullmatch(r"phase1e-[a-z0-9-]{1,32}", args.instance):
        parser.error("Use a new phase1e-* test identity")
    args.legacy_only = False
    BASE.DEMO = f"lecturelens-{args.instance}-demo"
    BASE.AGENT = f"lecturelens-{args.instance}-agent"
    raise SystemExit(Smoke(args).execute())
