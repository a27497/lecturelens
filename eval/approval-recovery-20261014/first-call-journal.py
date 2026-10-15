"""Replay committed model observations, never repeat an outcome-unknown model request."""

import hashlib
import json

from psycopg.types.json import Jsonb

from .store import StudyError
from .telemetry import _span


def operation_key(messages, schemas, purpose):
    span = _span.get()
    ordinal = span.get("model_ordinal", 0)
    span["model_ordinal"] = ordinal + 1
    return hashlib.sha256(
        json.dumps(
            [span["node"], span.get("turn"), span.get("call_id"), ordinal, purpose, messages, schemas],
            sort_keys=True,
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def begin(store, run_id, token, key, tokens, metadata, detail):
    with store.connect() as conn:
        run = store._active(conn, run_id, token)
        prior = conn.execute(
            "SELECT * FROM study_model_call WHERE run_id=%s AND operation_key=%s", (run_id, key)
        ).fetchone()
        if prior:
            if prior["response"] is None and prior["error"] is None:
                store._event(
                    conn,
                    run_id,
                    "recovery_stopped",
                    {
                        "operation_key": key,
                        "error_code": "MODEL_OUTCOME_UNKNOWN",
                        "failure_category": "checkpoint_recovery",
                        "policy": "fail_closed",
                    },
                )
                # Commit the public stop reason before raising outside the transaction.
                return {"error": {"code": "MODEL_OUTCOME_UNKNOWN"}}, prior["metadata"]
            store._event(conn, run_id, "model_replayed", {"operation_key": key, **prior["metadata"]})
            return prior, prior["metadata"]
        if run["model_calls"] >= 6 or run["reserved_tokens"] + tokens > 64000:
            from .store import BudgetExceeded

            raise BudgetExceeded()
        metadata = {**metadata, "attempt": run["model_calls"] + 1, "operation_key": key}
        conn.execute(
            "UPDATE study_run SET model_calls=model_calls+1,reserved_tokens=reserved_tokens+%s "
            "WHERE run_id=%s",
            (tokens, run_id),
        )
        conn.execute(
            "INSERT INTO study_model_call(run_id,operation_key,metadata,reserved_tokens) VALUES (%s,%s,%s,%s)",
            (run_id, key, Jsonb(metadata), tokens),
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
