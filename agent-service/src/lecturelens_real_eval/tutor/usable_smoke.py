"""Three-turn development smoke; no dispatch by default and no reviewer calls."""

import hashlib
import json
import os
import re
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path

import httpx
import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo

from lecturelens_real_eval.tutor_channel import EvalError, Ledger

from .bounded_provider import BoundedTutorProvider
from .claim_grounding_runtime import LessonAuthority
from .contracts import Command, Search
from .diagnostic_capture import CaptureTransport, private_file
from .observed_channel import DecodedMetadataTransport, ObservedChannel
from .relevant_authority import RelevantSnapshotAuthority
from .usable_mock import UsableMock
from .usable_policy import UsablePolicy
from .usable_runtime import IDENTITY, OUTPUT_TOKENS, UsableProposal, UsableStore, UsableTutorRuntime

ROOT = Path(__file__).resolve().parents[4]
BASE = ROOT / "eval/tutor-usability-v18-v1"
MAX_REQUESTS, MAX_NANO_USD = 12, 300_000_000
TEST_DSN = "postgresql://tutor_scale:synthetic-local-only@127.0.0.1:25841/lecturelens_agent_acceptance"
SOURCE_ROOTS = [
    "agent-service/src",
    "agent-service/pyproject.toml",
    "backend/src/main",
    "frontend/src",
    "scripts/dev",
]


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def verify_inputs():
    manifest = json.loads((BASE / "candidate.json").read_bytes())
    if manifest["candidate"] != IDENTITY or manifest["default_registration"] is not False:
        raise EvalError("V18_IDENTITY_INVALID")
    if not re.fullmatch(r"[a-f0-9]{40}", manifest["code_commit"]):
        raise EvalError("V18_CODE_COMMIT_INVALID")
    if subprocess.run(
        ["git", "diff", "--quiet", manifest["code_commit"], "--", *SOURCE_ROOTS], cwd=ROOT, check=False
    ).returncode or subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--", *SOURCE_ROOTS], cwd=ROOT
    ):
        raise EvalError("V18_FULL_SOURCE_TREE_CHANGED")
    for name, expected in manifest["files"].items():
        if digest(ROOT / name) != expected:
            raise EvalError("V18_FROZEN_FILE_CHANGED")
    parent = ROOT / "eval/tutor-followup-v17-v1/candidate.json"
    if digest(parent) != manifest["parent_manifest_sha256"]:
        raise EvalError("V18_PARENT_CHANGED")
    for name, expected in json.loads(parent.read_bytes())["files"].items():
        if digest(ROOT / name) != expected:
            raise EvalError("V18_PARENT_SOURCE_CHANGED")
    packet = json.loads((BASE / "sample-candidate.json").read_bytes())
    review = json.loads((BASE / "reference-review-pack.json").read_bytes())
    if review["packet_sha256"] != digest(BASE / "sample-candidate.json"):
        raise EvalError("V18_REFERENCE_BINDING_INVALID")
    if sum(len(s["turns"]) for s in packet["sessions"]) != 3 or packet["gates"]["scheduled"] != 3:
        raise EvalError("V18_PACKET_INVALID")
    return {
        "candidate_sha256": digest(BASE / "candidate.json"),
        "packet_sha256": digest(BASE / "sample-candidate.json"),
        "code_commit": manifest["code_commit"],
        "ready_for_live": False,
        "purpose": "THREE_TURN_DEVELOPMENT_SMOKE_NOT_FULL16_OR_HUMAN_ACCEPTANCE",
        "blockers": [
            "FRESH_PAID_GRANT",
            "CURRENT_PRICING_AND_MODEL_PREFLIGHT",
        ],
        "real_calls": 0,
    }


def live_admission(state, authorization, pricing):
    """Check nonsecret receipts before any provider transport or credential lookup."""
    if not all((authorization, pricing)):
        raise EvalError("V18_LIVE_RECEIPTS_REQUIRED")
    try:
        grant, price = [json.loads(Path(f).read_bytes()) for f in (authorization, pricing)]
    except (OSError, ValueError, UnicodeError):
        raise EvalError("V18_LIVE_RECEIPTS_INVALID") from None
    now = datetime.now(timezone.utc)
    try:
        valid = (
            grant["authorized"] is True
            and grant["scope"] == "ONE_V18_THREE_TURN_SMOKE_NO_RETRY_NO_EXPANSION"
            and grant["candidate_sha256"] == state["candidate_sha256"]
            and grant["packet_sha256"] == state["packet_sha256"]
            and grant["model"] == "deepseek-flash"
            and grant["max_output_tokens"] == OUTPUT_TOKENS
            and grant["max_requests"] == MAX_REQUESTS
            and grant["max_nano_usd"] == MAX_NANO_USD
            and datetime.fromisoformat(grant["expires_utc"]) > now
            and re.fullmatch(r"v18-[a-z0-9-]{8,64}", grant["run_id"])
            and price["requested_model"] == "deepseek-flash"
            and price["configuration_available_verified"] is True
            and price["input_nano_usd_per_token"] == 300
            and price["output_nano_usd_per_token"] == 1200
            and price["official_source"].startswith("https://api-docs.deepseek.com/")
            and 0 <= (now - datetime.fromisoformat(price["reviewed_utc"])).total_seconds() <= 86400
            and price["no_cache_peak_rates_cover_current_prices"] is True
        )
    except (KeyError, ValueError, TypeError, AttributeError):
        valid = False
    if not valid:
        raise EvalError("V18_LIVE_RECEIPTS_INVALID")
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip()
    if grant.get("git_head") != head or subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT):
        raise EvalError("V18_EXACT_CLEAN_COMMIT_REQUIRED")
    for name, expected in json.loads((BASE / "candidate.json").read_bytes())["files"].items():
        blob = subprocess.check_output(["git", "show", state["code_commit"] + ":" + name], cwd=ROOT)
        if hashlib.sha256(blob).hexdigest() != expected:
            raise EvalError("V18_CODE_COMMIT_MISMATCH")
    if os.environ.get("LECTURELENS_REAL_EVAL") != "1":
        raise EvalError("V18_LIVE_SWITCH_REQUIRED")
    return {
        "run_id": grant["run_id"],
        "git_head": head,
        "authorization_sha256": digest(authorization),
        "pricing_receipt_sha256": digest(pricing),
    }


class UsableProvider(BoundedTutorProvider):
    def validate(self, result):
        self.proposals.append(result)
        canonical = {e["evidence_id"] for e in self.authority.rows(self.scope)}

        def inspect(value):
            if isinstance(value, dict):
                if "evidence_id" in value and value["evidence_id"] not in canonical:
                    self.channel.ledger.block("REAL_EVAL_CITATION_FABRICATED")
                    raise EvalError("REAL_EVAL_CITATION_FABRICATED")
                for child in value.values():
                    inspect(child)
            elif isinstance(value, list):
                for child in value:
                    inspect(child)

        inspect(result["arguments"])
        if result["name"] == "search_tutor_evidence":
            Search.model_validate(result["arguments"])
        else:
            UsableProposal.model_validate(result["arguments"])

    def decide(self, messages, schemas, timeout):
        result = self.channel.request(
            messages, schemas, timeout, max_tokens=OUTPUT_TOKENS, validate=self.validate, purpose="tutor"
        )
        if self.channel.turn_calls[-1].get("returned_model") != "deepseek-flash":
            self.channel.ledger.block("REAL_EVAL_MODEL_MISMATCH")
            raise EvalError("REAL_EVAL_MODEL_MISMATCH")
        return result


class SmokeRuntime(UsableTutorRuntime):
    @staticmethod
    def reserve_call(conn, session, turn, amount, *, repair=False):
        if turn["model_calls"] >= (4 if repair else 3):
            raise EvalError("V18_SMOKE_TURN_REQUEST_LIMIT")
        return UsableTutorRuntime.reserve_call(conn, session, turn, amount, repair=repair)


def execute(output, *, live=False, authorization=None, pricing=None, fault="none"):
    state = verify_inputs()
    admission = live_admission(state, authorization, pricing) if live else None
    if live and fault != "none":
        raise EvalError("V18_LIVE_FAULT_FORBIDDEN")
    if not live and os.environ.get("LECTURELENS_PREFLIGHT_GUARDED") != "1":
        raise EvalError("V18_MOCK_SOCKET_FENCE_REQUIRED")
    output = Path(output).resolve()
    if not output.is_relative_to(ROOT / ".data"):
        raise EvalError("V18_PRIVATE_OUTPUT_REQUIRED")
    output.mkdir(mode=0o700, parents=True, exist_ok=False)
    if live:
        claims = ROOT / ".data/tutor-v18-authorizations"
        claims.mkdir(mode=0o700, exist_ok=True)
        private_file(claims / (admission["run_id"] + ".used"), json.dumps(admission).encode())
        directory = os.open(claims.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    schema = "v18_diag_" + uuid.uuid4().hex
    with psycopg.connect(TEST_DSN) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(schema)))
    isolated = make_conninfo(TEST_DSN, options=f"-csearch_path={schema},public")
    private_file(
        output / "owner.json",
        json.dumps(
            {
                "schema": schema,
                "live": live,
                "retention": "KEEP_LIVE_SCHEMA" if live else "DROP_OWN_MOCK_SCHEMA",
            }
        ).encode(),
    )
    runtime, packet = None, None
    outcomes = []
    try:
        packet = json.loads((BASE / "sample-candidate.json").read_bytes())
        snapshot = LessonAuthority(
            json.loads((ROOT / "eval/tutor-v14-fresh-v1/snapshot.json").read_bytes())
        ).snapshot
        authority = RelevantSnapshotAuthority(snapshot)
        mock = UsableMock()

        def send(request):
            wire = json.loads(request.content)
            result = mock.decide(wire["messages"], wire["tools"], 20)
            body = json.loads(wire["messages"][-1]["content"])
            if (
                fault in {"format_once", "format_twice"}
                and result["name"] == "finish_tutor_turn"
                and (fault == "format_twice" or "rejected_blocks" not in body)
                and not body["socratic"]
            ):
                source = body["evidence"][0]
                result["arguments"] = {
                    "outcome": "answered",
                    "blocks": [
                        {
                            "kind": "explanation",
                            "evidence_id": source["evidence_id"],
                            "quote": source["text"][:80],
                            "text": "x" * 901,
                        }
                    ],
                }
            if fault == "support_invalid" and result["name"] == "finish_tutor_turn":
                result["arguments"] = {
                    "outcome": "answered",
                    "blocks": [
                        {
                            "kind": "source",
                            "evidence_id": json.loads(wire["messages"][-1]["content"])["evidence"][0][
                                "evidence_id"
                            ],
                            "text": "Unobserved new assertion.",
                        }
                    ],
                }
            if fault == "fabricated_id" and result["name"] == "finish_tutor_turn":
                result = {
                    "name": "finish_tutor_turn",
                    "arguments": {
                        "outcome": "answered",
                        "blocks": [{"kind": "source", "evidence_id": "foreign", "text": "Not observed"}],
                    },
                }
            response = {
                "id": "synthetic-request",
                "model": "other-model" if fault == "model_mismatch" else "deepseek-flash",
                "usage": {"prompt_tokens": 100, "completion_tokens": 60},
                "choices": [
                    {
                        "finish_reason": "tool_calls",
                        "message": {
                            "tool_calls": [
                                {
                                    "type": "function",
                                    "function": {
                                        "name": result["name"],
                                        "arguments": json.dumps(result["arguments"]),
                                    },
                                }
                            ]
                        },
                    }
                ],
            }
            if fault == "unknown_usage":
                response.pop("usage")
            return httpx.Response(
                200, content=b"not-json" if fault == "malformed" else json.dumps(response).encode()
            )

        transport = httpx.HTTPTransport(retries=0, trust_env=False) if live else httpx.MockTransport(send)
        captured = CaptureTransport(transport, output / "wire")
        policy = UsablePolicy(
            live=live,
            max_calls=1 if fault == "budget" else MAX_REQUESTS,
            max_nano_usd=MAX_NANO_USD,
            candidate_sha256=state["candidate_sha256"],
        )
        ledger = Ledger(
            isolated,
            output / "ledger.jsonl",
            admission["run_id"] if live else "v18-mock-" + uuid.uuid4().hex,
            policy,
        )
        ledger.install()
        channel = ObservedChannel(
            ledger, records=output / "calls.jsonl", transport=DecodedMetadataTransport(captured)
        )
        provider = UsableProvider(channel, authority)
        runtime = SmokeRuntime(UsableStore(isolated), authority, provider)
        runtime.initialize()
        outcomes, global_stop, published_scopes = [], None, []
        for session in packet["sessions"]:
            scope = {"owner_id": 811016, "course_id": session["dialogue_id"], "revision": 1}
            if not global_stop:
                authority.register(scope, session["course_id"])
                scope["session_id"] = runtime.command(
                    Command(**scope, operation="CREATE", request_key="once")
                )["session"]["session_id"]
                published_scopes.append(scope.copy())
            closed = False
            for n, task in enumerate(session["turns"], 1):
                if global_stop or closed:
                    outcomes.append(
                        {
                            "turn_key": task["turn_key"],
                            "status": "SKIPPED",
                            "reason": global_stop or "SESSION_CLOSED",
                        }
                    )
                    continue
                channel.turn_key, channel.turn_calls, provider.scope = task["turn_key"], [], scope
                runtime.command(
                    Command(
                        **scope,
                        operation="TURN",
                        client_turn_id=f"t{n}",
                        text=task["text"],
                        socratic=task["socratic"],
                    )
                )
                runtime.execute(runtime.store.candidates()[0])
                row = runtime.command(Command(**scope, operation="GET"))["turns"][-1]
                outcomes.append({"turn_key": task["turn_key"], **row})
                if row["status"] != "completed":
                    closed = True
                    code = row["error_code"] or "UNKNOWN_FAILURE"
                    global_stop = code
        summary = {
            **state,
            "mode": "live" if live else "mock",
            "source_scope": "DEVELOPMENT_EXPOSED_KNOWN_COURSE"
            if live
            else "FROZEN_DEVELOPMENT_SMOKE_PACKET_MOCK_MECHANICS_NOT_QUALITY",
            "expected": 3,
            "completed": sum(r["status"] == "completed" for r in outcomes),
            "failed": sum(r["status"] == "failed" for r in outcomes),
            "skipped": sum(r["status"] == "SKIPPED" for r in outcomes),
            "sent_requests": captured.calls,
            "ledger": ledger.check(),
            "global_stop": global_stop,
            "quality": "NOT_RUN",
            "real_model_calls": captured.calls if live else 0,
            "embedding_calls": 0,
            "reviewer_calls": 0,
            "cost_usd": "UNKNOWN_SUPPLIER_INVOICE" if live else "0",
            "ledger_amounts": "CONSERVATIVE_LOCAL_NOT_INVOICE" if live else "SIMULATED_NOT_CHARGES",
            "admission": admission,
        }
        private_file(output / "outcomes.json", json.dumps(outcomes, indent=2, default=str).encode())
        private_file(output / "summary.json", json.dumps(summary, indent=2).encode())
        with runtime.store.connect() as conn:
            turns = conn.execute("SELECT * FROM tutor_turn ORDER BY created_at,ordinal").fetchall()
            sessions = conn.execute("SELECT * FROM tutor_session ORDER BY created_at").fetchall()
        private_file(
            output / "runtime.json",
            json.dumps(
                {"turns": turns, "sessions": sessions, "scopes": published_scopes}, indent=2, default=str
            ).encode(),
        )
        private_file(
            output / "execution.json",
            json.dumps(
                {
                    "git_head": subprocess.check_output(
                        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
                    ).strip(),
                    "candidate": state,
                    "live": live,
                    "fault": fault,
                    "entry": "scripts/dev/run_tutor_smoke_v18.py",
                },
                indent=2,
            ).encode(),
        )
        assert len(outcomes) == 3
        return summary
    finally:
        if runtime:
            runtime.close()
        # Preserve state even after an engineering exception. Unknown execution
        # positions cannot be relabelled as model-semantic failures or successes.
        if not (output / "runtime.json").exists():
            with psycopg.connect(isolated) as conn:
                tables = conn.execute(
                    "SELECT tablename FROM pg_tables WHERE schemaname=current_schema()"
                ).fetchall()
                exported = {}
                for (table,) in tables:
                    if table in {"tutor_turn", "tutor_session", "p8_tutor_real_run", "p8_tutor_real_event"}:
                        exported[table] = conn.execute(
                            sql.SQL("SELECT * FROM {}").format(sql.Identifier(table))
                        ).fetchall()
            private_file(
                output / "runtime.json",
                json.dumps(
                    {"execution_stop": "ENGINEERING_FAILURE_OR_UNOBSERVED", "tables": exported}, default=str
                ).encode(),
            )
        if packet and not (output / "outcomes.json").exists():
            observed = {row["turn_key"] for row in outcomes}
            outcomes.extend(
                {
                    "turn_key": t["turn_key"],
                    "status": "UNOBSERVED",
                    "reason": "ENGINEERING_STOP_NOT_SEMANTIC_FAILURE",
                }
                for s in packet["sessions"]
                for t in s["turns"]
                if t["turn_key"] not in observed
            )
            private_file(output / "outcomes.json", json.dumps(outcomes, indent=2, default=str).encode())
        if not live:
            with psycopg.connect(TEST_DSN) as conn:
                conn.execute(sql.SQL("DROP SCHEMA {} CASCADE").format(sql.Identifier(schema)))
