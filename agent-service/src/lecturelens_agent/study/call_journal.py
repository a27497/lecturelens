"""Replay committed model observations, never repeat an outcome-unknown model request."""

import hashlib
import json

from psycopg.types.json import Jsonb

from .store import StudyError, reservation_error
from .telemetry import _span


def slot_key(purpose, ordinal=0):
    span = _span.get()
    return hashlib.sha256(
        json.dumps(
            [
                "slot-v2",
                span["node"],
                span.get("turn"),
                span.get("call_id"),
                ordinal,
                purpose,
                span.get("protocol_retries", 0),
            ],
            sort_keys=True,
        ).encode()
    ).hexdigest()


def operation_key(messages, schemas, purpose):
    span = _span.get()
    ordinal = span.get("model_ordinal", 0)
    span["model_ordinal"] = ordinal + 1
    # Inputs include live budget hints, which change after reserving this call.
    key = slot_key(purpose, ordinal)
    span["model_key"] = key
    return key


def planning_calls(store, run_id, token, fallback):
    if not fallback:
        return fallback
    with store.connect() as conn:
        store._active(conn, run_id, token)
        row = conn.execute(
            "SELECT metadata FROM study_model_call WHERE run_id=%s AND operation_key=%s",
            (run_id, slot_key("decision")),
        ).fetchone()
        # Recreate the planning budget before this slot was reserved. This also
        # freezes budget-dependent feedback tool offerings during node replay.
        return row["metadata"]["attempt"] - 1 if row else fallback


def canonical_messages(detail):
    messages = []
    for message in detail["messages"]:
        content = message.get("content")
        if isinstance(content, str):
            try:
                body = json.loads(content)
            except ValueError:
                body = None
            if isinstance(body, dict):
                if "budget" in body and ("goal" in body or ("question" in body and "learner_answer" in body)):
                    body = {k: v for k, v in body.items() if k != "budget"}
                content = json.dumps(body, sort_keys=True, ensure_ascii=False)
        messages.append({**message, "content": content})
    return messages


def request_fingerprint(detail):
    return hashlib.sha256(
        json.dumps(
            [canonical_messages(detail), detail["schemas"]], sort_keys=True, ensure_ascii=False
        ).encode()
    ).hexdigest()


def stopped(store, conn, run_id, key, code, metadata):
    store._event(
        conn,
        run_id,
        "recovery_stopped",
        {
            "operation_key": key,
            "error_code": code,
            "failure_category": "checkpoint_recovery",
            "policy": "fail_closed",
        },
    )
    # Raise only outside this transaction so the public stop reason commits.
    return {"error": {"code": code}}, metadata


def legacy_observation(store, conn, run_id, key, fingerprint, metadata, detail):
    # Pre-journal Runs retain private model observations in Trace. Import an
    # exact (excluding live budget hints) match without charging their budget.
    starts = conn.execute(
        "SELECT payload,trace_detail FROM study_event WHERE run_id=%s AND event_type='model_started' "
        "AND NOT (payload ? 'operation_key') AND (payload->>'attempt')::integer NOT IN "
        "(SELECT (metadata->>'legacy_attempt')::integer FROM study_model_call WHERE run_id=%s "
        "AND metadata ? 'legacy_attempt') ORDER BY sequence",
        (run_id, run_id),
    ).fetchall()
    for row in starts:
        if not row["trace_detail"]:
            continue
        if request_fingerprint(row["trace_detail"]) != fingerprint:
            if canonical_messages(row["trace_detail"]) == canonical_messages(detail):
                return stopped(store, conn, run_id, key, "MODEL_INPUT_CHANGED", metadata)
            continue
        attempt = row["payload"]["attempt"]
        completed = conn.execute(
            "SELECT event_type,payload,trace_detail FROM study_event WHERE run_id=%s "
            "AND event_type IN ('model_finished','model_failed') AND payload->>'attempt'=%s "
            "ORDER BY sequence DESC LIMIT 1",
            (run_id, str(attempt)),
        ).fetchone()
        response = (completed["trace_detail"] or {}).get("response") if completed else None
        error = (
            {
                "code": completed["payload"]["error_code"],
                "usage": {
                    k: v
                    for k, v in completed["payload"].items()
                    if k in ("prompt_tokens", "completion_tokens")
                },
                "diagnostics": completed["payload"].get("diagnostics", {}),
            }
            if completed and completed["event_type"] == "model_failed"
            else None
        )
        stored = {**row["payload"], "operation_key": key, "legacy_attempt": attempt}
        conn.execute(
            "INSERT INTO study_model_call(run_id,operation_key,metadata,response,error,request_fingerprint) "
            "VALUES (%s,%s,%s,%s,%s,%s)",
            (
                run_id,
                key,
                Jsonb(stored),
                Jsonb(response) if response is not None else None,
                Jsonb(error) if error else None,
                fingerprint,
            ),
        )
        if response is None and error is None:
            return stopped(store, conn, run_id, key, "MODEL_OUTCOME_UNKNOWN", stored)
        store._event(conn, run_id, "model_replayed", stored)
        return {"response": response, "error": error}, stored
    # A legacy charge with no started event has no reliable logical identity.
    row = conn.execute(
        "SELECT model_calls,tool_calls,reserved_tokens,(SELECT count(*) FROM study_event WHERE run_id=%s "
        "AND event_type='model_started') AS starts FROM study_run WHERE run_id=%s",
        (run_id, run_id),
    ).fetchone()
    if row["model_calls"] > row["starts"]:
        if row["model_calls"] >= 6:
            raise reservation_error(row, "model")
        return stopped(store, conn, run_id, key, "MODEL_OUTCOME_UNKNOWN", metadata)
    return None


def begin(store, run_id, token, key, tokens, metadata, detail):
    fingerprint = request_fingerprint(detail)
    with store.connect() as conn:
        run = store._active(conn, run_id, token)
        prior = conn.execute(
            "SELECT * FROM study_model_call WHERE run_id=%s AND operation_key=%s", (run_id, key)
        ).fetchone()
        if prior:
            if prior["request_fingerprint"] != fingerprint:
                return stopped(store, conn, run_id, key, "MODEL_INPUT_CHANGED", prior["metadata"])
            if prior["response"] is None and prior["error"] is None:
                return stopped(store, conn, run_id, key, "MODEL_OUTCOME_UNKNOWN", prior["metadata"])
            store._event(conn, run_id, "model_replayed", {"operation_key": key, **prior["metadata"]})
            return prior, prior["metadata"]
        if conn.execute(
            "SELECT 1 FROM study_model_call WHERE run_id=%s AND request_fingerprint IS NULL LIMIT 1",
            (run_id,),
        ).fetchone():
            return stopped(store, conn, run_id, key, "MODEL_JOURNAL_VERSION_CHANGED", metadata)
        if run["model_calls"]:
            legacy = legacy_observation(store, conn, run_id, key, fingerprint, metadata, detail)
            if legacy:
                return legacy
        error = reservation_error(
            run,
            "model",
            tokens,
            operation_key=key,
            **{k: metadata[k] for k in ("purpose", "review_stage", "reservation") if k in metadata},
            **{k: detail[k] for k in ("node", "checkpoint_id") if k in detail},
        )
        if error:
            raise error
        metadata = {**metadata, "attempt": run["model_calls"] + 1, "operation_key": key}
        conn.execute(
            "UPDATE study_run SET model_calls=model_calls+1,reserved_tokens=reserved_tokens+%s "
            "WHERE run_id=%s",
            (tokens, run_id),
        )
        conn.execute(
            "INSERT INTO study_model_call(run_id,operation_key,metadata,reserved_tokens,request_fingerprint) "
            "VALUES (%s,%s,%s,%s,%s)",
            (run_id, key, Jsonb(metadata), tokens, fingerprint),
        )
        store._event(conn, run_id, "model_started", metadata | {"_trace": detail})
        return None, metadata


def complete(store, run_id, token, key, metadata, payload, *, response=None, error=None):
    with store.connect() as conn:
        store._active(conn, run_id, token)
        conn.execute(
            "UPDATE study_model_call SET response=%s,error=%s WHERE run_id=%s AND operation_key=%s",
            (
                Jsonb(response) if response is not None else None,
                Jsonb(error) if error is not None else None,
                run_id,
                key,
            ),
        )
        store._event(conn, run_id, "model_finished" if error is None else "model_failed", metadata | payload)


def replay(prior):
    if prior.get("error") is not None:
        error = StudyError(prior["error"]["code"])
        error.usage = prior["error"].get("usage", {})
        error.diagnostics = prior["error"].get("diagnostics", {})
        raise error
    return prior["response"]
