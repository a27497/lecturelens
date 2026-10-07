"""Bounded diagnostics in the existing journal, fenced like every other run effect.

`_trace` is operator-only data: StudyStore strips it from browser EVENTS.
No provider credentials, hidden reasoning or new execution state is stored here.
"""

import time
import uuid
from contextvars import ContextVar

from langchain_core.runnables import RunnableConfig

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
            {**span, "store": store, "run_id": run["run_id"], "token": token, "session_id": run["session_id"]}
        )
        started = time.monotonic()
        try:
            detail = {"pending": state.get("pending"), "evidence_ids": state.get("selected", [])}
            previous = (state.get("history") or [{}])[-1]
            quality = previous.get("result", {}).get("quality", {})
            if (
                name == "decide"
                and previous.get("tool") == "create_explanation"
                and "unsupported_explanation" in quality.get("issues", [])
            ):
                from .review_diagnostics import atomic_review_detail, enabled, semantic_review_detail

                if enabled({"review_mode": "answer_support_v1"}):
                    try:
                        detail["semantic_review"] = {
                            "review_call_id": previous["call_id"],
                            **(
                                atomic_review_detail
                                if quality.get("atomic_assessments")
                                else semantic_review_detail
                            )(
                                previous["arguments"]["explanation"],
                                quality.get("atomic_assessments")
                                or quality.get("explanation_assessments", []),
                                revision_triggered=True,
                            ),
                        }
                    except Exception as error:  # noqa: BLE001 -- observation cannot change execution
                        detail["semantic_capture_failed"] = type(error).__name__
            store.event(
                run["run_id"],
                token,
                "node_started",
                {
                    **span,
                    "_trace": detail,
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
            try:
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
    """Observe actual SEARCH/READ/WINDOW calls; CHECK still uses the original authority."""

    def __init__(self, authority):
        self.authority = authority

    def close(self):
        if hasattr(self.authority, "close"):
            self.authority.close()

    def read(self, scope, action="CHECK", **arguments):
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
