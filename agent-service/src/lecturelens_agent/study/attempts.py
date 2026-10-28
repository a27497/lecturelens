"""Immutable learner answers. They are facts, never inferred grades or learning memory."""

import uuid

from psycopg.types.json import Jsonb

from .store import StudyError

SCHEMA = """
CREATE TABLE IF NOT EXISTS study_attempt (
    attempt_id text PRIMARY KEY,
    artifact_id text NOT NULL REFERENCES study_artifact ON DELETE CASCADE,
    question_index integer NOT NULL CHECK (question_index BETWEEN 0 AND 1),
    version integer NOT NULL CHECK (version > 0),
    request_key text NOT NULL,
    answer_text text NOT NULL CHECK (length(btrim(answer_text)) BETWEEN 1 AND 4000),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(artifact_id,question_index,version),
    UNIQUE(artifact_id,request_key)
);
ALTER TABLE study_attempt ADD COLUMN IF NOT EXISTS selected_option_id text;
ALTER TABLE study_attempt ADD COLUMN IF NOT EXISTS choice_result jsonb;
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname='study_attempt_choice_pair' AND conrelid='study_attempt'::regclass) THEN
        ALTER TABLE study_attempt ADD CONSTRAINT study_attempt_choice_pair CHECK (
            (selected_option_id IS NULL AND choice_result IS NULL) OR
            (selected_option_id IS NOT NULL AND length(btrim(selected_option_id))>0 AND choice_result IS NOT NULL
             AND choice_result ?& ARRAY['is_correct','correct_option_id','citations']
             AND jsonb_typeof(choice_result->'is_correct')='boolean'
             AND jsonb_typeof(choice_result->'correct_option_id')='string'
             AND jsonb_typeof(choice_result->'citations')='array'));
    END IF;
END $$;
"""
PUBLIC_COLUMNS = (
    "attempt_id,artifact_id,question_index,version,answer_text,created_at,selected_option_id,choice_result"
)


def public_attempt(row):
    return {
        k: row[k]
        for k in PUBLIC_COLUMNS.split(",")
        if k not in {"selected_option_id", "choice_result"} or row[k] is not None
    }


def current_attempts(conn, artifact_id):
    rows = conn.execute(
        f"SELECT DISTINCT ON (question_index) {PUBLIC_COLUMNS} FROM study_attempt "
        "WHERE artifact_id=%s ORDER BY question_index,version DESC",
        (artifact_id,),
    ).fetchall()
    return [public_attempt(row) for row in rows]


def attempt_command(store, conn, run, command):
    # The caller has locked the owner/course/revision/session and run before entering.
    artifact = conn.execute(
        "SELECT content FROM study_artifact WHERE artifact_id=%s AND run_id=%s",
        (command.artifact_id, run["run_id"]),
    ).fetchone()
    if not artifact or run["status"] != "succeeded":
        raise StudyError("ARTIFACT_NOT_FOUND_OR_STALE", 404)
    questions = artifact["content"]["questions"]
    if command.question_index >= len(questions):
        raise StudyError("QUESTION_NOT_FOUND", 404)
    if command.operation == "ATTEMPT_HISTORY":
        rows = conn.execute(
            f"SELECT {PUBLIC_COLUMNS} FROM study_attempt WHERE artifact_id=%s AND question_index=%s "
            "AND (%s::integer IS NULL OR version<%s) ORDER BY version DESC LIMIT 21",
            (command.artifact_id, command.question_index, command.before_version, command.before_version),
        ).fetchall()
        return {
            "attempts": [public_attempt(row) for row in rows[:20]],
            "next_before_version": rows[19]["version"] if len(rows) > 20 else None,
        }
    question = questions[command.question_index]
    choice_result = None
    answer_text = command.answer_text
    if question.get("kind") == "choice":
        from .choice import judge

        answer_text, choice_result = judge(
            question, command.selected_option_id, artifact["content"]["citations"]
        )
    elif command.selected_option_id is not None:
        raise StudyError("OPEN_ANSWER_REQUIRES_TEXT", 422)
    prior = conn.execute(
        "SELECT * FROM study_attempt WHERE artifact_id=%s AND request_key=%s",
        (command.artifact_id, command.request_key),
    ).fetchone()
    if prior:
        if (
            prior["answer_text"] != answer_text
            or prior["selected_option_id"] != command.selected_option_id
            or prior["question_index"] != command.question_index
            or prior["version"] != command.expected_version + 1
        ):
            raise StudyError("REQUEST_KEY_CONFLICT")
        return {"attempt": public_attempt(prior)}
    latest = conn.execute(
        "SELECT COALESCE(MAX(version),0) AS version FROM study_attempt WHERE artifact_id=%s AND question_index=%s",
        (command.artifact_id, command.question_index),
    ).fetchone()["version"]
    if latest != command.expected_version:
        raise StudyError("ATTEMPT_VERSION_CONFLICT")
    saved = conn.execute(
        "INSERT INTO study_attempt(attempt_id,artifact_id,question_index,version,request_key,answer_text,selected_option_id,choice_result) "
        f"VALUES (%s,%s,%s,%s,%s,%s,%s,%s) RETURNING {PUBLIC_COLUMNS}",
        (
            str(uuid.uuid4()),
            command.artifact_id,
            command.question_index,
            latest + 1,
            command.request_key,
            answer_text,
            command.selected_option_id,
            Jsonb(choice_result) if choice_result is not None else None,
        ),
    ).fetchone()
    store._event(
        conn,
        run["run_id"],
        "attempt_saved",
        {
            "attempt_id": saved["attempt_id"],
            "question_index": command.question_index,
            "version": latest + 1,
        },
    )
    return {"attempt": public_attempt(saved)}
