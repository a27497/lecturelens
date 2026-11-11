"""Isolated frozen E3 course staging and first-trial runner."""

import argparse
import importlib.util
import json
import os
import re
import signal
import subprocess
import sys
import time
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
E1 = ROOT / "eval/phase1e-tutor"
sys.path[:0] = [str(ROOT / "agent-service/src"), str(E1)]

from diagnose import (
    authority_text,
    coverage,
    diagnose,
    packet,
    read_archive,
    read_dataset,
    sha,
    verify,
)
from lecturelens_agent.study.authority import EvidenceAuthority
from lecturelens_real_eval.tutor.flash_ledger import build_digest
from lecturelens_real_eval.tutor.flash_phase import (
    CASES,
    DATASET,
    PHASE_EXPIRY,
    PhaseFlashStore,
    PhaseReceipt,
    phase_usage,
    provision_phase,
    provision_target,
)
from lecturelens_real_eval.tutor.flash_provider import (
    MODEL,
    MODEL_VERSION,
    PRICE_ID,
)
from lecturelens_real_eval.tutor.light import LightTutorRuntime
from lecturelens_real_eval.tutor.store import TutorStore
from references import verify as references

SPEC = importlib.util.spec_from_file_location(
    "phase1e_integration", E1 / "integration.py"
)
E2 = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(E2)
BASE = E2.BASE
LIVE_ANCHOR = ROOT / ".data/phase1e3/live-anchor.json"


def write_json(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, default=str, indent=2) + "\n")
    path.chmod(0o600)


class Smoke(E2.Smoke):
    def preflight(self):
        super().preflight()
        self.env["PYTHONPATH"] += os.pathsep + str(Path(__file__).resolve().parent)
        self.dataset = read_dataset()
        self.historic = read_archive(self.dataset, self.args.archive)
        self.cases = verify(self.dataset, self.historic, self.args.upstream_dir)
        assert (
            sha((E1 / "dataset.json").read_bytes()) == DATASET
            and tuple(self.cases) == CASES
        )
        manifest = (E1 / "SHA256SUMS").read_bytes()
        candidate = json.loads((E1 / "CANDIDATE.json").read_bytes())
        assert sha(manifest) == candidate["freeze_manifest_sha256"]
        for line in manifest.decode().splitlines():
            digest, name = line.split()
            assert sha((E1 / name).read_bytes()) == digest
        self.reference_outputs = references()
        self.receipt, self.worker = None, None
        self.journal = {}
        self.reviewed = set()
        self.result["positions"] = dict.fromkeys(CASES, "NOT_RUN")

    def login(self):
        if not self.token:
            super().login()

    def freeze_courses(self):
        authority = EvidenceAuthority(self.base, self.env["AGENT_SERVICE_SECRET"])
        runtime = LightTutorRuntime(
            TutorStore(self.env["AGENT_DATABASE_URL"], engine="light"), authority
        )
        self.sessions, self.requirements, self.scopes = [], [], {}
        reports, seen_courses = {}, set()
        for dialogue in self.dataset["dialogues"]:
            self.course()
            assert self.task not in seen_courses
            seen_courses.add(self.task)
            excerpts = packet(self.dataset, dialogue["source"], self.historic)
            self.install_packet(excerpts)
            scope = {
                "owner_id": int(self.owner),
                "course_id": self.task,
                "revision": self.revision,
            }
            page = self.api("GET", f"/api/tasks/{self.task}/evidence")
            hashes = {
                key: sha(authority_text(text).encode())
                for key, text in excerpts.items()
            }
            actual = [row["normalizedText"] for row in page["items"]]
            assert sorted(sha(text.encode()) for text in actual) == sorted(
                hashes.values()
            )
            session = {
                **scope,
                "request_key": dialogue["id"],
                "evidence_sha256": list(hashes.values()),
                "turns": [],
            }
            history = []
            for case in dialogue["turns"]:
                key = case["id"]
                self.scopes[key] = scope
                turn = {"learner_text": case["question"], "socratic": case["socratic"]}
                prepared = runtime.prepare(scope, turn, history)
                reports[key] = coverage(case, excerpts, prepared["evidence"])
                history.append(turn | {"status": "completed", "answer": None})
                session["turns"].append(
                    {"text": case["question"], "socratic": case["socratic"]}
                )
                self.requirements.append(
                    [
                        [hashes[eid] for eid in group]
                        for group in case["required_evidence"]
                    ]
                )
            self.sessions.append(session)
        write_json(self.out / "retrieval-preflight.json", reports)
        write_json(self.out / "scopes.json", self.scopes)
        self.result["retrieval_preflight"] = {
            key: row["coverage"] for key, row in reports.items()
        }
        assert list(reports) == list(CASES)
        for key, row in reports.items():
            assert row["coverage"] == ("EXPECTED_GAP" if key == "git-2" else "FULL"), (
                key
            )

    def create_receipt(self):
        dsn = self.env["AGENT_DATABASE_URL"]
        mode = "real" if self.args.live else "offline-fake"
        phase_id = provision_phase(dsn, mode)
        now = datetime.now(timezone.utc)
        if self.args.live:
            write_json(self.out / "synthetic-stack-env.json", self.env)
            # A second launcher cannot mint a fresh phase against a rebuilt database.
            with LIVE_ANCHOR.open("x") as stream:
                os.fchmod(stream.fileno(), 0o600)
                json.dump(
                    {
                        "phase_id": phase_id,
                        "dataset_sha256": DATASET,
                        "commit_sha": self.result["head"],
                    },
                    stream,
                )
                stream.flush()
                os.fsync(stream.fileno())
            (LIVE_ANCHOR.parent / "live-dispatch").mkdir(mode=0o700)
            directory = os.open(LIVE_ANCHOR.parent, os.O_DIRECTORY)
            try:
                os.fsync(directory)
            finally:
                os.close(directory)
        grant = {
            "version": "lecturelens-phase1e-flash-v1",
            "mode": mode,
            "grant_id": uuid.uuid4().hex,
            "target_id": provision_target(dsn, "initial"),
            "build_sha256": build_digest(),
            "dataset_sha256": DATASET,
            "model": MODEL,
            "model_version": MODEL_VERSION,
            "price_id": PRICE_ID,
            "issued_at": now - timedelta(seconds=1),
            "expires_at": min(now + timedelta(hours=3), PHASE_EXPIRY)
            if self.args.live
            else now + timedelta(hours=1),
            "accepts_supplier_risk": True,
            "request_limit": 10,
            "budget_nano_usd": 550_000_000,
            "sessions": self.sessions,
        }
        self.receipt = PhaseReceipt.model_validate(
            {
                "phase_id": phase_id,
                "kind": "initial",
                "commit_sha": self.result["head"],
                "case_ids": list(CASES),
                "required": self.requirements,
                "grant": grant,
            }
        )
        path = self.out / "initial-receipt.json"
        write_json(path, self.receipt.model_dump(mode="json"))
        return path

    def start_e3(self, key):
        receipt_path = self.create_receipt()
        env = self.env | {
            "TUTOR_FLASH_EXPERIMENT": "phase1e3",
            "AGENT_LLM_MODE": "real",
            "STUDY_AGENT_ENABLED": "false",
            "TUTOR_E3_RECEIPT_FILE": str(receipt_path),
            "TUTOR_E3_COMMIT_SHA": self.receipt.commit_sha,
            "TUTOR_FLASH_API_KEY": key,
            "PHASE1E_FAKE_REQUEST_LOG": str(self.out / "fake-wire-hashes.jsonl"),
        }
        factory = "e3_fake:create_app"
        if self.args.live:
            self.private.append(key)
            env["LECTURELENS_E3_KEY_INJECTED"] = "phase1e3"
            env["TUTOR_E3_ANCHOR_FILE"] = str(LIVE_ANCHOR)
            factory = "lecturelens_real_eval.tutor.flash_e3_app:create_app"
            # Only this worker gets the injected key and egress to the fixed provider.
            env["PYTHONPATH"] = os.pathsep.join(
                p
                for p in env["PYTHONPATH"].split(os.pathsep)
                if p != str(self.out / "network-guard")
            )
        self.worker = self.spawn(
            [
                sys.executable,
                "-m",
                "uvicorn",
                factory,
                "--factory",
                "--host",
                "127.0.0.1",
                "--port",
                str(self.result["ports"]["AGENT_HTTP_PORT"]),
            ],
            "e3-worker",
            ROOT / "agent-service",
            env=env,
        )
        self.health(self.worker, self.agent_base, "/healthz")

    def record(self):
        store = PhaseFlashStore(
            self.env["AGENT_DATABASE_URL"],
            self.receipt,
            live_anchor=LIVE_ANCHOR if self.args.live else None,
        )
        with store.connect() as conn:
            rows = conn.execute(
                "SELECT * FROM tutor_turn ORDER BY created_at"
            ).fetchall()
            calls = conn.execute(
                "SELECT * FROM tutor_flash_call ORDER BY slot"
            ).fetchall()
            wires = conn.execute(
                "SELECT * FROM tutor_e3_wire ORDER BY started_at"
            ).fetchall()
            usage = phase_usage(conn)
        self.journal = {row["client_turn_id"]: row for row in rows}
        write_json(self.out / "journal.json", self.journal)
        write_json(self.out / "ledger.json", calls)
        self.result["phase_usage"] = usage
        self.result["generation_requests"] = len(wires) if self.args.live else 0
        self.result["offline_mock_requests"] = 0 if self.args.live else len(wires)
        self.result["review_requests"] = 0
        directory = self.out / "wire"
        directory.mkdir(mode=0o700, exist_ok=True)
        for row in wires:
            for field in ("request", "response"):
                if row[field] is not None:
                    path = directory / f"{row['turn_id']}.{field}.body"
                    path.write_bytes(row[field])
                    path.chmod(0o600)
        write_json(
            directory / "transport.json",
            [
                {k: v for k, v in row.items() if k not in {"request", "response"}}
                for row in wires
            ],
        )
        for case, row in self.journal.items():
            position = diagnose(*self.cases[case], row)
            if case in self.reviewed:
                position["semantic_quality"] = "AI_REVIEW_PASS"
            self.result["positions"][case] = position

    def evaluate(self):
        from review_packet import make_packet, reviewed_pass

        ordered_cases = iter(self.receipt.case_ids)
        for plan in self.receipt.grant.sessions:
            endpoint = f"/api/tasks/{plan.course_id}/tutor/sessions"
            sid = self.api("POST", endpoint, {"request_key": plan.request_key})[
                "session"
            ]["session_id"]
            for turn in plan.turns:
                key = next(ordered_cases)
                case, _ = self.cases[key]
                assert (case["question"], case["socratic"]) == (
                    turn.text,
                    turn.socratic,
                )
                assert self.scopes[key]["course_id"] == plan.course_id
                path = endpoint + "/" + sid
                self.api(
                    "POST",
                    path + "/turns",
                    {"client_turn_id": key, **turn.model_dump()},
                )
                reply = self.wait(
                    lambda path=path: self.api("GET", path)["turns"][-1],
                    lambda row: row["status"] in {"completed", "failed", "cancelled"},
                    30,
                    "E3 terminal " + key,
                )
                self.record()
                if not self.args.live:
                    assert reply["status"] == "completed" and reply["model_calls"] == 1
                    return "OFFLINE_PASS"
                diagnostic = self.result["positions"][key]
                if diagnostic["semantic_quality"] != "INDEPENDENT_REVIEW_REQUIRED":
                    return "STOPPED_EXECUTION_OR_RETRIEVAL"
                directory = self.out / "review-packets"
                directory.mkdir(mode=0o700, exist_ok=True)
                review = make_packet(
                    self.cases[key][0], self.journal[key], self.reference_outputs
                )
                write_json(directory / f"{key}.json", review)
                review_dir = self.out / "review-decisions"
                review_dir.mkdir(mode=0o700, exist_ok=True)
                decisions = review_dir / f"{key}.json"
                end = time.monotonic() + self.args.review_wait
                while (
                    not decisions.exists()
                    and time.monotonic() < end
                    and datetime.now(timezone.utc) < self.receipt.grant.expires_at
                ):
                    time.sleep(2)
                if not decisions.exists() or not reviewed_pass(
                    review, json.loads(decisions.read_bytes())
                ):
                    return "STOPPED_REVIEW_UNRESOLVED_OR_FAILED"
                self.reviewed.add(key)
                diagnostic["semantic_quality"] = "AI_REVIEW_PASS"
        return "COMPLETE"

    def compose(self, project, *args):
        # Keep the live databases/WAL for audit and the one possible retest.
        return super().compose(
            project, *(arg for arg in args if not (self.args.live and arg == "-v"))
        )

    def execute_e3(self, key):
        def interrupted(*_):
            raise TimeoutError("E3 runner interrupted")

        signal.signal(signal.SIGTERM, interrupted)
        status = "FAIL"
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
            with self.stage("stage-four-frozen-courses"):
                mock = self.start_agent()
                self.freeze_courses()
                self.stop(mock)
            with self.stage("audited-initial-path"):
                self.start_e3(key)
                status = self.evaluate()
                if not self.args.live:
                    self.zero_models()
        except Exception as error:  # noqa: BLE001 -- logs contain no raw credential
            self.result["error"] = self.redact(str(error))
        finally:
            if self.worker is not None:
                self.stop(self.worker)
                try:
                    self.record()
                except Exception as error:  # noqa: BLE001 -- earlier raw records stay intact
                    self.result["last_export_error"] = type(error).__name__
            try:
                with self.stage("cleanup"):
                    self.cleanup()
            except Exception:  # noqa: BLE001 -- stage records cleanup failure
                status = "FAIL"
            for position in self.result.get("positions", {}).values():
                if (
                    isinstance(position, dict)
                    and position["semantic_quality"] == "INDEPENDENT_REVIEW_REQUIRED"
                ):
                    position["semantic_quality"] = (
                        "UNRESOLVED" if self.args.live else "NOT_RUN"
                    )
            self.result["status"] = status
            self.save()
        return 0 if status in {"OFFLINE_PASS", "COMPLETE"} else 1


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--instance", required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--embedding-cache-source", type=Path, required=True)
    parser.add_argument("--archive", type=Path, required=True)
    parser.add_argument("--upstream-dir", type=Path, required=True)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--confirmed-price-id")
    parser.add_argument(
        "--review-wait", type=int, default=0, choices=range(1201), metavar="0..1200"
    )
    args = parser.parse_args()
    if not re.fullmatch(r"phase1e3-[a-z0-9-]{1,28}", args.instance):
        parser.error("Use a fresh phase1e3-* instance")
    key = "synthetic-phase1e-http"
    if args.live:
        if os.environ.get("LECTURELENS_E3_KEY_INJECTED") != "phase1e3" or not (
            key := os.environ.pop("TUTOR_FLASH_API_KEY", "")
        ):
            parser.error("E3_BLOCKED_EXPLICIT_KEY_INJECTION_REQUIRED")
        if (
            args.confirmed_price_id != PRICE_ID
            or LIVE_ANCHOR.exists()
            or datetime.now(timezone.utc) >= PHASE_EXPIRY
        ):
            parser.error("E3_BLOCKED_PRICE_ID_ANCHOR_OR_EXPIRY")
        if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT).strip():
            parser.error("E3_BLOCKED_DIRTY_CANDIDATE")
    BASE.DEMO = f"lecturelens-{args.instance}-demo"
    BASE.AGENT = f"lecturelens-{args.instance}-agent"
    args.legacy_only = False
    raise SystemExit(Smoke(args).execute_e3(key))
