"""Idempotent startup DDL, like StudyStore. No MySQL writes or shared Run changes."""

import uuid
from contextlib import contextmanager

from psycopg.types.json import Jsonb

from lecturelens_agent.study.store import StudyError, StudyStore

SCHEMA = """
CREATE TABLE IF NOT EXISTS tutor_session (
 session_id text PRIMARY KEY, owner_id bigint NOT NULL, course_id text NOT NULL,
 revision bigint NOT NULL, status text NOT NULL DEFAULT 'active' CHECK(status IN ('active','stale')),
 summary text NOT NULL DEFAULT '', summary_through integer NOT NULL DEFAULT 0,
 model_calls integer NOT NULL DEFAULT 0, reserved_tokens integer NOT NULL DEFAULT 0,
 max_calls integer NOT NULL DEFAULT 60, max_tokens integer NOT NULL DEFAULT 640000,
 created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS tutor_session_scope ON tutor_session(owner_id,course_id,created_at);
CREATE TABLE IF NOT EXISTS tutor_turn (
 turn_id text PRIMARY KEY, session_id text NOT NULL REFERENCES tutor_session ON DELETE CASCADE,
 client_turn_id text NOT NULL, ordinal integer NOT NULL, learner_text text NOT NULL,
 socratic boolean NOT NULL, status text NOT NULL DEFAULT 'queued'
 CHECK(status IN ('queued','running','completed','failed','cancelled')),
 outcome text CHECK(outcome IN ('answered','socratic_prompt','insufficient_evidence','failed')),
 answer text, evaluation text, citations jsonb NOT NULL DEFAULT '[]',
 usage jsonb NOT NULL DEFAULT '[]', model_calls integer NOT NULL DEFAULT 0,
 tool_calls integer NOT NULL DEFAULT 0, reserved_tokens integer NOT NULL DEFAULT 0,
 checkpoint jsonb NOT NULL DEFAULT '{"phase":"ready","observations":[],"selected":[]}',
 deadline timestamptz, error_code text, created_at timestamptz NOT NULL DEFAULT now(),
 finished_at timestamptz, UNIQUE(session_id,client_turn_id), UNIQUE(session_id,ordinal)
);
CREATE UNIQUE INDEX IF NOT EXISTS tutor_one_active_turn ON tutor_turn(session_id)
 WHERE status IN ('queued','running');
"""


class TutorStore(StudyStore):
    def initialize(self):
        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(7812250)")
            conn.execute(SCHEMA)

    @contextmanager
    def execution_lock(self, session_id):
        with self.connect(autocommit=True) as conn:
            acquired = conn.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,8)) AS ok", (session_id,)
            ).fetchone()["ok"]
            try:
                yield acquired
            finally:
                if acquired:
                    conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,8))", (session_id,))

    def session(self, conn, command):
        row = conn.execute(
            "SELECT * FROM tutor_session WHERE session_id=%s AND owner_id=%s AND course_id=%s FOR UPDATE",
            (command.session_id, command.owner_id, command.course_id),
        ).fetchone()
        if not row:
            raise StudyError("TUTOR_SESSION_NOT_FOUND", 404)
        return row

    def fence(self, conn, scope):
        # A deletion tombstone also blocks an in-flight result before asynchronous purge.
        if (
            conn.execute("SELECT to_regclass('evidence_index') AS t").fetchone()["t"]
            and conn.execute(
                "SELECT 1 FROM evidence_index WHERE owner_id=%s AND course_id=%s AND state='DELETED'",
                (scope["owner_id"], scope["course_id"]),
            ).fetchone()
        ):
            raise StudyError("COURSE_UNAVAILABLE_OR_CHANGED", 404)

    def command(self, command):
        error = None
        with self.connect() as conn:
            self.fence(conn, command.model_dump())
            if command.operation == "CREATE":
                sid = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"tutor:{command.owner_id}:{command.course_id}:{command.revision}:{command.request_key}",
                    )
                )
                conn.execute(
                    "INSERT INTO tutor_session(session_id,owner_id,course_id,revision) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (sid, command.owner_id, command.course_id, command.revision),
                )
                return {
                    "session": self.public_session(
                        conn.execute("SELECT * FROM tutor_session WHERE session_id=%s", (sid,)).fetchone()
                    )
                }
            # Committed staleness survives the conflict response and future retries.
            conn.execute(
                "UPDATE tutor_session SET status='stale' WHERE owner_id=%s AND course_id=%s AND revision<>%s",
                (command.owner_id, command.course_id, command.revision),
            )
            conn.execute(
                """UPDATE tutor_turn t SET status='failed',outcome='failed',answer=NULL,
                evaluation=NULL,citations='[]',error_code='TUTOR_SESSION_STALE',finished_at=now()
                FROM tutor_session s WHERE t.session_id=s.session_id AND s.owner_id=%s
                AND s.course_id=%s AND s.status='stale' AND t.status IN ('queued','running')""",
                (command.owner_id, command.course_id),
            )
            if command.operation == "LIST":
                return {
                    "sessions": [
                        self.public_session(row)
                        for row in conn.execute(
                            "SELECT * FROM tutor_session WHERE owner_id=%s AND course_id=%s ORDER BY created_at DESC,session_id LIMIT 20",
                            (command.owner_id, command.course_id),
                        ).fetchall()
                    ]
                }
            session = self.session(conn, command)
            if session["status"] == "stale" or session["revision"] != command.revision:
                error = StudyError("TUTOR_SESSION_STALE")
            elif command.operation == "GET":
                return self.view(conn, session)
            elif command.operation == "CANCEL":
                row = conn.execute(
                    "UPDATE tutor_turn SET status='cancelled',outcome='failed',answer=NULL,citations='[]',error_code='TUTOR_CANCELLED',finished_at=now() WHERE session_id=%s AND client_turn_id=%s AND status IN ('queued','running') RETURNING turn_id",
                    (session["session_id"], command.client_turn_id),
                ).fetchone()
                if (
                    not row
                    and not conn.execute(
                        "SELECT 1 FROM tutor_turn WHERE session_id=%s AND client_turn_id=%s",
                        (session["session_id"], command.client_turn_id),
                    ).fetchone()
                ):
                    raise StudyError("TUTOR_TURN_NOT_FOUND", 404)
                return self.view(conn, session)
            else:
                prior = conn.execute(
                    "SELECT * FROM tutor_turn WHERE session_id=%s AND client_turn_id=%s",
                    (session["session_id"], command.client_turn_id),
                ).fetchone()
                if prior:
                    if prior["learner_text"] != command.text or prior["socratic"] != command.socratic:
                        raise StudyError("REQUEST_KEY_CONFLICT")
                    return {**self.view(conn, session), "replayed": True}
                if conn.execute(
                    "SELECT 1 FROM tutor_turn WHERE session_id=%s AND status IN ('queued','running')",
                    (session["session_id"],),
                ).fetchone():
                    raise StudyError("SESSION_BUSY")
                count = conn.execute(
                    "SELECT count(*) AS n FROM tutor_turn WHERE session_id=%s", (session["session_id"],)
                ).fetchone()["n"]
                if (
                    count >= 40
                    or session["model_calls"] >= session["max_calls"]
                    or session["reserved_tokens"] >= session["max_tokens"]
                ):
                    raise StudyError("TUTOR_SESSION_BUDGET")
                conn.execute(
                    "INSERT INTO tutor_turn(turn_id,session_id,client_turn_id,ordinal,learner_text,socratic) VALUES (%s,%s,%s,%s,%s,%s)",
                    (
                        str(uuid.uuid4()),
                        session["session_id"],
                        command.client_turn_id,
                        count + 1,
                        command.text,
                        command.socratic,
                    ),
                )
                return {**self.view(conn, session), "replayed": False}
        if error:
            raise error

    def view(self, conn, session):
        rows = conn.execute(
            "SELECT * FROM tutor_turn WHERE session_id=%s ORDER BY ordinal", (session["session_id"],)
        ).fetchall()
        return {"session": self.public_session(session), "turns": [self.public_turn(row) for row in rows]}

    @staticmethod
    def public_session(row):
        return {k: v for k, v in row.items() if k not in {"summary", "summary_through"}}

    @staticmethod
    def public_turn(row):
        return {k: v for k, v in row.items() if k not in {"checkpoint", "deadline"}}

    def candidates(self):
        with self.connect() as conn:
            return conn.execute(
                "SELECT t.turn_id,t.session_id FROM tutor_turn t JOIN tutor_session s USING(session_id) WHERE t.status IN ('queued','running') AND s.status='active' ORDER BY t.created_at LIMIT 20"
            ).fetchall()

    def fail(self, turn_id, code, stale=False):
        with self.connect() as conn:
            # The Session lock always precedes the Turn lock, including cancellation.
            row = conn.execute("SELECT session_id FROM tutor_turn WHERE turn_id=%s", (turn_id,)).fetchone()
            if not row:
                return
            conn.execute("SELECT 1 FROM tutor_session WHERE session_id=%s FOR UPDATE", (row["session_id"],))
            conn.execute(
                "UPDATE tutor_turn SET status='failed',outcome='failed',answer=NULL,evaluation=NULL,citations='[]',error_code=%s,finished_at=now() WHERE turn_id=%s AND status IN ('queued','running')",
                (code, turn_id),
            )
            if stale:
                conn.execute(
                    "UPDATE tutor_session SET status='stale' WHERE session_id=%s", (row["session_id"],)
                )

    def purge_deleted(self):
        with self.connect() as conn:
            if not conn.execute("SELECT to_regclass('evidence_index') AS t").fetchone()["t"]:
                return
            rows = conn.execute(
                "SELECT s.session_id FROM tutor_session s JOIN evidence_index i USING(owner_id,course_id) WHERE i.state='DELETED' LIMIT 20"
            ).fetchall()
        for row in rows:
            with self.execution_lock(row["session_id"]) as acquired:
                if acquired:
                    with self.connect() as conn:
                        conn.execute("DELETE FROM tutor_session WHERE session_id=%s", (row["session_id"],))

    def rows(self, conn, turn_id):
        turn = conn.execute("SELECT session_id FROM tutor_turn WHERE turn_id=%s", (turn_id,)).fetchone()
        if not turn:
            raise StudyError("TUTOR_TURN_NOT_FOUND", 404)
        session = conn.execute(
            "SELECT * FROM tutor_session WHERE session_id=%s FOR UPDATE", (turn["session_id"],)
        ).fetchone()
        turn = conn.execute("SELECT * FROM tutor_turn WHERE turn_id=%s FOR UPDATE", (turn_id,)).fetchone()
        return session, turn

    @staticmethod
    def checkpoint(conn, turn_id, state):
        conn.execute("UPDATE tutor_turn SET checkpoint=%s WHERE turn_id=%s", (Jsonb(state), turn_id))
