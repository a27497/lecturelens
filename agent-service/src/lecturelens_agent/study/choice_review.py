"""Course/revision-scoped review of saved program judgments, never learner inference."""

from .attempts import public_attempt
from .choice import public_question

PAGE_SIZE = 20


def choice_review(conn, command):
    # Select latest versions BEFORE filtering judgments. A later correct answer
    # must remove an earlier wrong version. Counts and page share one snapshot.
    row = conn.execute(
        """WITH latest AS MATERIALIZED (
            SELECT DISTINCT ON (a.artifact_id,a.question_index)
                a.*,r.session_id,r.run_id,
                p.content->'questions'->a.question_index AS question
            FROM study_attempt a
            JOIN study_artifact p ON p.artifact_id=a.artifact_id
            JOIN study_run r ON r.run_id=p.run_id
            JOIN study_session s ON s.session_id=r.session_id
            WHERE s.owner_id=%s AND s.course_id=%s AND s.revision=%s
                AND r.task_kind='practice' AND r.status='succeeded'
            ORDER BY a.artifact_id,a.question_index,a.version DESC
        ), graded AS (
            SELECT * FROM latest WHERE selected_option_id IS NOT NULL
                AND question->>'kind'='choice'
                AND choice_result->'is_correct' IN ('true'::jsonb,'false'::jsonb)
        )
        SELECT
            (SELECT count(*) FROM graded WHERE choice_result->'is_correct'='true'::jsonb) AS correct_count,
            (SELECT count(*) FROM graded WHERE choice_result->'is_correct'='false'::jsonb) AS wrong_count,
            COALESCE((SELECT jsonb_agg(to_jsonb(page) ORDER BY page.created_at DESC,page.attempt_id DESC) FROM (
                SELECT * FROM graded WHERE choice_result->'is_correct'='false'::jsonb
                ORDER BY created_at DESC,attempt_id DESC LIMIT %s OFFSET %s
            ) page),'[]'::jsonb) AS rows""",
        (command.owner_id, command.course_id, command.revision, PAGE_SIZE + 1, command.after),
    ).fetchone()
    items = [
        {
            "session_id": item["session_id"],
            "run_id": item["run_id"],
            "artifact_id": item["artifact_id"],
            "question_index": item["question_index"],
            "question": public_question(item["question"]),
            "attempt": public_attempt(item),
        }
        for item in row["rows"][:PAGE_SIZE]
    ]
    return {
        "revision": command.revision,
        "correct_count": row["correct_count"],
        "wrong_count": row["wrong_count"],
        "items": items,
        "next_after": command.after + PAGE_SIZE if len(row["rows"]) > PAGE_SIZE else None,
    }
