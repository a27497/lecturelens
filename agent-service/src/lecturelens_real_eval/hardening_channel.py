"""P7 hardening channel; reuse historical dispatch/durability without changing its freeze.

Prices are conservative integer nano-USD per token, ignoring cache discounts.
The new ledger keeps the original lock/fsync/PG consistency and unknown-outcome rules.
"""

import hashlib
import json
import os
import re
import uuid
from dataclasses import dataclass

from .channel import ROUTE, EvalError
from .channel import Channel as HistoricalChannel
from .channel import Ledger as HistoricalLedger

GENERATOR_MODEL = "deepseek-flash"
REVIEWER_MODEL = "deepseek-v4-pro"
PRICES = {GENERATOR_MODEL: (300, 1200), REVIEWER_MODEL: (1740, 3960)}
DEFAULT_LEDGER = "/home/dev/lecturelens-eval/deepseek-20261027/ledger-p7-hardening-20261027.jsonl"


@dataclass(frozen=True)
class RealPolicy:
    live: bool = False
    allowed_route: str = ROUTE
    model: str = GENERATOR_MODEL
    reviewer_model: str = REVIEWER_MODEL
    thinking: str = "disabled"
    max_tokens: int = 1200
    max_calls: int = 220
    max_nano_usd: int = 600_000_000
    candidate_sha256: str = ""

    def validate(self):
        if self.live and os.environ.get("LECTURELENS_REAL_EVAL") != "1":
            raise EvalError("REAL_EVAL_SWITCH_REQUIRED")
        if (
            type(self.live) is not bool
            or (self.candidate_sha256 and not re.fullmatch(r"[a-f0-9]{64}", self.candidate_sha256))
            or self.allowed_route != ROUTE
            or self.model != GENERATOR_MODEL
            or self.reviewer_model != REVIEWER_MODEL
            or self.thinking != "disabled"
            or type(self.max_tokens) is not int
            or not 1 <= self.max_tokens <= 1200
            or type(self.max_calls) is not int
            or not 1 <= self.max_calls <= 220
            or type(self.max_nano_usd) is not int
            or not 1 <= self.max_nano_usd <= 600_000_000
        ):
            raise EvalError("REAL_EVAL_POLICY_INVALID")


def routed_model(policy, schemas, model=None):
    policy.validate()
    if not schemas or any(s.get("type") != "function" for s in schemas):
        raise EvalError("REAL_EVAL_MODEL_ROUTING")
    names = {s.get("function", {}).get("name") for s in schemas}
    if names == {"review_card_sources"}:
        expected = policy.reviewer_model
    elif names and names <= {"search_card_evidence", "create_evidence_cards", "stop_cards"}:
        expected = policy.model
    else:
        raise EvalError("REAL_EVAL_MODEL_ROUTING")
    if model is not None and model != expected:
        raise EvalError("REAL_EVAL_MODEL_ROUTING")
    return expected


class Ledger(HistoricalLedger):
    def reserve(self, raw, max_tokens):
        self.policy.validate()
        if (
            not isinstance(raw, bytes)
            or len(raw) > 65536
            or type(max_tokens) is not int
            or not 1 <= max_tokens <= self.policy.max_tokens
        ):
            raise EvalError("REAL_EVAL_REQUEST_INVALID")
        try:
            payload = json.loads(raw)
            model = routed_model(self.policy, payload["tools"], payload["model"])
            if payload["max_tokens"] != max_tokens:
                raise ValueError()
        except Exception:  # noqa: BLE001 -- malformed request details never escape
            raise EvalError("REAL_EVAL_REQUEST_INVALID") from None
        input_price, output_price = PRICES[model]
        error = None
        with self.locked() as (conn, file):
            records, blocked = self._check(conn, file)
            latest = {r["call_id"]: r for r in records}
            amount = len(raw) * input_price + max_tokens * output_price
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
                    "UPDATE p7_real_run SET blocked=COALESCE(blocked,%s) WHERE run_id=%s",
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
                        "model": model,
                        "input_bytes": len(raw),
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
            input_price, output_price = PRICES[reservation["model"]]
            actual = (
                usage["prompt_tokens"] * input_price + usage["completion_tokens"] * output_price
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
                    "UPDATE p7_real_run SET blocked='REAL_EVAL_USAGE_EXCEEDED' WHERE run_id=%s",
                    (self.run_id,),
                )
        self.check()
        if over:
            raise EvalError("REAL_EVAL_USAGE_EXCEEDED")


class _DispatchPolicy:
    """Per-request model view; validation always checks the entire immutable policy."""

    def __init__(self, policy, model):
        self.original, self.model = policy, model

    def __getattr__(self, name):
        return getattr(self.original, name)


class Channel(HistoricalChannel):
    def request(self, messages, schemas, timeout=20, max_tokens=1200, *, validate=None, model=None):
        selected = routed_model(self.policy, schemas, model)
        # A fresh dispatch object avoids mutating shared policy between generation/review.
        dispatch = HistoricalChannel(self.ledger, transport=self.transport)
        dispatch.policy = _DispatchPolicy(self.policy, selected)
        try:
            return dispatch.request(messages, schemas, timeout, max_tokens, validate=validate)
        finally:
            self.dropped_tool_calls += dispatch.dropped_tool_calls
