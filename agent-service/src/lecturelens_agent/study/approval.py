"""Durable publication gate. Only scoped commands may supply an approval decision."""

import copy
import uuid

from langgraph.types import interrupt
from psycopg.types.json import Jsonb

from .learning_scope import public_status, stored_status
from .store import RunStopped, StudyError

SCHEMA = """
ALTER TABLE study_run ADD COLUMN IF NOT EXISTS approval_required boolean NOT NULL DEFAULT false;
ALTER TABLE study_run ADD COLUMN IF NOT EXISTS approval_seconds double precision;
DROP INDEX IF EXISTS study_one_active_run;
CREATE UNIQUE INDEX study_one_active_run ON study_run(session_id)
    WHERE status IN ('queued','running','awaiting_approval');
CREATE TABLE IF NOT EXISTS study_approval (
    run_id text PRIMARY KEY REFERENCES study_run ON DELETE CASCADE,
    call_id text NOT NULL, kind text NOT NULL CHECK (kind IN ('practice','feedback')),
    draft jsonb NOT NULL, decision text CHECK (decision IN ('approve','edit','reject')),
    request_key text, edited_text text, decided_by bigint, decided_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(), published_at timestamptz
);
CREATE TABLE IF NOT EXISTS study_reservation (
    run_id text NOT NULL REFERENCES study_run ON DELETE CASCADE,
    kind text NOT NULL, operation_key text NOT NULL, PRIMARY KEY(run_id,kind,operation_key)
);
CREATE TABLE IF NOT EXISTS study_model_call (
    run_id text NOT NULL REFERENCES study_run ON DELETE CASCADE,
    operation_key text NOT NULL, metadata jsonb NOT NULL, response jsonb, error jsonb,
    reserved_tokens integer NOT NULL DEFAULT 0,
    PRIMARY KEY(run_id,operation_key)
);
ALTER TABLE study_model_call ADD COLUMN IF NOT EXISTS reserved_tokens integer NOT NULL DEFAULT 0;
ALTER TABLE study_model_call ADD COLUMN IF NOT EXISTS request_fingerprint text;
"""


def stage(store, conn, run, call_id, result, artifact, feedback):
    kind = "practice" if artifact is not None else "feedback"
    conn.execute(
        "INSERT INTO study_approval(run_id,call_id,kind,draft) VALUES (%s,%s,%s,%s) ON CONFLICT DO NOTHING",
        (run["run_id"], call_id, kind, Jsonb(artifact if artifact is not None else feedback)),
    )
    store._event(conn, run["run_id"], "approval_draft_saved", {"kind": kind, "call_id": call_id})
    # The graph's done flag denotes an accepted candidate, not a published artifact.
    field = "artifact_id" if kind == "practice" else "feedback_id"
    identity = f"{run['run_id']}:{call_id}" if kind == "practice" else f"feedback:{run['run_id']}"
    return result | {field: str(uuid.uuid5(uuid.NAMESPACE_URL, identity))}


def approval_view(conn, run):
    row = conn.execute(
        "SELECT kind,draft,decision,decided_by,decided_at,published_at FROM study_approval WHERE run_id=%s",
        (run["run_id"],),
    ).fetchone()
    if not row:
        return None
    if public_status(run["status"]) == "awaiting_approval":
        # Answers, scoring points and review diagnostics remain private even in previews.
        draft = copy.deepcopy(row.pop("draft"))
        if row["kind"] == "practice":
            draft.pop("quality_check", None)
            draft["questions"] = [{k: q[k] for k in ("question", "evidence_ids")} for q in draft["questions"]]
        row["preview"] = draft
    else:
        row.pop("draft")
    return row


def decide(store, conn, run, command):
    row = conn.execute("SELECT * FROM study_approval WHERE run_id=%s FOR UPDATE", (run["run_id"],)).fetchone()
    if not row:
        raise StudyError("APPROVAL_NOT_READY")
    if row["decision"]:
        if (row["request_key"], row["decision"], row["edited_text"]) != (
            command.request_key,
            command.approval_decision,
            command.approval_edit,
        ):
            raise StudyError("APPROVAL_DECISION_CONFLICT")
        return
    if public_status(run["status"]) != "awaiting_approval":
        raise StudyError("APPROVAL_NOT_WAITING")
    conn.execute(
        "UPDATE study_approval SET decision=%s,request_key=%s,edited_text=%s,decided_by=%s,decided_at=now() "
        "WHERE run_id=%s",
        (
            command.approval_decision,
            command.request_key,
            command.approval_edit,
            command.owner_id,
            run["run_id"],
        ),
    )
    store._event(
        conn,
        run["run_id"],
        "approval_decided",
        {
            "decision": command.approval_decision,
            "actor_id": command.owner_id,
            "edited": command.approval_decision == "edit",
            "request_key": command.request_key,
        },
    )
    # Approval is durable before resuming; the worker rechecks Java revision/deletion.
    conn.execute(
        "UPDATE study_run SET status=%s,worker_token=NULL WHERE run_id=%s",
        (stored_status(run, "queued"), run["run_id"]),
    )


def pause(store, run_id, token):
    with store.connect() as conn:
        run = store._active(conn, run_id, token)
        row = conn.execute("SELECT * FROM study_approval WHERE run_id=%s", (run_id,)).fetchone()
        if not row:
            raise StudyError("APPROVAL_DRAFT_MISSING")
        if row["decision"]:
            return row
        conn.execute(
            "UPDATE study_run SET status=%s,approval_seconds="
            "GREATEST(0,extract(epoch FROM deadline-now())),deadline=NULL WHERE run_id=%s",
            (stored_status(run, "awaiting_approval"), run_id),
        )
        store._event(conn, run_id, "approval_waiting", {"kind": row["kind"]})
        return row


def publish(store, run_id, token):
    with store.connect() as conn:
        run = store._active(conn, run_id, token)
        row = conn.execute("SELECT * FROM study_approval WHERE run_id=%s FOR UPDATE", (run_id,)).fetchone()
        if not row or not row["decision"]:
            raise StudyError("APPROVAL_REQUIRED")
        if row["decision"] == "reject":
            store._finish(conn, run_id, "failed", "APPROVAL_REJECTED")
            return False
        if row["published_at"]:
            return True
        content = copy.deepcopy(row["draft"])
        if row["decision"] == "edit":
            # Human publication text is attributed separately from model-validated fields.
            # Computed answers, questions, citations and evidence IDs cannot be replaced.
            field = "explanation" if row["kind"] == "practice" else "human_guidance"
            content[field] = row["edited_text"]
            content["human_edited"] = True
            content["edited_by"] = row["decided_by"]
        if row["kind"] == "practice":
            artifact_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"{run_id}:{row['call_id']}"))
            conn.execute(
                "INSERT INTO study_artifact VALUES (%s,%s,%s,%s,now()) ON CONFLICT DO NOTHING",
                (artifact_id, run_id, row["call_id"], Jsonb(content)),
            )
            store._event(
                conn,
                run_id,
                "artifact_created",
                {"artifact_id": artifact_id, "question_count": len(content["questions"])},
            )
        else:
            from .feedback_store import save_feedback

            feedback_id = save_feedback(conn, run, content)
            store._event(conn, run_id, "feedback_created", {"feedback_id": feedback_id})
        conn.execute("UPDATE study_approval SET published_at=now() WHERE run_id=%s", (run_id,))
        store._event(conn, run_id, "approval_published", {"kind": row["kind"], "decision": row["decision"]})
        return True


def add_gate(graph, runtime, run, token):
    def approval(state):
        if runtime.stop.is_set():
            raise RunStopped()
        runtime.authority.read(run)
        row = pause(runtime.store, run["run_id"], token)
        if not row["decision"]:
            # Ignore resume payloads: the authenticated, persisted decision is authoritative.
            interrupt({"kind": row["kind"], "run_id": run["run_id"]})
            runtime.store.guard(run["run_id"], token)
        runtime.authority.read(run)
        return {"done": publish(runtime.store, run["run_id"], token)}

    graph.add_node("approval", approval)
