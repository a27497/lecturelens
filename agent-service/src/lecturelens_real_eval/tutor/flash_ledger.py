"""A single, operator-approved Tutor trial per isolated PostgreSQL database."""

from datetime import timedelta
from pathlib import Path
from typing import Annotated, Literal

from psycopg.types.json import Jsonb
from pydantic import AwareDatetime, Field, model_validator

from lecturelens_agent.contracts import Contract, Identifier
from lecturelens_agent.study.store import StudyError

from .contracts import Command
from .flash_provider import MODEL, MODEL_VERSION, PRICE_ID, RATES, RESERVE_NANO_USD, digest
from .store import TutorStore

SHA256 = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
MAX_TRIAL_REQUESTS = 12
MAX_TRIAL_NANO_USD = MAX_TRIAL_REQUESTS * RESERVE_NANO_USD

TARGET_SCHEMA = """
CREATE TABLE IF NOT EXISTS tutor_flash_target (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 target_id uuid NOT NULL DEFAULT gen_random_uuid()
);
"""
SCHEMA = """
CREATE TABLE IF NOT EXISTS tutor_flash_trial (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),
 grant_id text NOT NULL UNIQUE, grant_sha256 text NOT NULL, mode text NOT NULL,
 build_sha256 text NOT NULL, dataset_sha256 text NOT NULL,
 model text NOT NULL, model_version text NOT NULL, price_id text NOT NULL, rates jsonb NOT NULL,
 issued_at timestamptz NOT NULL, expires_at timestamptz NOT NULL,
 request_limit integer NOT NULL CHECK(request_limit > 0),
 budget_nano_usd bigint NOT NULL CHECK(budget_nano_usd > 0),
 started_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 stop_code text, fingerprint text
);
CREATE TABLE IF NOT EXISTS tutor_flash_call (
 slot integer PRIMARY KEY CHECK(slot > 0),
 turn_id text NOT NULL UNIQUE, request_sha256 text NOT NULL,
 request_size_units integer NOT NULL CHECK(request_size_units > 0),
 reserved_nano_usd bigint NOT NULL CHECK(reserved_nano_usd > 0),
 reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 response_sha256 text, provider_id text, fingerprint text, usage jsonb,
 charged_nano_usd bigint CHECK(charged_nano_usd >= 0), error_code text,
 observed_at timestamptz, published_at timestamptz,
 CHECK((usage IS NULL) = (charged_nano_usd IS NULL))
);
"""


class AuthorizedTurn(Contract):
    text: Annotated[str, Field(min_length=1, max_length=2000)]
    socratic: bool = False


class AuthorizedSession(Contract):
    owner_id: Annotated[int, Field(ge=1)]
    course_id: Identifier
    revision: Annotated[int, Field(ge=0)]
    request_key: Identifier
    evidence_sha256: Annotated[list[SHA256], Field(min_length=1, max_length=4096)]
    turns: Annotated[list[AuthorizedTurn], Field(min_length=1, max_length=6)]

    @property
    def scope(self):
        return self.owner_id, self.course_id, self.revision


class FlashAuthorization(Contract):
    version: str
    grant_id: Annotated[str, Field(pattern=r"^[0-9a-f]{32}$")]
    mode: Literal["real", "offline-fake"]
    target_id: Annotated[str, Field(pattern=r"^[0-9a-f-]{36}$")]
    build_sha256: SHA256
    dataset_sha256: SHA256
    model: Literal[MODEL]
    model_version: Literal[MODEL_VERSION]
    price_id: Literal[PRICE_ID]
    issued_at: AwareDatetime
    expires_at: AwareDatetime
    accepts_supplier_risk: bool
    request_limit: Annotated[int, Field(ge=1, le=MAX_TRIAL_REQUESTS)]
    budget_nano_usd: Annotated[int, Field(ge=1, le=MAX_TRIAL_NANO_USD)]

    @model_validator(mode="after")
    def valid_window(self):
        if not self.accepts_supplier_risk or not timedelta(0) < self.expires_at - self.issued_at <= timedelta(
            hours=24
        ):
            raise ValueError("Inconsistent trial authorization")
        return self


class Grant(FlashAuthorization):
    version: Literal["lecturelens-phase1e-flash-v1"]
    sessions: Annotated[list[AuthorizedSession], Field(min_length=1, max_length=MAX_TRIAL_REQUESTS)]

    @model_validator(mode="after")
    def consistent(self):
        if (
            len({(*session.scope, session.request_key) for session in self.sessions}) != len(self.sessions)
            or sum(len(session.turns) for session in self.sessions) != self.request_limit
        ):
            raise ValueError("Inconsistent trial authorization")
        return self


def build_digest():
    # Bind authorization to the controller, authority transport and publication code.
    root = Path(__file__).resolve().parents[2]
    files = sorted(Path(__file__).parent.glob("*.py")) + [
        root / "lecturelens_agent/study/authority.py",
        root / "lecturelens_agent/study/store.py",
        root / "lecturelens_agent/contracts.py",
    ]
    return digest(b"".join(bytes.fromhex(digest(path.read_bytes())) for path in files))


class FlashLedgerStore(TutorStore):
    def __init__(self, dsn, grant, *, experiment):
        if grant.build_sha256 != build_digest():
            raise StudyError("TUTOR_FLASH_BUILD_CHANGED")
        super().__init__(dsn, engine="light", experiment=experiment)
        self.grant = grant
        self.grant_hash = digest(grant.model_dump_json().encode())

    def initialize(self):
        g = self.grant
        with self.connect() as conn:
            if not conn.execute("SELECT to_regclass('tutor_flash_target') AS target").fetchone()["target"]:
                raise StudyError("TUTOR_FLASH_WRONG_DATABASE", 403)
            target = conn.execute("SELECT target_id::text FROM tutor_flash_target WHERE singleton").fetchone()
            if not target or target["target_id"] != g.target_id:
                raise StudyError("TUTOR_FLASH_WRONG_DATABASE", 403)
        super().initialize()
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(7812251)")
            conn.execute(SCHEMA)
            row = conn.execute("SELECT * FROM tutor_flash_trial WHERE singleton").fetchone()
            if row:
                if row["grant_sha256"] != self.grant_hash:
                    raise StudyError("TUTOR_FLASH_GRANT_ALREADY_USED", 403)
                # The same receipt can recover its journal. It cannot reset limits or authorize a used slot.
                return
            now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
            if not g.issued_at <= now < g.expires_at:
                raise StudyError("TUTOR_FLASH_GRANT_EXPIRED", 403)
            conn.execute(
                """INSERT INTO tutor_flash_trial
                (grant_id,grant_sha256,mode,build_sha256,dataset_sha256,model,model_version,price_id,rates,
                 issued_at,expires_at,request_limit,budget_nano_usd)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (
                    g.grant_id,
                    self.grant_hash,
                    g.mode,
                    g.build_sha256,
                    g.dataset_sha256,
                    MODEL,
                    MODEL_VERSION,
                    PRICE_ID,
                    Jsonb(RATES),
                    g.issued_at,
                    g.expires_at,
                    g.request_limit,
                    g.budget_nano_usd,
                ),
            )

    def command(self, command):
        self.authorize_command(command)
        return super().command(command)

    def reserve_slot(self, conn, turn, state, request_sha256, *, slot=None):
        trial = self.lock_trial(conn)
        if trial["stop_code"]:
            raise StudyError("TUTOR_FLASH_TRIAL_STOPPED", 403)
        now = conn.execute("SELECT clock_timestamp() AS now").fetchone()["now"]
        if not (
            max(trial["issued_at"], self.grant.issued_at)
            <= now
            < min(trial["expires_at"], self.grant.expires_at)
        ):
            raise StudyError("TUTOR_FLASH_GRANT_EXPIRED", 403)
        if turn["deadline"] <= now:
            raise StudyError("TUTOR_DEADLINE")
        calls = conn.execute("SELECT slot,charged_nano_usd,published_at FROM tutor_flash_call").fetchall()
        if slot is None:
            slot = max((row["slot"] for row in calls), default=0) + 1
        if any(row["slot"] == slot for row in calls):
            raise StudyError("TUTOR_FLASH_SLOT_USED", 403)
        if any(row["charged_nano_usd"] is None for row in calls):
            raise StudyError("TUTOR_FLASH_UNRESOLVED_CHARGE", 403)
        if any(row["published_at"] is None for row in calls):
            raise StudyError("TUTOR_FLASH_PREVIOUS_UNPUBLISHED", 403)
        if len(calls) >= min(trial["request_limit"], self.grant.request_limit) or sum(
            row["charged_nano_usd"] for row in calls
        ) + RESERVE_NANO_USD > min(trial["budget_nano_usd"], self.grant.budget_nano_usd):
            raise StudyError("TUTOR_FLASH_COST_BUDGET", 403)
        conn.execute(
            """INSERT INTO tutor_flash_call (slot,turn_id,request_sha256,request_size_units,reserved_nano_usd)
            VALUES (%s,%s,%s,%s,%s)""",
            (slot, turn["turn_id"], request_sha256, state["reservation"], RESERVE_NANO_USD),
        )

    def lock_trial(self, conn):
        trial = conn.execute("SELECT * FROM tutor_flash_trial WHERE singleton FOR UPDATE").fetchone()
        if (
            not trial
            or trial["grant_sha256"] != self.grant_hash
            or (trial["model"], trial["model_version"], trial["price_id"], trial["rates"])
            != (MODEL, MODEL_VERSION, PRICE_ID, RATES)
        ):
            raise StudyError("TUTOR_FLASH_GRANT_MISMATCH", 403)
        return trial

    def settle(self, turn_id, request_sha256, result):
        with self.connect() as conn:
            trial = self.lock_trial(conn)
            error = result.error
            if trial["fingerprint"] and result.fingerprint and trial["fingerprint"] != result.fingerprint:
                error = "TUTOR_FLASH_IDENTITY_CHANGED"
            charge = sum(result.usage[key] * price for key, price in RATES.items()) if result.usage else None
            row = conn.execute(
                """UPDATE tutor_flash_call SET response_sha256=%s,provider_id=%s,fingerprint=%s,usage=%s,
                   charged_nano_usd=%s,error_code=%s,observed_at=clock_timestamp()
                   WHERE turn_id=%s AND request_sha256=%s AND observed_at IS NULL RETURNING slot""",
                (
                    result.response_sha256,
                    result.provider_id,
                    result.fingerprint,
                    Jsonb(result.usage) if result.usage is not None else None,
                    charge,
                    error,
                    turn_id,
                    request_sha256,
                ),
            ).fetchone()
            if not row:
                raise StudyError("TUTOR_FLASH_SETTLEMENT_CONFLICT")
            conn.execute(
                """UPDATE tutor_flash_trial SET fingerprint=coalesce(fingerprint,%s),
                   stop_code=coalesce(stop_code,%s) WHERE singleton""",
                (result.fingerprint if error is None else None, error),
            )
            return error

    def published(self, conn, turn_id):
        self.lock_trial(conn)
        # A deterministic no-evidence reply has no request to finalize.
        conn.execute(
            "UPDATE tutor_flash_call SET published_at=clock_timestamp() WHERE turn_id=%s AND charged_nano_usd IS NOT NULL",
            (turn_id,),
        )

    def fail(self, turn_id, code, stale=False):
        # A failed admitted turn closes the trial, even after usage was settled.
        # The orphan charge remains after Tutor content is purged.
        with self.connect() as conn:
            if conn.execute("SELECT 1 FROM tutor_flash_call WHERE turn_id=%s", (turn_id,)).fetchone():
                conn.execute(
                    """UPDATE tutor_flash_trial SET stop_code=coalesce(stop_code,%s)
                       WHERE singleton AND grant_sha256=%s""",
                    (code, self.grant_hash),
                )
                conn.execute(
                    "UPDATE tutor_flash_call SET error_code=coalesce(error_code,%s) WHERE turn_id=%s",
                    (code, turn_id),
                )
        super().fail(turn_id, code, stale)


class FlashStore(FlashLedgerStore):
    def __init__(self, dsn, grant):
        super().__init__(dsn, grant, experiment=grant.grant_id)
        offset = 0
        self.sessions = {}
        for plan in grant.sessions:
            command = Command(
                owner_id=plan.owner_id,
                course_id=plan.course_id,
                revision=plan.revision,
                request_key=plan.request_key,
                operation="CREATE",
            )
            self.sessions[self.session_id(command)] = (plan, offset)
            offset += len(plan.turns)

    def authorize_command(self, command):
        scope = command.owner_id, command.course_id, command.revision
        session_id = self.session_id(command) if command.operation == "CREATE" else command.session_id
        if command.operation == "LIST":
            allowed = any(scope == plan.scope for plan, _ in self.sessions.values())
        else:
            allowed = session_id in self.sessions and scope == self.sessions[session_id][0].scope
        if not allowed:
            raise StudyError("TUTOR_FLASH_SCOPE_DENIED", 404)

    def slot(self, session_id, ordinal, text, socratic):
        entry = self.sessions.get(session_id)
        if entry is None:
            raise StudyError("TUTOR_FLASH_SCOPE_DENIED", 404)
        plan, offset = entry
        if not 1 <= ordinal <= len(plan.turns):
            raise StudyError("TUTOR_FLASH_TASK_DENIED", 403)
        expected = plan.turns[ordinal - 1]
        if (text, socratic) != (expected.text, expected.socratic):
            raise StudyError("TUTOR_FLASH_TASK_DENIED", 403)
        return offset + ordinal

    def before_enqueue(self, conn, command, session, ordinal):
        self.slot(session["session_id"], ordinal, command.text, command.socratic)
        if (
            ordinal > 1
            and not conn.execute(
                "SELECT 1 FROM tutor_turn WHERE session_id=%s AND ordinal=%s AND status='completed'",
                (session["session_id"], ordinal - 1),
            ).fetchone()
        ):
            raise StudyError("TUTOR_FLASH_PREVIOUS_TURN_FAILED")

    def reserve(self, conn, session, turn, state, request_sha256):
        slot = self.slot(session["session_id"], turn["ordinal"], turn["learner_text"], turn["socratic"])
        plan, _ = self.sessions[session["session_id"]]
        if any(digest(row["text"].encode()) not in plan.evidence_sha256 for row in state["evidence"]):
            raise StudyError("TUTOR_FLASH_EVIDENCE_NOT_APPROVED", 403)
        self.reserve_slot(conn, turn, state, request_sha256, slot=slot)
