"""A fresh authorized attempt, never a rewind of a terminal run or checkpoint."""

import hashlib

from .store import TERMINAL, StudyError
from .trace import SCOPE


def start_replay(trace, source_run_id, request_key, *, mode="live_rerun"):
    if mode not in {"live_rerun", "recorded_model_response"}:
        raise StudyError("INVALID_REPLAY_MODE", 422)
    if not request_key or len(request_key) > 128:
        raise StudyError("REQUEST_KEY_REQUIRED", 422)
    source = trace.locate(source_run_id)
    trace.authorize(source)
    if source["status"] not in TERMINAL or source["task_kind"] != "practice":
        raise StudyError("REPLAY_REQUIRES_TERMINAL_PRACTICE")
    # An empty session avoids inheriting unrelated post-failure conversation.
    # Historical context is visible in Trace, but is not silently injected as current authority.
    key = hashlib.sha256(f"replay-v1:{mode}:{source_run_id}:{request_key}".encode()).hexdigest()
    session = trace.gateway.command(source["course_id"], {"operation": "CREATE_SESSION", "request_key": key})
    if any(session.get(k) != source[k] for k in SCOPE):
        raise StudyError("REPLAY_SCOPE_CHANGED", 403)
    # Revalidate the source immediately before START, including its old revision.
    trace.authorize(source)
    result = trace.gateway.command(
        source["course_id"],
        {
            "operation": "START",
            "session_id": session["session_id"],
            "request_key": key,
            "goal": source["goal"],
        },
    )
    target = trace.locate(result["run"]["run_id"])
    trace.authorize(target)
    if any(target[k] != source[k] for k in SCOPE) or target["goal"] != source["goal"]:
        raise StudyError("REPLAY_SCOPE_CHANGED", 403)
    with trace.store.connect() as conn:
        row = conn.execute(
            "SELECT run_id FROM study_run WHERE run_id=%s FOR UPDATE", (target["run_id"],)
        ).fetchone()
        if not row:
            raise StudyError("RUN_NOT_FOUND", 404)
        trace.store._event(
            conn,
            target["run_id"],
            "replay_linked",
            {
                "source_run_id": source_run_id,
                "mode": mode,
                "fresh_session": True,
            },
        )
    return result
