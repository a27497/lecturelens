"""Run journal and idempotent artifacts; PostgreSQL owns the execution lifecycle."""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

SCHEMA = """
CREATE TABLE IF NOT EXISTS study_session (
    session_id text PRIMARY KEY, owner_id bigint NOT NULL, course_id text NOT NULL,
    revision bigint NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS study_session_scope ON study_session(owner_id,course_id,created_at);
CREATE TABLE IF NOT EXISTS study_run (
    run_id text PRIMARY KEY, session_id text NOT NULL REFERENCES study_session,
    request_key text NOT NULL, goal text NOT NULL, status text NOT NULL DEFAULT 'queued',
    model_mode text NOT NULL, worker_token text, model_calls integer NOT NULL DEFAULT 0,
    tool_calls integer NOT NULL DEFAULT 0, reserved_tokens integer NOT NULL DEFAULT 0,
    deadline timestamptz, error_code text, created_at timestamptz NOT NULL DEFAULT now(),
    finished_at timestamptz, UNIQUE(session_id,request_key)
);
CREATE UNIQUE INDEX IF NOT EXISTS study_one_active_run ON study_run(session_id)
    WHERE status IN ('queued','running');
ALTER TABLE study_run ADD COLUMN IF NOT EXISTS model_config jsonb;
CREATE TABLE IF NOT EXISTS study_event (
    run_id text NOT NULL REFERENCES study_run ON DELETE CASCADE, sequence bigint NOT NULL,
    event_type text NOT NULL, payload jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    PRIMARY KEY(run_id,sequence), UNIQUE(run_id,event_type,payload)
);
ALTER TABLE study_event ADD COLUMN IF NOT EXISTS trace_detail jsonb;
CREATE TABLE IF NOT EXISTS study_tool_result (
    run_id text NOT NULL REFERENCES study_run ON DELETE CASCADE, call_id text NOT NULL,
    tool_name text NOT NULL, arguments jsonb NOT NULL, result jsonb NOT NULL,
    PRIMARY KEY(run_id,call_id)
);
CREATE TABLE IF NOT EXISTS study_artifact (
    artifact_id text PRIMARY KEY, run_id text NOT NULL UNIQUE REFERENCES study_run ON DELETE CASCADE,
    call_id text NOT NULL, content jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(run_id,call_id)
);
"""
TERMINAL = {"succeeded", "failed", "cancelled", "budget_exceeded"}


class StudyError(Exception):
    def __init__(self, code, status=409):
        self.code, self.status = code, status
        super().__init__(code)


class RunStopped(Exception):
    pass


class BudgetExceeded(Exception):
    pass


class StudyStore:
    def __init__(self, dsn, model_resolver=None):
        self.dsn = dsn
        self.model_resolver = model_resolver

    def connect(self, **kwargs):
        return psycopg.connect(self.dsn, connect_timeout=5, row_factory=dict_row, **kwargs)

    def initialize(self):
        from .attempts import SCHEMA as ATTEMPT_SCHEMA
        from .feedback_store import SCHEMA as FEEDBACK_SCHEMA

        with self.connect() as conn:
            conn.execute("SELECT pg_advisory_xact_lock(7812250)")
            conn.execute(SCHEMA)
            conn.execute(ATTEMPT_SCHEMA)
            conn.execute(FEEDBACK_SCHEMA)

    @staticmethod
    def _session(conn, command):
        row = conn.execute(
            """SELECT * FROM study_session WHERE session_id=%s AND owner_id=%s
                              AND course_id=%s AND revision=%s FOR UPDATE""",
            (command.session_id, command.owner_id, command.course_id, command.revision),
        ).fetchone()
        if not row:
            raise StudyError("SESSION_NOT_FOUND_OR_STALE", 404)
        return row

    def command(self, command, mode):
        with self.connect() as conn:
            if command.operation == "CREATE_SESSION":
                if not command.request_key:
                    raise StudyError("REQUEST_KEY_REQUIRED", 422)
                # Deterministic scoped ID makes an HTTP retry safe even if its response was lost.
                session = str(
                    uuid.uuid5(
                        uuid.NAMESPACE_URL,
                        f"study:{command.owner_id}:{command.course_id}:{command.revision}:{command.request_key}",
                    )
                )
                conn.execute(
                    "INSERT INTO study_session(session_id,owner_id,course_id,revision) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
                    (session, command.owner_id, command.course_id, command.revision),
                )
                return {"session_id": session, "revision": command.revision, "mode": mode}
            if command.operation == "LIST":
                rows = conn.execute(
                    """SELECT session_id,revision,created_at FROM study_session
                    WHERE owner_id=%s AND course_id=%s AND revision=%s ORDER BY created_at DESC LIMIT 20""",
                    (command.owner_id, command.course_id, command.revision),
                ).fetchall()
                return {"sessions": rows, "mode": mode}
            self._session(conn, command)
            if command.operation == "RUNS":
                rows = conn.execute(
                    "SELECT run_id,goal,status,created_at FROM study_run WHERE session_id=%s AND task_kind='practice' "
                    "ORDER BY created_at DESC LIMIT 20",
                    (command.session_id,),
                ).fetchall()
                return {"runs": rows}
            if command.operation == "START":
                if not command.goal or not command.goal.strip() or not command.request_key:
                    raise StudyError("GOAL_AND_REQUEST_KEY_REQUIRED", 422)
                prior = conn.execute(
                    "SELECT * FROM study_run WHERE session_id=%s AND request_key=%s",
                    (command.session_id, command.request_key),
                ).fetchone()
                if prior:
                    if prior["goal"] != command.goal or prior["task_kind"] != "practice":
                        raise StudyError("REQUEST_KEY_CONFLICT")
                    return self._view(conn, prior)
                if conn.execute(
                    "SELECT 1 FROM study_run WHERE session_id=%s AND status IN ('queued','running')",
                    (command.session_id,),
                ).fetchone():
                    raise StudyError("SESSION_BUSY")
                run_id = str(uuid.uuid4())
                config = (
                    self.model_resolver(command.owner_id) if mode == "real" and self.model_resolver else None
                )
                row = conn.execute(
                    """INSERT INTO study_run(run_id,session_id,request_key,goal,model_mode,model_config)
                    VALUES (%s,%s,%s,%s,%s,%s) RETURNING *""",
                    (
                        run_id,
                        command.session_id,
                        command.request_key,
                        command.goal,
                        mode,
                        Jsonb(config) if config else None,
                    ),
                ).fetchone()
                self._event(conn, run_id, "run_queued", {})
                return self._view(conn, row)
            if command.run_id:
                run = conn.execute(
                    "SELECT * FROM study_run WHERE run_id=%s AND session_id=%s FOR UPDATE",
                    (command.run_id, command.session_id),
                ).fetchone()
            else:
                run = conn.execute(
                    "SELECT * FROM study_run WHERE session_id=%s AND task_kind='practice' ORDER BY created_at DESC LIMIT 1 FOR UPDATE",
                    (command.session_id,),
                ).fetchone()
            if not run:
                if command.operation == "READ" and command.run_id is None:
                    return {"run": None, "mode": mode}
                raise StudyError("RUN_NOT_FOUND", 404)
            if command.operation == "START_FEEDBACK":
                from .feedback_store import start_feedback

                return start_feedback(self, conn, run, command, mode)
            if command.operation in {"SAVE_FEEDBACK_NOTE", "FEEDBACK_NOTES"}:
                from .feedback_store import feedback_note

                return feedback_note(self, conn, run, command)
            if command.operation in {"SAVE_ATTEMPT", "ATTEMPT_HISTORY"}:
                from .attempts import attempt_command

                return attempt_command(self, conn, run, command)
            if command.operation == "CANCEL":
                if run["status"] not in TERMINAL:
                    self._finish(conn, run["run_id"], "cancelled", "USER_CANCELLED")
                    run["status"], run["error_code"] = "cancelled", "USER_CANCELLED"
            if command.operation == "ANSWERS":
                if run["status"] != "succeeded":
                    raise StudyError("ARTIFACT_NOT_READY")
                artifact = conn.execute(
                    "SELECT content FROM study_artifact WHERE run_id=%s", (run["run_id"],)
                ).fetchone()
                if not artifact:
                    raise StudyError("ARTIFACT_NOT_READY")
                return {"questions": artifact["content"]["questions"]}
            if command.operation == "EVENTS":
                rows = conn.execute(
                    "SELECT sequence,event_type,payload FROM study_event WHERE run_id=%s AND sequence>%s "
                    "AND event_type NOT IN ('node_started','node_finished','node_failed','evidence_started','evidence_finished','evidence_failed','replay_linked') "
                    "ORDER BY sequence LIMIT 100",
                    (run["run_id"], command.after),
                ).fetchall()
                # Preserve sequence/cursor semantics; private diagnostics never enter SSE.
                for event in rows:
                    event["payload"] = {k: v for k, v in event["payload"].items() if k != "_trace"}
                return {"events": rows, "status": run["status"]}
            return self._view(conn, run)

    @staticmethod
    def _view(conn, row):
        from .attempts import current_attempts
        from .feedback_store import enabled, feedback_runs, feedback_view

        artifact = (
            conn.execute(
                "SELECT artifact_id,content FROM study_artifact WHERE run_id=%s", (row["run_id"],)
            ).fetchone()
            if row["status"] == "succeeded"
            else None
        )
        public = None
        if artifact:
            public = {**artifact["content"], "artifact_id": artifact["artifact_id"]}
            public["questions"] = [
                {"question": q["question"], "evidence_ids": q["evidence_ids"]} for q in public["questions"]
            ]
        return {
            "run": {
                k: row[k]
                for k in (
                    "run_id",
                    "session_id",
                    "goal",
                    "request_key",
                    "status",
                    "model_mode",
                    "model_calls",
                    "tool_calls",
                    "reserved_tokens",
                    "error_code",
                    "created_at",
                    "finished_at",
                    "task_kind",
                )
            }
            | {
                "model_selection": {
                    role: {key: config[key] for key in ("connection_id", "name", "version", "model")}
                    for role, config in (row.get("model_config") or {}).items()
                }
            },
            "artifact": public,
            "attempts": current_attempts(conn, artifact["artifact_id"]) if artifact else [],
            "feedback_enabled": enabled(),
            "feedback": feedback_view(conn, row["run_id"]) if row["task_kind"] == "feedback" else None,
            "feedback_runs": feedback_runs(conn, artifact["artifact_id"]) if artifact else [],
        }

    @staticmethod
    def _event(conn, run_id, name, payload):
        # Caller locks the run row. Event sequence and effect commit together.
        detail = payload.get("_trace")
        public = {k: v for k, v in payload.items() if k != "_trace"}
        conn.execute(
            """INSERT INTO study_event(run_id,sequence,event_type,payload,trace_detail)
            SELECT %s,COALESCE(MAX(sequence),0)+1,%s,%s,%s FROM study_event WHERE run_id=%s
            ON CONFLICT DO NOTHING""",
            (run_id, name, Jsonb(public), Jsonb(detail) if detail is not None else None, run_id),
        )

    def recent_context(self, session_id, run_id):
        with self.connect() as conn:
            rows = conn.execute(
                """SELECT r.goal,a.artifact_id,a.content FROM study_run r
                JOIN study_artifact a USING(run_id) WHERE r.session_id=%s AND r.run_id<>%s
                AND r.status='succeeded' ORDER BY r.created_at DESC LIMIT 2""",
                (session_id, run_id),
            ).fetchall()
            return [
                {
                    "goal": row["goal"],
                    "artifact_id": row["artifact_id"],
                    "title": row["content"]["title"],
                    "explanation": row["content"]["explanation"][:800],
                    "evidence_ids": row["content"]["evidence_ids"],
                }
                for row in reversed(rows)
            ]

    def candidates(self):
        with self.connect() as conn:
            return conn.execute("""SELECT r.*,s.owner_id,s.course_id,s.revision FROM study_run r JOIN study_session s USING(session_id)
                WHERE r.status IN ('queued','running') ORDER BY r.created_at LIMIT 20""").fetchall()

    @contextmanager
    def execution_lock(self, session_id):
        # Session advisory lock is held by a dedicated *autocommit* connection, not a DB transaction.
        # A crashed process loses the connection; a merely slow worker cannot be fenced out and
        # then overwrite a newer LangGraph checkpoint after its external call returns.
        with self.connect(autocommit=True) as conn:
            acquired = conn.execute(
                "SELECT pg_try_advisory_lock(hashtextextended(%s,7812251)) AS acquired", (session_id,)
            ).fetchone()["acquired"]
            try:
                yield acquired
            finally:
                if acquired:
                    conn.execute("SELECT pg_advisory_unlock(hashtextextended(%s,7812251))", (session_id,))

    def claim(self, run_id, token, seconds):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM study_run WHERE run_id=%s FOR UPDATE", (run_id,)).fetchone()
            if not row or row["status"] in TERMINAL:
                raise RunStopped()
            conn.execute(
                """UPDATE study_run SET status='running',worker_token=%s,
                deadline=COALESCE(deadline,now()+(%s * interval '1 second')) WHERE run_id=%s""",
                (token, seconds, run_id),
            )
            self._event(conn, run_id, "run_started" if row["status"] == "queued" else "run_resumed", {})

    @staticmethod
    def _active(conn, run_id, token):
        row = conn.execute("SELECT * FROM study_run WHERE run_id=%s FOR UPDATE", (run_id,)).fetchone()
        if not row or row["status"] != "running" or row["worker_token"] != token:
            raise RunStopped()
        if row["deadline"] and datetime.now(timezone.utc) >= row["deadline"]:
            raise BudgetExceeded()
        return row

    def guard(self, run_id, token):
        with self.connect() as conn:
            return self._active(conn, run_id, token)

    def reserve(self, run_id, token, kind, tokens=0):
        with self.connect() as conn:
            row = self._active(conn, run_id, token)
            if (
                (kind == "model" and row["model_calls"] >= 6)
                or (kind == "tool" and row["tool_calls"] >= 8)
                or row["reserved_tokens"] + tokens > 64000
            ):
                raise BudgetExceeded()
            column = "model_calls" if kind == "model" else "tool_calls"
            conn.execute(
                f"UPDATE study_run SET {column}={column}+1,reserved_tokens=reserved_tokens+%s WHERE run_id=%s",
                (tokens, run_id),
            )

    def tool_result(self, run_id, call_id):
        with self.connect() as conn:
            return conn.execute(
                "SELECT * FROM study_tool_result WHERE run_id=%s AND call_id=%s", (run_id, call_id)
            ).fetchone()

    def event(self, run_id, token, name, payload):
        with self.connect() as conn:
            self._active(conn, run_id, token)
            self._event(conn, run_id, name, payload)

    def save_tool(self, run_id, token, call_id, name, arguments, result, artifact=None, feedback=None):
        with self.connect() as conn:
            run = self._active(conn, run_id, token)
            prior = conn.execute(
                "SELECT * FROM study_tool_result WHERE run_id=%s AND call_id=%s", (run_id, call_id)
            ).fetchone()
            if prior:
                if prior["tool_name"] != name or prior["arguments"] != arguments:
                    raise StudyError("TOOL_ID_CONFLICT")
                return prior["result"]
            if "quality" in result:
                # Never expose critique prose, draft answers or evidence in the public event stream.
                self._event(
                    conn,
                    run_id,
                    "quality_checked",
                    {
                        "call_id": call_id,
                        "accepted": result["quality"]["accepted"],
                        "issues": result["quality"]["issues"],
                        "source": result["quality"].get("source", "model_review"),
                    },
                )
            if artifact:
                artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{call_id}"))
                conn.execute(
                    "INSERT INTO study_artifact VALUES (%s,%s,%s,%s,now()) ON CONFLICT (run_id) DO NOTHING",
                    (artifact_id, run_id, call_id, Jsonb(artifact)),
                )
                public = {"artifact_id": artifact_id, "question_count": len(artifact["questions"])}
                self._event(conn, run_id, "artifact_created", public)
                # Keep accepted checks available for private audit and checkpoint recovery too.
                result = {**result, **public}
            if feedback is not None:
                from .feedback_store import save_feedback

                feedback_id = save_feedback(conn, run, feedback)
                self._event(conn, run_id, "feedback_created", {"feedback_id": feedback_id})
                result = {**result, "feedback_id": feedback_id}
            conn.execute(
                "INSERT INTO study_tool_result VALUES (%s,%s,%s,%s,%s)",
                (run_id, call_id, name, Jsonb(arguments), Jsonb(result)),
            )
            self._event(conn, run_id, "tool_finished", {"call_id": call_id, "tool": name})
            return result

    @classmethod
    def _finish(cls, conn, run_id, status, error=None):
        conn.execute(
            "UPDATE study_run SET status=%s,error_code=%s,finished_at=now() WHERE run_id=%s",
            (status, error, run_id),
        )
        cls._event(conn, run_id, "run_finished", {"status": status, "error_code": error})

    def finish(self, run_id, token, status, error=None):
        with self.connect() as conn:
            row = conn.execute("SELECT * FROM study_run WHERE run_id=%s FOR UPDATE", (run_id,)).fetchone()
            if row and row["status"] == "running" and row["worker_token"] == token:
                if status == "succeeded" and row["deadline"] <= datetime.now(timezone.utc):
                    status, error = "budget_exceeded", "DEADLINE_EXCEEDED"
                self._finish(conn, run_id, status, error)
