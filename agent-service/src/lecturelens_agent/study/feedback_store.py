"""Feedback journals reference immutable answers and share the normal Run lifecycle."""

import os
import uuid

from psycopg.types.json import Jsonb

from .store import StudyError

SCHEMA = """
ALTER TABLE study_run ADD COLUMN IF NOT EXISTS task_kind text NOT NULL DEFAULT 'practice'
    CHECK (task_kind IN ('practice','feedback'));
ALTER TABLE study_run ADD COLUMN IF NOT EXISTS source_attempt_id text
    REFERENCES study_attempt ON DELETE CASCADE;
CREATE TABLE IF NOT EXISTS study_feedback (
    feedback_id text PRIMARY KEY, run_id text NOT NULL UNIQUE REFERENCES study_run ON DELETE CASCADE,
    attempt_id text NOT NULL REFERENCES study_attempt ON DELETE CASCADE,
    content jsonb NOT NULL, created_at timestamptz NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS study_feedback_note (
    note_id text PRIMARY KEY, feedback_id text NOT NULL REFERENCES study_feedback ON DELETE CASCADE,
    version integer NOT NULL CHECK (version > 0), request_key text NOT NULL,
    disposition text NOT NULL CHECK (disposition IN ('disputed','acknowledged')),
    note_text text NOT NULL CHECK (length(btrim(note_text)) BETWEEN 1 AND 2000),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(feedback_id,version), UNIQUE(feedback_id,request_key)
);
"""


def enabled():
    return os.environ.get("STUDY_FEEDBACK_ENABLED", "false").lower() == "true"


def start_feedback(store, conn, parent, command, mode):
    if not enabled():
        raise StudyError("FEEDBACK_DISABLED", 409)
    attempt = conn.execute(
        "SELECT a.* FROM study_attempt a JOIN study_artifact p USING(artifact_id) "
        "WHERE a.attempt_id=%s AND p.run_id=%s AND a.artifact_id=%s AND a.question_index=%s",
        (command.attempt_id, parent["run_id"], command.artifact_id, command.question_index),
    ).fetchone()
    if not attempt or parent["status"] != "succeeded":
        raise StudyError("ATTEMPT_NOT_FOUND", 404)
    prior = conn.execute(
        "SELECT * FROM study_run WHERE session_id=%s AND request_key=%s",
        (parent["session_id"], command.request_key),
    ).fetchone()
    if prior:
        if prior["task_kind"] != "feedback" or prior["source_attempt_id"] != command.attempt_id:
            raise StudyError("REQUEST_KEY_CONFLICT")
        return store._view(conn, prior)
    if conn.execute(
        "SELECT 1 FROM study_run WHERE session_id=%s AND status IN ('queued','running')",
        (parent["session_id"],),
    ).fetchone():
        raise StudyError("SESSION_BUSY")
    config = store.model_resolver(command.owner_id) if mode == "real" and store.model_resolver else None
    row = conn.execute(
        "INSERT INTO study_run(run_id,session_id,request_key,goal,model_mode,model_config,task_kind,source_attempt_id) "
        "VALUES (%s,%s,%s,%s,%s,%s,'feedback',%s) RETURNING *",
        (
            str(uuid.uuid4()),
            parent["session_id"],
            command.request_key,
            f"第 {attempt['question_index'] + 1} 题第 {attempt['version']} 版作答的课程证据反馈",
            mode,
            Jsonb(config) if config else None,
            command.attempt_id,
        ),
    ).fetchone()
    store._event(conn, row["run_id"], "run_queued", {})
    return store._view(conn, row)


def feedback_source(store, run):
    with store.connect() as conn:
        row = conn.execute(
            "SELECT a.*,p.content FROM study_attempt a JOIN study_artifact p USING(artifact_id) "
            "JOIN study_run r ON r.run_id=p.run_id WHERE a.attempt_id=%s AND r.session_id=%s",
            (run["source_attempt_id"], run["session_id"]),
        ).fetchone()
    if not row:
        raise StudyError("ATTEMPT_NOT_FOUND", 404)
    return {
        "attempt_id": row["attempt_id"],
        "version": row["version"],
        "answer_text": row["answer_text"],
        "question": row["content"]["questions"][row["question_index"]],
    }


def feedback_view(conn, run_id):
    row = conn.execute(
        "SELECT f.feedback_id,f.content,a.attempt_id,a.version AS answer_version,a.question_index,a.answer_text "
        "FROM study_feedback f JOIN study_attempt a USING(attempt_id) "
        "JOIN study_run r ON r.run_id=f.run_id WHERE f.run_id=%s AND r.status='succeeded'",
        (run_id,),
    ).fetchone()
    if row:
        row["note"] = conn.execute(
            "SELECT note_id,version,disposition,note_text,created_at FROM study_feedback_note "
            "WHERE feedback_id=%s ORDER BY version DESC LIMIT 1",
            (row["feedback_id"],),
        ).fetchone()
    return row


def feedback_runs(conn, artifact_id):
    rows = conn.execute(
        "SELECT r.run_id,r.request_key,r.status,r.error_code,a.attempt_id,a.question_index,a.version AS answer_version "
        "FROM study_run r JOIN study_attempt a ON r.source_attempt_id=a.attempt_id "
        "WHERE a.artifact_id=%s ORDER BY r.created_at DESC LIMIT 20",
        (artifact_id,),
    ).fetchall()
    return [row | {"feedback": feedback_view(conn, row["run_id"])} for row in rows]


def save_feedback(conn, run, content):
    feedback_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"feedback:{run['run_id']}"))
    conn.execute(
        "INSERT INTO study_feedback(feedback_id,run_id,attempt_id,content) VALUES (%s,%s,%s,%s) "
        "ON CONFLICT(run_id) DO NOTHING",
        (feedback_id, run["run_id"], run["source_attempt_id"], Jsonb(content)),
    )
    return feedback_id


def feedback_note(store, conn, run, command):
    feedback = feedback_view(conn, run["run_id"])
    if not feedback or feedback["feedback_id"] != command.feedback_id:
        raise StudyError("FEEDBACK_NOT_FOUND", 404)
    if command.operation == "FEEDBACK_NOTES":
        rows = conn.execute(
            "SELECT note_id,version,disposition,note_text,created_at FROM study_feedback_note "
            "WHERE feedback_id=%s AND (%s::integer IS NULL OR version<%s) ORDER BY version DESC LIMIT 21",
            (command.feedback_id, command.before_version, command.before_version),
        ).fetchall()
        return {"notes": rows[:20], "next_before_version": rows[19]["version"] if len(rows) > 20 else None}
    prior = conn.execute(
        "SELECT * FROM study_feedback_note WHERE feedback_id=%s AND request_key=%s",
        (command.feedback_id, command.request_key),
    ).fetchone()
    if prior:
        if (
            prior["version"] != command.expected_version + 1
            or prior["note_text"] != command.note_text
            or prior["disposition"] != command.disposition
        ):
            raise StudyError("REQUEST_KEY_CONFLICT")
        return {
            "note": {k: prior[k] for k in ("note_id", "version", "disposition", "note_text", "created_at")}
        }
    version = feedback["note"]["version"] if feedback["note"] else 0
    if command.expected_version != version:
        raise StudyError("FEEDBACK_VERSION_CONFLICT")
    row = conn.execute(
        "INSERT INTO study_feedback_note(note_id,feedback_id,version,request_key,disposition,note_text) "
        "VALUES (%s,%s,%s,%s,%s,%s) RETURNING note_id,version,disposition,note_text,created_at",
        (
            str(uuid.uuid4()),
            command.feedback_id,
            version + 1,
            command.request_key,
            command.disposition,
            command.note_text,
        ),
    ).fetchone()
    store._event(
        conn, run["run_id"], "feedback_note_saved", {"note_id": row["note_id"], "version": version + 1}
    )
    return {"note": row}
