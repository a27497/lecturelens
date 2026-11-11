"""Read-only practice review derived from existing immutable learner records."""

from .feedback_store import feedback_view
from .learning_scope import public_status


def practice_results(conn, artifact_id, question_count, attempts):
    """One bounded row per question; the recent-feedback window cannot imply missing feedback."""
    latest = {row["question_index"]: row for row in attempts}
    results = []
    for index in range(question_count):
        attempt = latest.get(index)
        rows = conn.execute(
            "SELECT r.run_id,r.status,r.error_code,a.attempt_id,a.question_index,a.version AS answer_version "
            "FROM study_run r JOIN study_attempt a ON r.source_attempt_id=a.attempt_id "
            "JOIN study_feedback f ON f.run_id=r.run_id "
            "WHERE a.artifact_id=%s AND a.question_index=%s AND r.status='succeeded' "
            "ORDER BY (a.attempt_id=%s) DESC,r.created_at DESC,r.run_id DESC LIMIT 1",
            (artifact_id, index, attempt["attempt_id"] if attempt else None),
        ).fetchall()
        feedback_run = None
        if rows:
            row = rows[0]
            feedback_run = row | {"feedback": feedback_view(conn, row["run_id"])}
        pending = conn.execute(
            "SELECT r.status,a.version AS answer_version FROM study_run r JOIN study_attempt a ON r.source_attempt_id=a.attempt_id "
            "WHERE a.artifact_id=%s AND a.question_index=%s ORDER BY r.created_at DESC,r.run_id DESC LIMIT 1",
            (artifact_id, index),
        ).fetchone()
        results.append(
            {
                "question_index": index,
                "attempt": attempt,
                "feedback_run": feedback_run,
                "latest_feedback_status": public_status(pending["status"]) if pending else None,
                "latest_feedback_answer_version": pending["answer_version"] if pending else None,
            }
        )
    return results
