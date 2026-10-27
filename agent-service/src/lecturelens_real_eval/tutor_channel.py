"""P8 two-model fail-closed paid egress with append-only, mirrored accounting. Never auto-installed.

Amounts are integer nano-USD. Flash costs 300 input / 1200 output per token,
Pro costs 1740 input / 3960 output; model/tool routing is checked at reservation.
cache discounts are deliberately ignored. Unknown outcomes consume the reservation.
The two durable stores cannot commit atomically: any divergence blocks dispatch,
including a crash after the file fsync but before the PG commit. No auto-repair.
"""

import fcntl
import hashlib
import json
import os
import re
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from decimal import Decimal
from pathlib import Path

import httpx
import psycopg
from psycopg.conninfo import conninfo_to_dict, make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from lecturelens_agent.study.store import StudyError

ROUTE = "https://api.deepseek.com"
MODEL = "deepseek-flash"
DEFAULT_LEDGER = "/home/dev/lecturelens-eval/deepseek-20261027/ledger-p8-tutor-20261027.jsonl"
SCHEMA = """
CREATE TABLE IF NOT EXISTS p8_tutor_real_run (
 run_id text PRIMARY KEY, policy jsonb NOT NULL, blocked text
);
CREATE TABLE IF NOT EXISTS p8_tutor_real_event (
 run_id text REFERENCES p8_tutor_real_run, sequence integer NOT NULL, record jsonb NOT NULL,
 PRIMARY KEY(run_id,sequence)
);
"""


class EvalError(StudyError):
    """Only constant codes cross the boundary; never a provider body or exception."""


@dataclass(frozen=True)
class TutorPolicy:
    live: bool = False
    allowed_route: str = ROUTE
    model: str = MODEL
    thinking: str = "disabled"
    max_tokens: int = 1200
    max_calls: int = 400
    max_nano_usd: int = 700_000_000
    candidate_sha256: str = ""

    def validate(self):
        if self.live and os.environ.get("LECTURELENS_REAL_EVAL") != "1":
            raise EvalError("REAL_EVAL_SWITCH_REQUIRED")
        if (
            type(self.live) is not bool
            or (self.candidate_sha256 and not re.fullmatch(r"[a-f0-9]{64}", self.candidate_sha256))
            or self.allowed_route != ROUTE
            or self.model != MODEL
            or self.thinking != "disabled"
            or type(self.max_tokens) is not int
            or not 1 <= self.max_tokens <= 1200
            or type(self.max_calls) is not int
            or not 1 <= self.max_calls <= 400
            or type(self.max_nano_usd) is not int
            or not 1 <= self.max_nano_usd <= 700_000_000
        ):
            raise EvalError("REAL_EVAL_POLICY_INVALID")


def isolated_dsn(dsn):
    try:
        c = conninfo_to_dict(dsn)
        valid = (
            c.get("host") == "127.0.0.1"
            and c.get("hostaddr") in (None, "127.0.0.1")
            and not c.get("service")
            and c.get("dbname") == "lecturelens_agent_acceptance"
            and 20_000 <= int(c.get("port", "0")) <= 32_767
        )
        if valid:
            # Explicit hostaddr overrides inherited PGHOSTADDR; options cannot route libpq.
            return make_conninfo(
                dsn, hostaddr="127.0.0.1", options=c.get("options", "") + " -csynchronous_commit=on"
            )
    except Exception:  # noqa: BLE001 -- constant redacted boundary, no raw exception escapes
        pass
    raise EvalError("REAL_EVAL_ISOLATED_DATABASE_REQUIRED") from None


def encode(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()


class Ledger:
    def __init__(self, dsn, path, run_id, policy):
        policy.validate()
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{0,95}", run_id):
            raise EvalError("REAL_EVAL_RUN_ID_INVALID")
        self.dsn, self.path, self.run_id, self.policy = (
            isolated_dsn(dsn),
            Path(path).resolve(),
            run_id,
            policy,
        )

    def connect(self):
        return psycopg.connect(self.dsn, row_factory=dict_row)

    @contextmanager
    def locked(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Never truncate. Exclusive file lock serializes all writers across runs.
        fd = os.open(self.path, os.O_RDWR | os.O_CREAT | os.O_APPEND | os.O_NOFOLLOW, 0o600)
        with os.fdopen(fd, "a+b") as file:
            fcntl.flock(file, fcntl.LOCK_EX)
            with self.connect() as conn:
                conn.execute("SELECT pg_advisory_xact_lock(78281027)")
                yield conn, file

    def install(self):
        with self.locked() as (conn, file):
            if conn.execute("SHOW fsync").fetchone()["fsync"] != "on":
                raise EvalError("REAL_EVAL_DURABILITY_REQUIRED")
            conn.execute(SCHEMA)
            # A run is single-use. Recovery/checking never sends an unknown request again.
            if conn.execute("SELECT 1 FROM p8_tutor_real_run WHERE run_id=%s", (self.run_id,)).fetchone():
                raise EvalError("REAL_EVAL_RUN_ALREADY_EXISTS")
            if self._file_records(file):
                raise EvalError("REAL_EVAL_LEDGER_MISMATCH")
            conn.execute(
                "INSERT INTO p8_tutor_real_run VALUES (%s,%s,NULL)",
                (self.run_id, Jsonb({**asdict(self.policy), "ledger": str(self.path)})),
            )

    def _file_records(self, file):
        file.seek(0)
        try:
            lines = list(file)
            if any(not line.endswith(b"\n") for line in lines):
                raise ValueError()
            rows = [json.loads(line) for line in lines]
            if any(not isinstance(row, dict) or "run_id" not in row for row in rows):
                raise ValueError()
            return [row for row in rows if row["run_id"] == self.run_id]
        except Exception:  # noqa: BLE001 -- constant redacted boundary, no raw exception escapes
            raise EvalError("REAL_EVAL_LEDGER_MISMATCH") from None

    def _check(self, conn, file):
        row = conn.execute(
            "SELECT * FROM p8_tutor_real_run WHERE run_id=%s FOR UPDATE", (self.run_id,)
        ).fetchone()
        if not row or row["policy"] != {**asdict(self.policy), "ledger": str(self.path)}:
            raise EvalError("REAL_EVAL_LEDGER_POLICY_MISMATCH")
        records = [
            r["record"]
            for r in conn.execute(
                "SELECT record FROM p8_tutor_real_event WHERE run_id=%s ORDER BY sequence", (self.run_id,)
            )
        ]
        if records != self._file_records(file):
            raise EvalError("REAL_EVAL_LEDGER_MISMATCH")
        return records, row["blocked"]

    def check(self):
        with self.locked() as (conn, file):
            records, blocked = self._check(conn, file)
            latest = {r["call_id"]: r for r in records}
            return {
                "calls": len(latest),
                "nano_usd": sum(r["charged_nano_usd"] for r in latest.values()),
                "pending": sum(r["state"] == "reserved" for r in latest.values()),
                "blocked": blocked,
            }

    def _append(self, conn, file, records, record):
        record = {"run_id": self.run_id, "sequence": len(records) + 1, **record}
        file.write(encode(record) + b"\n")
        file.flush()
        os.fsync(file.fileno())
        conn.execute(
            "INSERT INTO p8_tutor_real_event VALUES (%s,%s,%s)",
            (self.run_id, record["sequence"], Jsonb(record)),
        )
        return record

    def block(self, code):
        with self.connect() as conn:
            conn.execute(
                "UPDATE p8_tutor_real_run SET blocked=COALESCE(blocked,%s) WHERE run_id=%s",
                (code, self.run_id),
            )

    def reserve(self, raw, max_tokens):
        self.policy.validate()
        if (
            not isinstance(raw, bytes)
            or len(raw) > 65536
            or type(max_tokens) is not int
            or not 1 <= max_tokens <= self.policy.max_tokens
        ):
            raise EvalError("REAL_EVAL_REQUEST_INVALID")
        error = None
        with self.locked() as (conn, file):
            records, blocked = self._check(conn, file)
            latest = {r["call_id"]: r for r in records}
            try:
                payload = json.loads(raw)
                model = payload["model"]
                names = {s["function"]["name"] for s in payload["tools"]}
                if model == MODEL and names and names <= {"search_tutor_evidence", "finish_tutor_turn"}:
                    input_rate, output_rate = 300, 1200
                elif model == "deepseek-v4-pro" and names == {"review_tutor_turn"}:
                    input_rate, output_rate = 1740, 3960
                else:
                    raise ValueError()
            except Exception:  # noqa: BLE001 -- route errors never expose request bodies
                raise EvalError("REAL_EVAL_ROUTE_INVALID") from None
            amount = len(raw) * input_rate + max_tokens * output_rate
            if blocked:
                error = "REAL_EVAL_RUN_STOPPED"
            elif any(r["state"] == "reserved" for r in latest.values()):
                error = "REAL_EVAL_UNKNOWN_OUTCOME"
            elif (
                len(latest) >= self.policy.max_calls
                or sum(r["charged_nano_usd"] for r in latest.values()) + amount > self.policy.max_nano_usd
            ):
                error = "REAL_EVAL_BUDGET_EXHAUSTED"
            if error:
                conn.execute(
                    "UPDATE p8_tutor_real_run SET blocked=COALESCE(blocked,%s) WHERE run_id=%s",
                    (error, self.run_id),
                )
            else:
                record = self._append(
                    conn,
                    file,
                    records,
                    {
                        "call_id": str(uuid.uuid4()),
                        "state": "reserved",
                        "input_bytes": len(raw),
                        "model": model,
                        "input_rate": input_rate,
                        "output_rate": output_rate,
                        "wire_sha256": hashlib.sha256(raw).hexdigest(),
                        "max_tokens": max_tokens,
                        "reserved_nano_usd": amount,
                        "charged_nano_usd": amount,
                        "usage": None,
                        "error": None,
                    },
                )
        if error:
            raise EvalError(error)
        # Both commits must be visible before handing control to the sender.
        self.check()
        return record

    def settle(self, reservation, usage=None, error=None):
        over = False
        with self.locked() as (conn, file):
            records, _ = self._check(conn, file)
            latest = {r["call_id"]: r for r in records}
            if latest.get(reservation["call_id"]) != reservation:
                raise EvalError("REAL_EVAL_SETTLEMENT_CONFLICT")
            actual = (
                usage["prompt_tokens"] * reservation["input_rate"]
                + usage["completion_tokens"] * reservation["output_rate"]
                if usage
                else 0
            )
            # Failed/unknown requests never receive a refund, even with partial usage.
            over = actual > reservation["reserved_nano_usd"]
            amount = max(actual, reservation["reserved_nano_usd"]) if error else actual
            self._append(
                conn,
                file,
                records,
                {
                    **{k: v for k, v in reservation.items() if k not in {"sequence", "run_id"}},
                    "state": "failed" if error else "settled",
                    "usage": usage,
                    "charged_nano_usd": amount,
                    "error": "REAL_EVAL_USAGE_EXCEEDED" if over else error,
                },
            )
            if over:
                conn.execute(
                    "UPDATE p8_tutor_real_run SET blocked='REAL_EVAL_USAGE_EXCEEDED' WHERE run_id=%s",
                    (self.run_id,),
                )
        self.check()
        if over:
            raise EvalError("REAL_EVAL_USAGE_EXCEEDED")


class Channel:
    def __init__(self, ledger, *, transport=None):
        ledger.policy.validate()
        self.ledger, self.policy = ledger, ledger.policy
        if not self.policy.live and transport is None:
            raise EvalError("REAL_EVAL_FAKE_TRANSPORT_REQUIRED")
        self.transport = transport
        self.dropped_tool_calls = 0

    def request(self, messages, schemas, timeout=20, max_tokens=1200, *, validate=None, purpose="tutor"):
        self.policy.validate()
        if (
            not 0 < timeout <= 20
            or type(max_tokens) is not int
            or not 1 <= max_tokens <= self.policy.max_tokens
        ):
            raise EvalError("REAL_EVAL_REQUEST_INVALID")
        allowed = (
            {"search_tutor_evidence", "finish_tutor_turn"} if purpose == "tutor" else {"review_tutor_turn"}
        )
        if purpose not in {"tutor", "review"}:
            raise EvalError("REAL_EVAL_ROUTE_INVALID")
        if not schemas or any(
            s.get("type") != "function" or s.get("function", {}).get("name") not in allowed for s in schemas
        ):
            raise EvalError("REAL_EVAL_REQUEST_INVALID")
        payload = {
            "model": MODEL if purpose == "tutor" else "deepseek-v4-pro",
            "messages": messages,
            "tools": schemas,
            "tool_choice": "required",
            "parallel_tool_calls": False,
            "temperature": 0,
            "thinking": {"type": "disabled"},
            "max_tokens": max_tokens,
        }
        raw = encode(payload)
        if len(raw) > 65536:
            raise EvalError("REAL_EVAL_BODY_LIMIT")
        reservation = self.ledger.reserve(raw, max_tokens)
        usage, result, code = None, None, None
        deadline = time.monotonic() + timeout
        # Credential lookup is inside the live-only branch; fake never reads it.
        key = os.environ.get("AGENT_LLM_API_KEY", "") if self.policy.live else ""
        try:
            if key and key.encode() in raw:
                raise ValueError()
            if self.policy.live and not key:
                raise ValueError()
            with httpx.Client(
                transport=self.transport, timeout=timeout, trust_env=False, follow_redirects=False
            ) as client:
                with client.stream(
                    "POST",
                    self.policy.allowed_route + "/chat/completions",
                    content=raw,
                    headers={
                        "Content-Type": "application/json",
                        **({"Authorization": "Bearer " + key} if key else {}),
                    },
                ) as response:
                    response.raise_for_status()
                    body = bytearray()
                    for piece in response.iter_bytes():
                        body.extend(piece)
                        if len(body) > 128 * 1024 or time.monotonic() >= deadline:
                            raise ValueError()
            if key and key.encode() in body:
                raise ValueError()
            data = json.loads(body)
            if key and key in json.dumps(data, ensure_ascii=False):
                raise ValueError()
            u = data["usage"]
            if any(type(u.get(k)) is not int or u[k] < 0 for k in ("prompt_tokens", "completion_tokens")):
                raise ValueError()
            usage = {k: u[k] for k in ("prompt_tokens", "completion_tokens")}
            choice = data["choices"][0]
            calls = choice["message"]["tool_calls"]
            # DeepSeek may ignore parallel_tool_calls=False. Every returned call must be
            # well-formed; only the first is executed and the rest are counted, never
            # re-requested (no retry, no extra paid call).
            if (
                choice.get("finish_reason") != "tool_calls"
                or not isinstance(calls, list)
                or not 1 <= len(calls) <= 8
                or any(c["type"] != "function" for c in calls)
            ):
                raise ValueError()
            names = {s["function"]["name"] for s in schemas}
            parsed = []
            for c in calls:
                if c["function"]["name"] not in names:
                    raise ValueError()
                # Strict JSON only. No ChatProvider.decide repair/re-ask path is reachable.
                a = json.loads(c["function"]["arguments"])
                if key and key in json.dumps(a, ensure_ascii=False):
                    raise ValueError()
                if not isinstance(a, dict):
                    raise ValueError()
                parsed.append((c["function"]["name"], a))
            self.dropped_tool_calls += len(parsed) - 1
            result = {
                "name": parsed[0][0],
                "arguments": parsed[0][1],
                "usage": usage,
                "dropped_tool_calls": len(parsed) - 1,
            }
            if validate:
                try:
                    # Ignored parallel calls are still proposals: an invented ID in
                    # one must stop the round even though only the first is executed.
                    for name, arguments in parsed:
                        validate({**result, "name": name, "arguments": arguments})
                except Exception:  # noqa: BLE001 -- validation details may contain provider output
                    code = "REAL_EVAL_PROTOCOL_FAILURE"
        except Exception:  # noqa: BLE001 -- constant redacted boundary, no raw exception escapes
            code = "REAL_EVAL_REQUEST_FAILED"
        # Raised outside the except block: no raw exception context/key survives.
        self.ledger.settle(reservation, usage, code)
        if code:
            raise EvalError(code) from None
        return result


def usd_to_nano(value):
    try:
        amount = Decimal(value) * 1_000_000_000
        if not amount.is_finite() or amount != amount.to_integral_value():
            raise ValueError()
        return int(amount)
    except Exception:  # noqa: BLE001 -- constant redacted boundary, no raw exception escapes
        raise EvalError("REAL_EVAL_POLICY_INVALID") from None
