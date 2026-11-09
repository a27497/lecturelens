"""Reuse the frozen E3 harness with a managed launcher and an independent approval."""

import argparse
import hashlib
import importlib.util
import json
import os
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from lecturelens_real_eval.cli import CLIError, json_file
from lecturelens_real_eval.tutor.flash_phase import CASES, DATASET, PHASE_BUDGET, PHASE_EXPIRY, PHASE_REQUESTS
from lecturelens_real_eval.tutor.flash_provider import PRICE_ID, RESERVE_NANO_USD

from .e3_terminal import check_disk, read_operator_key, require_ssh_tty

OFFLINE_TIMEOUT = 540
SERVICE_USER = "ll-eval"
SERVICE_CREDENTIALS = Path("/run/credentials/lecturelens-eval-e3.service")
AUTHORIZATION = "e3-authorization"
PROVIDER_KEY = "deepseek-api-key"
DEFAULT_ASSETS = {
    "archive": ".data/phase1e/v19-smoke-2227-REAL-review.zip",
    "upstream_dir": ".data/phase1e/source",
    "embedding_cache_source": ".data/phase1e/cross-b/agent-cache/models",
    "java_jar": "backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar",
}


@dataclass(frozen=True)
class Admission:
    directory: Path | None
    approval_id: str
    expires_at: datetime
    java_jar_sha256: str
    commit_sha: str


def options(root, args):
    overrides = json_file(args.assets) if args.assets else {}
    if not isinstance(overrides, dict) or set(overrides) - DEFAULT_ASSETS.keys():
        raise CLIError("E3_INVALID_ASSETS")
    paths = {}
    for name, value in (DEFAULT_ASSETS | overrides).items():
        if not isinstance(value, str) or not value:
            raise CLIError("E3_INVALID_ASSETS")
        path = (root / value).resolve()
        if not (path.is_file() if name in {"archive", "java_jar"} else path.is_dir()):
            raise CLIError(f"E3_ASSET_MISSING_{name.upper()}")
        paths[name] = str(path)
    if not 0 <= args.review_wait <= 1200:
        raise CLIError("E3_INVALID_REVIEW_WAIT")
    return paths | {"review_wait": args.review_wait, "batch": args.batch}


def private_file(directory, name, limit, *, read):
    path = directory / name
    try:
        fd = os.open(path, os.O_RDONLY | os.O_CLOEXEC | os.O_NOFOLLOW | os.O_NONBLOCK)
        with os.fdopen(fd, "rb") as stream:
            info = os.fstat(stream.fileno())
            # systemd may grant its UID access via an ACL with a group-read mask.
            systemd_acl = (
                directory == SERVICE_CREDENTIALS
                and info.st_uid == info.st_gid == 0
                and os.fstatvfs(stream.fileno()).f_flag & os.ST_RDONLY
            )
            if (
                not stat.S_ISREG(info.st_mode)
                or info.st_uid not in {0, os.geteuid()}
                or info.st_mode & (0o037 if systemd_acl else 0o077)
                or not 0 < info.st_size <= limit
            ):
                raise CLIError(f"E3_CREDENTIAL_PERMISSIONS_{name}")
            return stream.read(limit + 1) if read else None
    except OSError:
        raise CLIError(f"E3_CREDENTIAL_REQUIRED_{name}") from None


def service_directory():
    uid = os.geteuid()
    if (
        uid == 0
        or pwd.getpwuid(uid).pw_name != SERVICE_USER
        or os.environ.get("CREDENTIALS_DIRECTORY") != str(SERVICE_CREDENTIALS)
    ):
        raise CLIError("E3_LIVE_REQUIRES_ISOLATED_SYSTEMD_SERVICE")
    try:
        info = SERVICE_CREDENTIALS.stat()
        trusted = (
            stat.S_ISDIR(info.st_mode)
            and info.st_uid in {0, uid}
            and (not info.st_mode & 0o070 or info.st_gid == 0)
            and not info.st_mode & 0o027
            and os.statvfs(SERVICE_CREDENTIALS).f_flag & os.ST_RDONLY
        )
    except OSError:
        trusted = False
    if not trusted:
        raise CLIError("E3_CREDENTIAL_MOUNT_NOT_ISOLATED")
    return SERVICE_CREDENTIALS


def parse_authorization(raw, commit, now):
    try:
        record = json.loads(raw)
        expires = datetime.fromisoformat(record["expires_at"])
        approval = record["approval_id"]
        jar_sha = record["java_jar_sha256"]
        if not (
            set(record)
            == {
                "experiment",
                "approval_id",
                "expires_at",
                "commit_sha",
                "java_jar_sha256",
                "dataset_sha256",
                "price_id",
                "accepts_supplier_risk",
                "budget_nano_usd",
                "initial_requests",
                "retest_requests",
            }
            and record["experiment"] == "e3"
            and record["commit_sha"] == commit
            and re.fullmatch(r"[a-f0-9]{32}", approval)
            and re.fullmatch(r"[a-f0-9]{64}", jar_sha)
            and now < expires <= PHASE_EXPIRY
            and record["dataset_sha256"] == DATASET
            and record["price_id"] == PRICE_ID
            and record["accepts_supplier_risk"] is True
            and type(record["budget_nano_usd"]) is int
            and record["budget_nano_usd"] == PHASE_BUDGET
            and type(record["initial_requests"]) is int
            and record["initial_requests"] == len(CASES)
            and type(record["retest_requests"]) is int
            and record["retest_requests"] == PHASE_REQUESTS - len(CASES)
        ):
            raise ValueError
    except (KeyError, ValueError, TypeError):
        raise CLIError("E3_AUTHORIZATION_INVALID_OR_EXPIRED") from None
    return approval, expires, jar_sha


def git(root, *args):
    return subprocess.check_output(["git", *args], cwd=root, text=True).strip()


def live_admission(root, args):
    if args.dev_ssh:
        require_ssh_tty()
        if datetime.now(timezone.utc) >= PHASE_EXPIRY:
            raise CLIError("E3_AUTHORIZATION_INVALID_OR_EXPIRED")
        if args.confirmed_price_id != PRICE_ID:
            raise CLIError("E3_FROZEN_PRICE_CONFIRMATION_REQUIRED")
        check_checkout(root)
        check_disk(root)
        assets = options(root, args)
        return Admission(
            None,
            uuid.uuid4().hex,
            PHASE_EXPIRY,
            digest_file(Path(assets["java_jar"])),
            git(root, "rev-parse", "HEAD"),
        )
    directory = service_directory()
    if root.stat().st_uid != 0 or root.stat().st_mode & 0o022:
        raise CLIError("E3_LIVE_WORKSPACE_MUST_BE_ADMIN_CONTROLLED")
    check_checkout(root)
    commit = git(root, "rev-parse", "HEAD")
    raw = private_file(directory, AUTHORIZATION, 8192, read=True)
    approval, expires, jar_sha = parse_authorization(raw, commit, datetime.now(timezone.utc))
    assets = options(root, args)
    if digest_file(Path(assets["java_jar"])) != jar_sha:
        raise CLIError("E3_JAVA_ARTIFACT_MISMATCH")
    private_file(directory, PROVIDER_KEY, 1024, read=False)
    return Admission(directory, approval, expires, jar_sha, commit)


def check_checkout(root):
    anchor = root / ".data/phase1e3/live-anchor.json"
    if git(root, "status", "--porcelain") or os.path.lexists(anchor):
        raise CLIError("E3_LIVE_DIRTY_CHECKOUT_OR_CONSUMED_PHASE")


def digest_file(path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def provider_key(context):
    if datetime.now(timezone.utc) >= context.expires_at:
        raise CLIError("E3_AUTHORIZATION_INVALID_OR_EXPIRED")
    raw = private_file(context.directory, PROVIDER_KEY, 1024, read=True)
    try:
        value = raw.decode("ascii").rstrip("\r\n")
    except UnicodeError:
        raise CLIError("E3_PROVIDER_CREDENTIAL_INVALID") from None
    if not re.fullmatch(r"[!-~]{1,512}", value):
        raise CLIError("E3_PROVIDER_CREDENTIAL_INVALID")
    return value


def load_harness(root):
    folder = root / "eval/phase1e3-tutor"
    sys.path.insert(0, str(folder))
    spec = importlib.util.spec_from_file_location("ll_frozen_e3", folder / "preflight.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def evaluate_batch(smoke, before_turn):
    """Collect in frozen order, deferring semantic review while enforcing execution gates."""
    positions = iter(smoke.receipt.case_ids)
    for plan in smoke.receipt.grant.sessions:
        endpoint = f"/api/tasks/{plan.course_id}/tutor/sessions"
        session = smoke.api("POST", endpoint, {"request_key": plan.request_key})["session"]
        path = endpoint + "/" + session["session_id"]
        for turn in plan.turns:
            key = next(positions)
            case, _ = smoke.cases[key]
            assert (case["question"], case["socratic"]) == (turn.text, turn.socratic)
            assert smoke.scopes[key]["course_id"] == plan.course_id
            before_turn()
            smoke.api("POST", path + "/turns", {"client_turn_id": key, **turn.model_dump()})
            reply = smoke.wait(
                lambda path=path: smoke.api("GET", path)["turns"][-1],
                lambda row: row["status"] in {"completed", "failed", "cancelled"},
                30,
                "E3 terminal " + key,
            )
            smoke.record()
            smoke.save()
            diagnostic = smoke.result["positions"][key]
            if (
                reply["status"] != "completed"
                or reply["model_calls"] != 1
                or smoke.result["phase_usage"]["unsettled_nano_usd"]
                or diagnostic["semantic_quality"] != "QUALITY_PENDING"
            ):
                return "STOPPED_EXECUTION_OR_RETRIEVAL"
    # The frozen lifecycle accepts COMPLETE as a successful execution exit.
    return "COMPLETE"


def execute(root, directory, operation, assets, context):
    harness = load_harness(root)
    instance = f"ll-e3-{directory.name}"
    harness.BASE.DEMO = f"lecturelens-{instance}-demo"
    harness.BASE.AGENT = f"lecturelens-{instance}-agent"
    harness.E2.PHASE1D.PYTHON = sys.executable
    args = argparse.Namespace(
        output_dir=directory / "evidence",
        legacy_only=False,
        live=context is not None,
        **{key: Path(value) if key in DEFAULT_ASSETS else value for key, value in assets.items()},
    )
    prepare_only = operation == "preflight"
    developer = context is not None and context.directory is None

    class ManagedE3(harness.Smoke):
        def require_dispatch_disk(self):
            if developer:
                try:
                    check_disk(root)
                except CLIError as error:
                    self.result["local_refusal_exit_code"] = error.exit_code
                    raise

        def spawn(self, command, name, cwd=root, env=None):
            if name == "e3-worker" and self.args.batch and not self.args.live:
                command = [
                    "lecturelens_real_eval.experiments.e3_worker:batch_mock_app"
                    if item == "e3_fake:create_app"
                    else item
                    for item in command
                ]
            return super().spawn(command, name, cwd, env)

        def stage(self, name):
            if prepare_only and name == "audited-initial-path":
                name = "offline-egress-check"
            return super().stage(name)

        def dependencies(self):
            # Preserve the frozen E3 backend source identity and bind the exact live JAR via approval.
            if self.capture(["git", "diff", "17d78636cf97fcf55fe642b1ecc30c5e2ea48865", "--", "backend"]):
                raise CLIError("E3_BACKEND_SOURCE_CHANGED")
            self.jar = self.out / "backend.jar"
            shutil.copy2(self.args.java_jar, self.jar)
            jar_sha = digest_file(self.jar)
            if context and jar_sha != context.java_jar_sha256:
                raise CLIError("E3_JAVA_ARTIFACT_MISMATCH")
            self.result["java_jar_sha256"] = jar_sha
            shutil.copytree(self.args.embedding_cache_source, self.out / "agent-cache/models")

        def create_receipt(self):
            path = super().create_receipt()
            # The parent only stages this receipt. Bind the usable one before worker startup.
            receipt = self.receipt.model_dump(mode="python")
            grant = receipt["grant"]
            grant["budget_nano_usd"] = min(PHASE_BUDGET, grant["request_limit"] * RESERVE_NANO_USD)
            if context:
                grant["expires_at"] = min(grant["expires_at"], context.expires_at)
            self.receipt = harness.PhaseReceipt.model_validate(receipt)
            path.rename(self.out / "receipt-draft.json")
            harness.write_json(path, self.receipt.model_dump(mode="json"))
            return path

        def start_e3(self, key):
            if prepare_only:
                return
            if context:
                if self.result["head"] != context.commit_sha or git(root, "status", "--porcelain"):
                    raise CLIError("E3_CANDIDATE_CHANGED_BEFORE_DISPATCH")
                if developer:
                    self.require_dispatch_disk()
                    check_checkout(root)
                    if datetime.now(timezone.utc) >= context.expires_at:
                        raise CLIError("E3_AUTHORIZATION_INVALID_OR_EXPIRED")
                    try:
                        key = read_operator_key()
                    except CLIError as error:
                        self.result["local_refusal_exit_code"] = error.exit_code
                        raise
                    self.require_dispatch_disk()
                    check_checkout(root)
                    if datetime.now(timezone.utc) >= context.expires_at:
                        raise CLIError("E3_AUTHORIZATION_INVALID_OR_EXPIRED")
                    self.result["approval_id"] = context.approval_id
                    return self.start_pipe_worker(key)
                key = provider_key(context)
            return super().start_e3(key)

        def start_pipe_worker(self, key):
            harness.LIVE_ANCHOR.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
            receipt_path = self.create_receipt()
            env = self.env | {
                "TUTOR_FLASH_EXPERIMENT": "phase1e3",
                "AGENT_LLM_MODE": "real",
                "STUDY_AGENT_ENABLED": "false",
                "TUTOR_E3_RECEIPT_FILE": str(receipt_path),
                "TUTOR_E3_COMMIT_SHA": self.receipt.commit_sha,
                "TUTOR_E3_ANCHOR_FILE": str(harness.LIVE_ANCHOR),
                "LECTURELENS_E3_KEY_INJECTED": "phase1e3",
                "TUTOR_E3_LAUNCHER_PID": str(os.getpid()),
            }
            env.pop("TUTOR_FLASH_API_KEY", None)
            env["PYTHONPATH"] = os.pathsep.join(
                part
                for part in env["PYTHONPATH"].split(os.pathsep)
                if part != str(self.out / "network-guard")
            )
            self.worker = subprocess.Popen(
                [
                    sys.executable,
                    "-m",
                    "uvicorn",
                    "lecturelens_real_eval.experiments.e3_worker:pipe_app",
                    "--factory",
                    "--host",
                    "127.0.0.1",
                    "--port",
                    str(self.result["ports"]["AGENT_HTTP_PORT"]),
                ],
                cwd=root / "agent-service",
                env=env,
                stdin=subprocess.PIPE,
                bufsize=0,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                start_new_session=True,
            )
            # The inherited lifecycle stops self.worker in finally. The credential
            # never enters its logs, argv or environment.
            with self.worker.stdin as pipe:
                if pipe.write(key.encode("ascii")) != len(key):
                    raise CLIError("E3_KEY_PIPE_INCOMPLETE")
            del key

        def record(self):
            super().record()
            if not self.args.batch:
                return
            from review_packet import make_packet

            for key, position in self.result["positions"].items():
                if not isinstance(position, dict):
                    continue
                if position["semantic_quality"] != "INDEPENDENT_REVIEW_REQUIRED":
                    position["semantic_quality"] = "UNRESOLVED"
                    continue
                position["semantic_quality"] = "QUALITY_PENDING"
                directory = self.out / "review-packets"
                directory.mkdir(mode=0o700, exist_ok=True)
                path = directory / f"{key}.json"
                if not path.exists():
                    packet = make_packet(self.cases[key][0], self.journal[key], self.reference_outputs)
                    harness.write_json(path, packet)

        def evaluate(self):
            if prepare_only:
                self.result.update(generation_requests=0, review_requests=0, offline_mock_requests=0)
                return "OFFLINE_PASS"
            if self.args.batch:
                if developer:
                    self.health(self.worker, self.agent_base, "/healthz")
                return evaluate_batch(self, self.require_dispatch_disk)
            return super().evaluate()

        def zero_models(self):
            if prepare_only:
                if (self.out / "denied-network.log").exists() or not (
                    self.out / "guard-active.log"
                ).is_file():
                    raise CLIError("E3_OFFLINE_NETWORK_GUARD")
            else:
                super().zero_models()

    smoke = ManagedE3(args)
    if context and not developer:
        smoke.result["approval_id"] = context.approval_id
    if args.batch:
        smoke.result["collection"] = "batch"
    previous = None
    if developer:

        def hangup(*_):
            raise KeyboardInterrupt

        previous = signal.signal(signal.SIGHUP, hangup)
    try:
        code = smoke.execute_e3("synthetic-phase1e-http")
    finally:
        if previous is not None:
            signal.signal(signal.SIGHUP, previous)
    if prepare_only and code == 0:
        smoke.result["status"] = "PREFLIGHT_PASS"
        smoke.save()
    elif args.batch and code == 0:
        smoke.result["status"] = "COLLECTION_COMPLETE"
        smoke.save()
    return smoke.result.get("local_refusal_exit_code", code)


def validate_reviews(packet, reviews):
    if (
        not isinstance(packet, dict)
        or packet.get("case_id") not in CASES
        or not isinstance(reviews, list)
        or len(reviews) != 2
        or any(not isinstance(review, dict) for review in reviews)
    ):
        raise CLIError("E3_TWO_REVIEW_DECISIONS_REQUIRED")
    claimed = packet.get("packet_sha256")
    source = {key: value for key, value in packet.items() if key != "packet_sha256"}
    actual = hashlib.sha256(json.dumps(source, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    if claimed != actual or not isinstance(packet.get("criteria"), dict):
        raise CLIError("E3_REVIEW_PACKET_INTEGRITY")
    for field in ("model", "independent_context"):
        values = [review.get(field) for review in reviews]
        if any(not isinstance(value, str) or not value.strip() for value in values) or values[0] == values[1]:
            raise CLIError("E3_REVIEW_INDEPENDENCE_REQUIRED")
    for review in reviews:
        checks = review.get("checks")
        if (
            not packet.get("packet_sha256")
            or review.get("packet_sha256") != packet["packet_sha256"]
            or not isinstance(checks, dict)
            or set(checks) != set(packet["criteria"])
            or type(review.get("severe_error")) is not bool
            or not isinstance(review.get("confidence"), str)
            or not isinstance(review.get("claim_checks"), list)
            or not isinstance(review.get("citation_and_teaching_check"), dict)
        ):
            raise CLIError("E3_REVIEW_PACKET_MISMATCH_OR_INCOMPLETE")
