"""Opt-in acceptance egress ledger; never installed by the application worker.

The ordinary Run token budget is unchanged. This separate, non-refundable CNY
reservation covers even unknown HTTP outcomes. Only an isolated acceptance DB
may install the singleton envelope; restarting a proxy cannot replenish it.
"""

import hashlib
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlsplit

from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.types.json import Jsonb

from .call_journal import request_fingerprint
from .learning_scope import public_status
from .store import StudyError, StudyStore
from .support_review import output_tokens

FROZEN_AGENT = "e34d8c596d74d4320ce6a224359190374520e4d3"
UPSTREAM = "https://api.deepseek.com/chat/completions"
MODEL = "deepseek-flash"
MAX_BODY = 65_536
INPUT_TOKEN_CEILING = 1_048_576
INPUT_MICRO_CNY = 2
OUTPUT_MICRO_CNY = 8
PRICE_SOURCE = "https://api-docs.deepseek.com/zh-cn/quick_start/pricing/"
NO_PROVIDER_CREDENTIAL = "provider-key-held-only-by-acceptance-egress"

SCHEMA = """
CREATE TABLE IF NOT EXISTS acceptance_cost_envelope (
    singleton boolean PRIMARY KEY DEFAULT true CHECK (singleton),
    policy jsonb NOT NULL, policy_hash text NOT NULL,
    reserved_micro_cny bigint NOT NULL DEFAULT 0 CHECK (reserved_micro_cny >= 0),
    calls integer NOT NULL DEFAULT 0 CHECK (calls >= 0), blocked_code text,
    practice_run text UNIQUE, feedback_run text UNIQUE
);
CREATE TABLE IF NOT EXISTS acceptance_cost_call (
    run_id text NOT NULL, operation_key text NOT NULL, purpose text NOT NULL,
    wire_sha256 text NOT NULL, input_bytes integer NOT NULL, output_tokens integer NOT NULL,
    reserved_micro_cny bigint NOT NULL, state text NOT NULL,
    provider_usage jsonb, usage_peak_upper_micro_cny bigint,
    provider_billed_micro_cny bigint, error_code text,
    created_at timestamptz NOT NULL DEFAULT now(), completed_at timestamptz,
    PRIMARY KEY (run_id,operation_key)
);
CREATE TABLE IF NOT EXISTS acceptance_cost_event (
    sequence bigserial PRIMARY KEY, code text NOT NULL, run_id text,
    created_at timestamptz NOT NULL DEFAULT now()
);
"""


class CostDenied(StudyError):
    pass


@dataclass(frozen=True)
class DispatchWindow:
    deadline: datetime
    monotonic_deadline: float

    @classmethod
    def until(cls, deadline, maximum):
        # Capture before commit so DB/adapter delays consume the same window.
        # A wall-clock rollback must not grant additional execution time.
        tick = time.monotonic()
        remaining = min(maximum, (deadline - datetime.now(timezone.utc)).total_seconds())
        return cls(deadline, tick + remaining)

    def remaining(self):
        return min(
            (self.deadline - datetime.now(timezone.utc)).total_seconds(),
            self.monotonic_deadline - time.monotonic(),
        )


def verify_frozen_agent(package=None):
    package = Path(package) if package is not None else Path(__file__).resolve().parent.parent
    manifest = json.loads(Path(__file__).with_name("acceptance_agent_manifest.json").read_text())
    if any(
        not (package / path).is_file()
        or hashlib.sha256((package / path).read_bytes()).hexdigest() != expected
        for path, expected in manifest.items()
    ):
        raise CostDenied("COST_AGENT_IDENTITY_CHANGED")
    return len(manifest)


@dataclass(frozen=True)
class CostPolicy:
    session_id: str
    verified_at: str
    expires_at: str
    # This aligned entry is offline-only. Historical live policy fields remain
    # parseable but cannot activate any real sender.
    mode: str = "fake"
    authorization_id: str | None = None
    budget_micro_cny: int = 20_000_000
    max_calls: int = 12
    candidate_sha: str = FROZEN_AGENT

    def validate(self):
        start = datetime.fromisoformat(self.verified_at)
        end = datetime.fromisoformat(self.expires_at)
        if (
            not start.tzinfo
            or not end.tzinfo
            or not start <= datetime.now(timezone.utc) < end <= start + timedelta(hours=24)
            or self.mode != "fake"
            or self.authorization_id is not None
            or self.candidate_sha != FROZEN_AGENT
            or type(self.budget_micro_cny) is not int
            or not 0 < self.budget_micro_cny <= 20_000_000
            or type(self.max_calls) is not int
            or not 0 < self.max_calls <= 12
        ):
            raise CostDenied("COST_POLICY_INVALID_OR_EXPIRED")


def worker_snapshot(_owner):
    # An isolated StudyStore uses this resolver instead of personal model
    # bindings. The worker's DB/key material cannot authenticate at DeepSeek.
    return {
        role: {
            "base_url": "https://api.deepseek.com",
            "model": MODEL,
            "version": 1,
            "connection_id": None,
            "name": "Isolated acceptance Flash",
            "credential": NO_PROVIDER_CREDENTIAL,
        }
        for role in ("decision", "review")
    }


def allowed_route(url):
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc.lower() in {"api.deepseek.com", "api.deepseek.com:443"}
        and parsed.path.rstrip("/") in {"", "/v1"}
        and not parsed.query
        and not parsed.fragment
    )


def routes(config):
    if not isinstance(config, dict) or set(config) != {"decision", "review"}:
        raise CostDenied("COST_ROUTE_REQUIRED")
    public = {}
    for role, route in config.items():
        if (
            not isinstance(route, dict)
            or route.get("model") != MODEL
            or not isinstance(route.get("base_url"), str)
            or not allowed_route(route.get("base_url", ""))
        ):
            raise CostDenied("COST_ROUTE_NOT_ALLOWED")
        if route.get("credential") != NO_PROVIDER_CREDENTIAL:
            raise CostDenied("COST_WORKER_CREDENTIAL_NOT_ISOLATED")
        public[role] = {k: route.get(k) for k in ("base_url", "model", "version", "connection_id")}
    return public


def wire_body(raw):
    if len(raw) > MAX_BODY:
        raise CostDenied("COST_INPUT_LIMIT")
    try:
        body = json.loads(raw)
        allowed = {
            "model",
            "messages",
            "tools",
            "tool_choice",
            "parallel_tool_calls",
            "temperature",
            "max_tokens",
            "thinking",
        }
        if (
            not isinstance(body, dict)
            or set(body) - allowed
            or body.get("model") != MODEL
            or body.get("thinking", {"type": "disabled"}) != {"type": "disabled"}
            or body.get("tool_choice") != "required"
            or body.get("parallel_tool_calls") is not False
            or type(body.get("temperature")) not in (int, float)
            or body.get("temperature") not in (0, 0.2)
            or type(body.get("max_tokens")) is not int
            or not 1 <= body["max_tokens"] <= 1200
            or not isinstance(body["messages"], list)
            or not 1 <= len(body["messages"]) <= 128
            or any(
                not isinstance(m, dict)
                or m.get("role") not in {"system", "user", "assistant", "tool"}
                or not (
                    isinstance(m.get("content"), str)
                    or (
                        m.get("role") == "assistant"
                        and m.get("content") is None
                        and isinstance(m.get("tool_calls"), list)
                    )
                )
                or set(m) - {"role", "content", "tool_calls", "tool_call_id"}
                for m in body["messages"]
            )
            or not isinstance(body["tools"], list)
            or not 1 <= len(body["tools"]) <= 16
            or any(t.get("type") != "function" or set(t) != {"type", "function"} for t in body["tools"])
        ):
            raise CostDenied("COST_REQUEST_NOT_ALLOWED")
        # The frozen client calls a local URL and so does not add the official
        # endpoint-specific flag. Only this flag is added before official egress.
        body["thinking"] = {"type": "disabled"}
        packed = json.dumps(body, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode()
    except (ValueError, KeyError, TypeError, AttributeError, RecursionError):
        raise CostDenied("COST_REQUEST_NOT_ALLOWED") from None
    if len(packed) > MAX_BODY:
        raise CostDenied("COST_INPUT_LIMIT")
    return body, packed


class CostLedger:
    def __init__(self, dsn):
        config = conninfo_to_dict(dsn)
        if (
            config.get("host") != "127.0.0.1"
            or config.get("hostaddr") not in (None, "127.0.0.1")
            or config.get("service")
            or config.get("dbname") not in {"lecturelens_agent_test", "lecturelens_agent_acceptance"}
            or not 20_000 <= int(config.get("port", "0")) < 32_768
        ):
            raise CostDenied("COST_ISOLATED_DATABASE_REQUIRED")
        # libpq can route using hostaddr/PGHOSTADDR instead of host. An explicit
        # address also overrides inherited environment/service defaults.
        self.store = StudyStore(
            make_conninfo(
                dsn,
                hostaddr="127.0.0.1",
                options=config.get("options", "") + " -csynchronous_commit=on",
            )
        )

    def install(self, policy):
        verify_frozen_agent()
        policy.validate()
        value = asdict(policy)
        fingerprint = hashlib.sha256(json.dumps(value, sort_keys=True).encode()).hexdigest()
        with self.store.connect() as conn:
            if conn.execute("SHOW fsync").fetchone()["fsync"] != "on":
                raise CostDenied("COST_DURABLE_DATABASE_REQUIRED")
            conn.execute("SELECT pg_advisory_xact_lock(7812259)")
            conn.execute(SCHEMA)
            conn.execute(
                "INSERT INTO acceptance_cost_envelope(policy,policy_hash) VALUES (%s,%s) ON CONFLICT DO NOTHING",
                (Jsonb(value), fingerprint),
            )
            prior = conn.execute("SELECT policy_hash FROM acceptance_cost_envelope").fetchone()
            if prior["policy_hash"] != fingerprint:
                raise CostDenied("COST_ENVELOPE_ALREADY_FROZEN")

    def snapshot(self):
        with self.store.connect() as conn:
            envelope = conn.execute("SELECT * FROM acceptance_cost_envelope").fetchone()
            calls = conn.execute("SELECT * FROM acceptance_cost_call ORDER BY created_at").fetchall()
            events = conn.execute(
                "SELECT code,run_id FROM acceptance_cost_event ORDER BY sequence"
            ).fetchall()
        return {"envelope": envelope, "calls": calls, "events": events}

    @staticmethod
    def _denial(conn, code, run_id):
        conn.execute("INSERT INTO acceptance_cost_event(code,run_id) VALUES (%s,%s)", (code, run_id))
        return CostDenied(code)

    def deny(self, code, run_id=None):
        with self.store.connect() as conn:
            error = self._denial(conn, code, run_id)
        raise error

    @staticmethod
    def _active(run):
        return (
            run
            and public_status(run["status"]) == "running"
            and run["model_mode"] == "real"
            and run["worker_token"]
            and run["deadline"]
            and run["deadline"] > datetime.now(timezone.utc)
        )

    def admit(self, run_id, purpose, raw):
        try:
            body, packed = wire_body(raw)
        except CostDenied as error:
            self.deny(error.code, run_id)
        with self.store.connect() as conn:
            envelope = conn.execute("SELECT * FROM acceptance_cost_envelope FOR UPDATE").fetchone()
            result = self._admit(conn, envelope, run_id, purpose, body, packed)
        if isinstance(result, CostDenied):
            raise result
        return result, packed

    def _admit(self, conn, envelope, run_id, purpose, body, packed):
        def reject(code):
            return self._denial(conn, code, run_id)

        if not envelope:
            return reject("COST_ENVELOPE_REQUIRED")
        policy = CostPolicy(**envelope["policy"])
        try:
            policy.validate()
        except CostDenied as error:
            return reject(error.code)
        if envelope["blocked_code"]:
            return reject("COST_CAMPAIGN_STOPPED")
        run = conn.execute("SELECT * FROM study_run WHERE run_id=%s FOR UPDATE", (run_id,)).fetchone()
        if not self._active(run) or run["session_id"] != policy.session_id:
            return reject("COST_RUN_NOT_ACTIVE_OR_ALLOWED")
        if not 1 <= run["model_calls"] <= 6 or run["tool_calls"] > 8 or run["reserved_tokens"] > 64000:
            return reject("COST_RUN_BUDGET_INVALID")
        try:
            routes(run["model_config"])
        except CostDenied as error:
            return reject(error.code)
        pending = conn.execute(
            "SELECT * FROM study_model_call WHERE run_id=%s AND response IS NULL AND error IS NULL",
            (run_id,),
        ).fetchall()
        if len(pending) != 1 or pending[0]["metadata"].get("purpose") != purpose:
            return reject("COST_JOURNAL_REQUIRED")
        call = pending[0]
        key = call["operation_key"]
        if conn.execute(
            "SELECT 1 FROM acceptance_cost_call WHERE run_id=%s AND operation_key=%s", (run_id, key)
        ).fetchone():
            return reject("COST_DUPLICATE_CALL")
        if conn.execute(
            "SELECT 1 FROM acceptance_cost_call WHERE state IN ('reserved','sent','unknown')"
        ).fetchone():
            return reject("COST_OUTCOME_PENDING_OR_UNKNOWN")
        if (
            conn.execute(
                "SELECT 1 FROM study_model_call m JOIN study_run r USING(run_id) WHERE r.session_id=%s AND m.error IS NOT NULL",
                (policy.session_id,),
            ).fetchone()
            or conn.execute(
                "SELECT 1 FROM study_event e JOIN study_run r USING(run_id) WHERE r.session_id=%s "
                "AND (e.event_type IN ('protocol_retry_scheduled','model_retry_scheduled') OR (e.event_type='quality_checked' AND e.payload->>'accepted'='false'))",
                (policy.session_id,),
            ).fetchone()
        ):
            conn.execute("UPDATE acceptance_cost_envelope SET blocked_code='COST_RETRY_NOT_ALLOWED'")
            return reject("COST_RETRY_NOT_ALLOWED")
        expected = (
            900
            if run.get("task_kind") == "feedback"
            else output_tokens(call["metadata"].get("review_stage"))
            if purpose == "review"
            else 900
        )
        if (
            purpose not in {"decision", "review"}
            or body["max_tokens"] != expected
            or (purpose == "decision" and body["max_tokens"] != 900)
            or call["request_fingerprint"]
            != request_fingerprint({"messages": body["messages"], "schemas": body["tools"]})
        ):
            return reject("COST_JOURNAL_INPUT_CHANGED")
        kind = "feedback_run" if run.get("task_kind") == "feedback" else "practice_run"
        if envelope[kind] not in (None, run_id):
            return reject("COST_EXTRA_RUN_NOT_ALLOWED")
        if kind == "feedback_run":
            attempt = conn.execute(
                "SELECT p.run_id FROM study_attempt a JOIN study_artifact p USING(artifact_id) WHERE a.attempt_id=%s",
                (run.get("source_attempt_id"),),
            ).fetchone()
            if not attempt or attempt["run_id"] != envelope["practice_run"]:
                return reject("COST_FEEDBACK_ATTEMPT_REQUIRED")
        charge = INPUT_TOKEN_CEILING * INPUT_MICRO_CNY + body["max_tokens"] * OUTPUT_MICRO_CNY
        run_calls = conn.execute(
            "SELECT count(*) AS n FROM acceptance_cost_call WHERE run_id=%s", (run_id,)
        ).fetchone()["n"]
        if envelope["calls"] >= policy.max_calls or run_calls >= 6:
            return reject("COST_CALL_LIMIT")
        if envelope["reserved_micro_cny"] + charge > policy.budget_micro_cny:
            return reject("COST_BUDGET_INSUFFICIENT")
        # Both the budget and idempotency claim commit BEFORE any upstream I/O.
        # Never refund a request, even when the provider reports a small usage.
        conn.execute(
            "UPDATE acceptance_cost_envelope SET reserved_micro_cny=reserved_micro_cny+%s,calls=calls+1,"
            "practice_run=CASE WHEN %s='practice_run' THEN %s ELSE practice_run END,"
            "feedback_run=CASE WHEN %s='feedback_run' THEN %s ELSE feedback_run END",
            (charge, kind, run_id, kind, run_id),
        )
        conn.execute(
            "INSERT INTO acceptance_cost_call(run_id,operation_key,purpose,wire_sha256,input_bytes,output_tokens,reserved_micro_cny,state) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,'reserved')",
            (
                run_id,
                key,
                purpose,
                hashlib.sha256(packed).hexdigest(),
                len(packed),
                body["max_tokens"],
                charge,
            ),
        )
        return {"run_id": run_id, "operation_key": key, "output_tokens": body["max_tokens"]}

    def dispatch(self, claim):
        with self.store.connect() as conn:
            envelope = conn.execute("SELECT * FROM acceptance_cost_envelope FOR UPDATE").fetchone()
            run = conn.execute(
                "SELECT * FROM study_run WHERE run_id=%s FOR UPDATE", (claim["run_id"],)
            ).fetchone()
            try:
                policy = CostPolicy(**envelope["policy"])
                policy.validate()
                valid_policy = True
            except CostDenied:
                valid_policy = False
            if envelope["blocked_code"] or not self._active(run) or not valid_policy:
                conn.execute("UPDATE acceptance_cost_envelope SET blocked_code='COST_CANCELLED_BEFORE_SEND'")
                error = self._denial(conn, "COST_CANCELLED_BEFORE_SEND", claim["run_id"])
            else:
                row = conn.execute(
                    "UPDATE acceptance_cost_call SET state='sent' WHERE run_id=%s AND operation_key=%s AND state='reserved' RETURNING run_id",
                    (claim["run_id"], claim["operation_key"]),
                ).fetchone()
                error = None if row else self._denial(conn, "COST_DUPLICATE_CALL", claim["run_id"])
                window = DispatchWindow.until(
                    min(run["deadline"], datetime.fromisoformat(policy.expires_at)),
                    20 if run.get("task_kind") == "feedback" else 90,
                )
        if error:
            raise error
        return window

    def expire_before_send(self, claim):
        # The gateway has not entered its sender. Keep the durable reservation
        # and stop the campaign; neither a restart nor a new key can refund it.
        code = "COST_DEADLINE_BEFORE_SEND"
        with self.store.connect() as conn:
            conn.execute("SELECT singleton FROM acceptance_cost_envelope FOR UPDATE")
            conn.execute(
                "UPDATE acceptance_cost_call SET state='not_sent',error_code=%s,completed_at=now() "
                "WHERE run_id=%s AND operation_key=%s AND state='sent'",
                (code, claim["run_id"], claim["operation_key"]),
            )
            conn.execute("UPDATE acceptance_cost_envelope SET blocked_code=%s", (code,))
            error = self._denial(conn, code, claim["run_id"])
        raise error

    def settle(self, claim, response, error_code=None):
        usage = None
        if isinstance(response, dict) and isinstance(response.get("usage"), dict):
            usage = {
                k: v
                for k, v in response["usage"].items()
                if k
                in {
                    "prompt_tokens",
                    "completion_tokens",
                    "total_tokens",
                    "prompt_cache_hit_tokens",
                    "prompt_cache_miss_tokens",
                }
                and type(v) is int
                and 0 <= v < 100_000_000
            }
        code = error_code
        if not code and (
            not usage
            or "prompt_tokens" not in usage
            or "completion_tokens" not in usage
            or response.get("model") != MODEL
        ):
            code = "COST_USAGE_OR_MODEL_UNKNOWN"
        if not code and (
            usage["prompt_tokens"] > INPUT_TOKEN_CEILING
            or usage["completion_tokens"] > claim["output_tokens"]
            or (
                "total_tokens" in usage
                and usage["total_tokens"] != usage["prompt_tokens"] + usage["completion_tokens"]
            )
        ):
            code = "COST_PROVIDER_BOUND_BREACH"
        with self.store.connect() as conn:
            conn.execute("SELECT singleton FROM acceptance_cost_envelope FOR UPDATE")
            row = conn.execute(
                "UPDATE acceptance_cost_call SET state=%s,provider_usage=%s,usage_peak_upper_micro_cny=%s,error_code=%s,completed_at=now() "
                "WHERE run_id=%s AND operation_key=%s AND state='sent' RETURNING run_id",
                (
                    "unknown" if code else "observed",
                    Jsonb(usage) if usage is not None else None,
                    None
                    if code
                    else usage["prompt_tokens"] * INPUT_MICRO_CNY
                    + usage["completion_tokens"] * OUTPUT_MICRO_CNY,
                    code,
                    claim["run_id"],
                    claim["operation_key"],
                ),
            ).fetchone()
            if not row:
                code = "COST_DUPLICATE_SETTLEMENT"
            if code:
                conn.execute("UPDATE acceptance_cost_envelope SET blocked_code=%s", (code,))
                self._denial(conn, code, claim["run_id"])
        if code:
            raise CostDenied(code)

    def cancel(self):
        with self.store.connect() as conn:
            conn.execute("SELECT singleton FROM acceptance_cost_envelope FOR UPDATE")
            conn.execute("UPDATE acceptance_cost_envelope SET blocked_code='COST_CAMPAIGN_CANCELLED'")
            self._denial(conn, "COST_CAMPAIGN_CANCELLED", None)
