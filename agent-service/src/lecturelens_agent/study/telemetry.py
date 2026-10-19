"""Bounded diagnostics in the existing journal, fenced like every other run effect.

`_trace` is operator-only data: StudyStore strips it from browser EVENTS.
No provider credentials, hidden reasoning or new execution state is stored here.
"""

import time
import uuid
from contextlib import contextmanager
from contextvars import ContextVar

from langchain_core.runnables import RunnableConfig
from pydantic import ValidationError

from .failures import failure_category
from .store import BudgetExceeded, RunStopped, StudyError

_span = ContextVar("study_trace_span", default=None)


def model_detail(messages, schemas, timeout):
    span = _span.get() or {}
    return {
        **{k: span.get(k) for k in ("node", "span_id", "checkpoint_id")},
        "messages": messages,
        "schemas": schemas,
        "timeout_seconds": timeout,
    }


def traced_node(store, run, token, name, function):
    def invoke(state, config: RunnableConfig):
        span = {
            "node": name,
            "span_id": str(uuid.uuid4()),
            "checkpoint_id": config.get("configurable", {}).get("checkpoint_map", {}).get(""),
            "step": config.get("metadata", {}).get("langgraph_step"),
            "call_id": (state.get("pending") or {}).get("call_id"),
        }
        context = _span.set(
            {
                **(_span.get() or {}),
                **span,
                "read_ordinal": 0,
                "model_ordinal": 0,
                "turn": state.get("turn", 0),
                "protocol_retries": state.get("protocol_retries", 0),
                "store": store,
                "run_id": run["run_id"],
                "token": token,
            }
        )
        started = time.monotonic()
        try:
            store.event(
                run["run_id"],
                token,
                "node_started",
                {
                    **span,
                    "_trace": {"pending": state.get("pending"), "evidence_ids": state.get("selected", [])},
                },
            )
            result = function(state)
            store.event(
                run["run_id"],
                token,
                "node_finished",
                {
                    **span,
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                },
            )
            return result
        except (RunStopped, BudgetExceeded):
            # A late result must never be journaled past cancellation/deadline.
            raise
        except Exception as error:
            code = (
                error.code
                if isinstance(error, StudyError)
                else "INVALID_TOOL_ARGUMENTS"
                if isinstance(error, ValidationError)
                else type(error).__name__
            )
            try:
                if failure_category(code) in {"model_tool_selection", "invalid_parameters", "model_protocol"}:
                    store.event(
                        run["run_id"],
                        token,
                        "tool_rejected",
                        {
                            "node": name,
                            "call_id": span["call_id"],
                            "error_code": code,
                            "failure_category": failure_category(code),
                            "policy": "reject_before_execution",
                        },
                    )
                store.event(
                    run["run_id"],
                    token,
                    "node_failed",
                    {
                        **span,
                        "duration_ms": round((time.monotonic() - started) * 1000, 3),
                        "error_code": error.code if isinstance(error, StudyError) else type(error).__name__,
                    },
                )
            except (RunStopped, BudgetExceeded):
                pass
            raise
        finally:
            _span.reset(context)

    return invoke


class TracedAuthority:
    """Fence and trace bounded read attempts; authorization always remains with Java."""

    def __init__(self, authority):
        self.authority = authority

    def close(self):
        if hasattr(self.authority, "close"):
            self.authority.close()

    @contextmanager
    def execution(self, store, run, token, stop):
        context = _span.set(
            {
                "store": store,
                "run_id": run["run_id"],
                "token": token,
                "stop": stop,
                "node": "execute",
                "span_id": None,
                "checkpoint_id": None,
                "call_id": None,
                "read_ordinal": 0,
            }
        )
        try:
            yield
        finally:
            _span.reset(context)

    def read(self, scope, action="CHECK", **arguments):
        from .resilience import execute_read

        return execute_read(self._read_once, _span.get(), scope, action, **arguments)

    def _read_once(self, scope, action="CHECK", **arguments):
        span = _span.get()
        if action == "CHECK" or span is None:
            return self.authority.read(scope, action, **arguments)
        store, run_id, token = (span[k] for k in ("store", "run_id", "token"))
        metadata = {k: span[k] for k in ("node", "span_id", "checkpoint_id", "call_id")}
        metadata["transport"] = getattr(self.authority, "transport", "internal")
        metadata.update(action=action, evidence_call_id=str(uuid.uuid4()))
        store.event(run_id, token, "evidence_started", {**metadata, "_trace": {"arguments": arguments}})
        started = time.monotonic()
        try:
            result = self.authority.read(scope, action, **arguments)
        except Exception as error:
            store.event(
                run_id,
                token,
                "evidence_failed",
                {
                    **metadata,
                    "duration_ms": round((time.monotonic() - started) * 1000, 3),
                    "error_code": error.code if isinstance(error, StudyError) else type(error).__name__,
                },
            )
            raise
        store.event(
            run_id,
            token,
            "evidence_finished",
            {
                **metadata,
                "duration_ms": round((time.monotonic() - started) * 1000, 3),
                "_trace": {"evidence_ids": [e["evidence_id"] for e in result.get("evidence", [])]},
            },
        )
        return result
