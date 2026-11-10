"""E3 admission and accounting across two journals in the same isolated database."""

import json
import os
from datetime import datetime, timezone
from typing import Annotated, Literal

import psycopg
from psycopg import sql
from psycopg.conninfo import make_conninfo
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb
from pydantic import Field, model_validator

from lecturelens_agent.contracts import Contract
from lecturelens_agent.study.store import StudyError

from .flash_ledger import SHA256, TARGET_SCHEMA, FlashStore, Grant
from .flash_provider import RESERVE_NANO_USD, digest

PHASE_BUDGET = 10_000_000_000
PHASE_REQUESTS = 16
PHASE_EXPIRY = datetime(2026, 11, 12, 15, 59, 59, tzinfo=timezone.utc)
DATASET = "8d6db2bae205f262a86a6d4d3d42c59f953828b9751df04b3a5dcbbfd96eb4cf"
CASES = ("loop-1", "loop-2", "loop-3", "sql-1", "sql-2", "sql-3", "shell-1", "shell-2", "git-1", "git-2")
QUESTIONS = {
    "loop-1": "af61dfec78307afd88946a82b6a694af689e0d20a5bc1f0f4d169fb76ead1730",
    "loop-2": "bcedf2026fbd552db3c8fab6b7b5ad20d17569009823b18ff180249ef39d3843",
    "loop-3": "6418de4be00fd17cb6a6b6638cd591aac80d56071aed3ea3de5df87cbf58cbf1",
    "sql-1": "b18164950ea2eae276331b2190fcbf24c61b8f31bc10bc552ba45189fc295d41",
    "sql-2": "b6a11d9dc5a494e741109e19b7812df6bf5c4b865da13aa8d0a9d95b087305bc",
    "sql-3": "243dd6112f643a0277339b684b6cb74cbdd0f62212f63d2f718adea288cd7537",
    "shell-1": "ea6cc261c8fe86b1890bb7579662867317bf8eecdcf700d0983a63b370dcbb77",
    "shell-2": "b7b0eb64e242698b02302e9ed3c1f6493d6a9e8ecf004ee43dcc9655fb716d6a",
    "git-1": "a995815d46ba6d1becd6924c75ab7c2a01145ebf64df99d3001c982161aa3cd0",
    "git-2": "a2f5f5b56c29153db48e45c8ef4a5414ccd0949e01fdebf01acc8b14be82cccc",
}
SCHEMAS = {"initial": "tutor_e3_initial", "retest": "tutor_e3_retest"}
IRRECOVERABLE = {"TUTOR_FLASH_IDENTITY_CHANGED", "TUTOR_FLASH_USAGE_OVERRUN", "TUTOR_FLASH_GRANT_MISMATCH"}
PHASE_DDL = """
CREATE SCHEMA tutor_e3;
CREATE TABLE tutor_e3.phase (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 phase_id uuid NOT NULL DEFAULT gen_random_uuid(),
 mode text NOT NULL CHECK(mode IN ('real','offline-fake')),
 initial_closed_at timestamptz, repair_case text, repair_sha256 text
);
CREATE TABLE tutor_e3.run (
 kind text PRIMARY KEY CHECK(kind IN ('initial','retest')),
 grant_sha256 text NOT NULL UNIQUE, target_id uuid NOT NULL UNIQUE,
 grant_id text NOT NULL UNIQUE, commit_sha text NOT NULL UNIQUE, build_sha256 text NOT NULL,
 case_bindings jsonb NOT NULL
);
"""
WIRE_DDL = """
CREATE TABLE IF NOT EXISTS tutor_e3_wire (
 turn_id text PRIMARY KEY REFERENCES tutor_flash_call(turn_id),
 request bytea NOT NULL, started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 response bytea, http_status integer, response_complete boolean
);
"""


class PhaseReceipt(Contract):
    phase_id: Annotated[str, Field(pattern=r"^[0-9a-f-]{36}$")]
    kind: Literal["initial", "retest"]
    commit_sha: Annotated[str, Field(pattern=r"^[0-9a-f]{40}$")]
    case_ids: Annotated[list[str], Field(min_length=1, max_length=10)]
    required: list[list[list[SHA256]]]
    grant: Grant

    @model_validator(mode="after")
    def bounds(self):
        if len(self.case_ids) != self.grant.request_limit or len(self.required) != len(self.case_ids):
            raise ValueError("E3 receipt positions do not match")
        if self.grant.mode == "real":
            if self.grant.dataset_sha256 != DATASET or self.grant.expires_at > PHASE_EXPIRY:
                raise ValueError("E3 frozen dataset or expiry mismatch")
            turns = (turn for plan in self.grant.sessions for turn in plan.turns)
            if any(
                QUESTIONS.get(key)
                != digest(json.dumps([turn.text, turn.socratic], ensure_ascii=False).encode())
                for key, turn in zip(self.case_ids, turns, strict=True)
            ):
                raise ValueError("E3 frozen question mismatch")
            if self.kind == "initial" and tuple(self.case_ids) != CASES:
                raise ValueError("E3 initial positions differ from the freeze")
            if self.kind == "retest":
                expected = [case for case in CASES[:6] if case in self.case_ids]
                if expected != self.case_ids or any(
                    int(case[-1]) > 1 and case[:-1] + str(int(case[-1]) - 1) not in expected
                    for case in expected
                ):
                    raise ValueError("E3 retest must use ordered development dialogue prefixes")
        if self.kind == "retest" and len(self.case_ids) > 6:
            raise ValueError("E3 retest request limit")
        return self

    def case_bindings(self):
        plans = (plan for plan in self.grant.sessions for _ in plan.turns)
        return {
            key: digest(json.dumps([plan.scope, sorted(plan.evidence_sha256), groups]).encode())
            for key, plan, groups in zip(self.case_ids, plans, self.required, strict=True)
        }


def provision_phase(dsn, mode):
    # Fresh only. The caller must keep the single live phase identity and its WAL.
    with psycopg.connect(dsn) as conn:
        conn.execute(PHASE_DDL)
        (phase_id,) = conn.execute(
            "INSERT INTO tutor_e3.phase(mode) VALUES (%s) RETURNING phase_id", (mode,)
        ).fetchone()
        return str(phase_id)


def run_dsn(dsn, kind):
    return make_conninfo(dsn, options=f"-csearch_path={SCHEMAS[kind]},public")


def provision_target(dsn, kind):
    with psycopg.connect(dsn) as conn:
        conn.execute(sql.SQL("CREATE SCHEMA {}").format(sql.Identifier(SCHEMAS[kind])))
    with psycopg.connect(run_dsn(dsn, kind)) as conn:
        conn.execute(TARGET_SCHEMA)
        (target,) = conn.execute(
            "INSERT INTO tutor_flash_target DEFAULT VALUES RETURNING target_id"
        ).fetchone()
        return str(target)


def phase_rows(conn):
    return [
        row
        for run in conn.execute("SELECT kind FROM tutor_e3.run ORDER BY kind").fetchall()
        for row in conn.execute(
            sql.SQL("SELECT *, %s AS run_kind FROM {}.tutor_flash_call ORDER BY slot").format(
                sql.Identifier(SCHEMAS[run["kind"]])
            ),
            (run["kind"],),
        ).fetchall()
    ]


def phase_usage(conn):
    calls = phase_rows(conn)
    return {
        "reservations": len(calls),
        "settled_nano_usd": sum(row["charged_nano_usd"] or 0 for row in calls),
        "unsettled_nano_usd": sum(
            row["reserved_nano_usd"] for row in calls if row["charged_nano_usd"] is None
        ),
    }


def lock_phase(conn, receipt):
    row = conn.execute("SELECT * FROM tutor_e3.phase WHERE singleton FOR UPDATE").fetchone()
    if not row or (str(row["phase_id"]), row["mode"]) != (receipt.phase_id, receipt.grant.mode):
        raise StudyError("TUTOR_E3_PHASE_MISMATCH", 403)
    return row


def approve_retest(dsn, initial_receipt, development_case, repair_sha256):
    if (
        initial_receipt.kind != "initial"
        or development_case not in CASES[:6]
        or development_case not in initial_receipt.case_ids
        or len(repair_sha256) != 64
        or any(c not in "0123456789abcdef" for c in repair_sha256)
    ):
        raise StudyError("TUTOR_E3_REPAIR_EVIDENCE_REQUIRED", 403)
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        phase = lock_phase(conn, initial_receipt)
        run = conn.execute("SELECT grant_sha256 FROM tutor_e3.run WHERE kind='initial'").fetchone()
        calls = phase_rows(conn)
        development_slot = initial_receipt.case_ids.index(development_case) + 1
        if (
            phase["initial_closed_at"]
            or not run
            or run["grant_sha256"] != digest(initial_receipt.model_dump_json().encode())
            or not any(row["slot"] == development_slot and row["run_kind"] == "initial" for row in calls)
            or any(row["charged_nano_usd"] is None or row["error_code"] in IRRECOVERABLE for row in calls)
            or any(row["published_at"] is None and row["error_code"] is None for row in calls)
        ):
            raise StudyError("TUTOR_E3_RETEST_DENIED", 403)
        # This freezes the first run before another candidate may send.
        conn.execute(
            """UPDATE tutor_e3.phase SET initial_closed_at=clock_timestamp(),repair_case=%s,repair_sha256=%s
               WHERE singleton""",
            (development_case, repair_sha256),
        )


class PhaseFlashStore(FlashStore):
    def __init__(self, dsn, receipt, *, live_anchor=None):
        if (receipt.grant.mode == "real") != (live_anchor is not None):
            raise StudyError("TUTOR_E3_LIVE_ANCHOR_REQUIRED", 403)
        self.dispatch_dir = live_anchor.parent / "live-dispatch" if live_anchor is not None else None
        self.receipt = receipt
        self.receipt_hash = digest(receipt.model_dump_json().encode())
        super().__init__(run_dsn(dsn, receipt.kind), receipt.grant)

    def initialize(self):
        with self.connect() as conn:
            phase = lock_phase(conn, self.receipt)
            if (
                conn.execute("SELECT current_schema() AS name").fetchone()["name"]
                != SCHEMAS[self.receipt.kind]
            ):
                raise StudyError("TUTOR_E3_WRONG_RUN_SCHEMA", 403)
            target = conn.execute("SELECT target_id::text FROM tutor_flash_target WHERE singleton").fetchone()
            if not target or target["target_id"] != self.grant.target_id:
                raise StudyError("TUTOR_FLASH_WRONG_DATABASE", 403)
            row = conn.execute("SELECT * FROM tutor_e3.run WHERE kind=%s", (self.receipt.kind,)).fetchone()
            if row:
                if row["grant_sha256"] != self.receipt_hash:
                    raise StudyError("TUTOR_E3_RUN_ALREADY_BOUND", 403)
            else:
                if self.receipt.kind == "retest":
                    first = conn.execute("SELECT * FROM tutor_e3.run WHERE kind='initial'").fetchone()
                    if (
                        not first
                        or not phase["repair_sha256"]
                        or first["commit_sha"] == self.receipt.commit_sha
                        or first["build_sha256"] == self.grant.build_sha256
                        or any(
                            first["case_bindings"].get(key) != value
                            for key, value in self.receipt.case_bindings().items()
                        )
                    ):
                        raise StudyError("TUTOR_E3_RETEST_DENIED", 403)
                conn.execute(
                    """INSERT INTO tutor_e3.run
                       (kind,grant_sha256,target_id,grant_id,commit_sha,build_sha256,case_bindings)
                       VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                    (
                        self.receipt.kind,
                        self.receipt_hash,
                        self.grant.target_id,
                        self.grant.grant_id,
                        self.receipt.commit_sha,
                        self.grant.build_sha256,
                        Jsonb(self.receipt.case_bindings()),
                    ),
                )
        super().initialize()
        with self.connect() as conn:
            conn.execute(WIRE_DDL)

    def reserve(self, conn, session, turn, state, request_sha256):
        phase = lock_phase(conn, self.receipt)
        if self.receipt.kind == "initial" and phase["initial_closed_at"]:
            raise StudyError("TUTOR_E3_INITIAL_CLOSED", 403)
        calls = phase_rows(conn)
        if any(row["charged_nano_usd"] is None or row["error_code"] in IRRECOVERABLE for row in calls):
            raise StudyError("TUTOR_E3_UNRESOLVED_PHASE", 403)
        if self.dispatch_dir is not None:
            verify_dispatch_markers(self.dispatch_dir, calls)
        if (
            len(calls) >= PHASE_REQUESTS
            or sum(row["charged_nano_usd"] for row in calls) + RESERVE_NANO_USD > PHASE_BUDGET
        ):
            raise StudyError("TUTOR_E3_PHASE_BUDGET", 403)
        slot = self.slot(session["session_id"], turn["ordinal"], turn["learner_text"], turn["socratic"])
        count = conn.execute("SELECT count(*) AS n FROM tutor_flash_call").fetchone()["n"]
        if slot != count + 1:
            raise StudyError("TUTOR_E3_POSITION_OUT_OF_ORDER", 403)
        seen = {digest(row["text"].encode()) for row in state["evidence"]}
        if any(not seen.intersection(group) for group in self.receipt.required[slot - 1]):
            raise StudyError("TUTOR_E3_RETRIEVAL_MISS", 403)
        # The existing per-turn and per-run reservation commits under the phase lock.
        super().reserve(conn, session, turn, state, request_sha256)

    def observe(self, request, response=None, status=None, complete=False):
        with self.connect() as conn:
            if response is None:
                row = conn.execute(
                    """INSERT INTO tutor_e3_wire(turn_id,request)
                       SELECT turn_id,%s FROM tutor_flash_call
                       WHERE request_sha256=%s AND charged_nano_usd IS NULL
                       RETURNING turn_id""",
                    (request, digest(request)),
                ).fetchone()
                if row and self.dispatch_dir is not None:
                    call = conn.execute(
                        "SELECT slot FROM tutor_flash_call WHERE turn_id=%s", (row["turn_id"],)
                    ).fetchone()
                    mark_dispatch(self.dispatch_dir, self.receipt.kind, call["slot"], digest(request))
            else:
                row = conn.execute(
                    """UPDATE tutor_e3_wire w SET response=%s,http_status=%s,response_complete=%s
                       FROM tutor_flash_call c WHERE c.turn_id=w.turn_id AND c.request_sha256=%s
                       AND c.charged_nano_usd IS NULL AND w.response IS NULL RETURNING w.turn_id""",
                    (response, status, complete, digest(request)),
                ).fetchone()
            if not row:
                raise StudyError("TUTOR_E3_WIRE_JOURNAL_MISMATCH")


def verify_dispatch_markers(directory, calls):
    expected = {f"{row['run_kind']}-{row['slot']}": row["request_sha256"] for row in calls}
    actual = {item.name: item.read_text() for item in directory.iterdir()} if directory.exists() else {}
    if actual != expected:
        raise StudyError("TUTOR_E3_LEDGER_RESTORE_MISMATCH", 403)


def mark_dispatch(directory, kind, slot, request_sha256):
    # Durable outside PG so restoring a pre-dispatch DB snapshot cannot restore allowance.
    directory.mkdir(mode=0o700, exist_ok=True)
    with (directory / f"{kind}-{slot}").open("x") as stream:
        os.fchmod(stream.fileno(), 0o600)
        stream.write(request_sha256)
        stream.flush()
        os.fsync(stream.fileno())
    fd = os.open(directory, os.O_DIRECTORY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)
