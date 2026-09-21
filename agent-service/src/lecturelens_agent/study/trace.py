"""Operator trace projection. No new tables and no checkpoint/state mutation.

Access requires both an operator database connection and a live authenticated Java
READ, before and after collecting private data. This is deliberately not a browser API.
"""

from datetime import datetime, timezone

from langgraph.checkpoint.postgres import PostgresSaver

from .store import StudyError

SCOPE = ("owner_id", "course_id", "revision")
RUN_FIELDS = (
    "run_id",
    "session_id",
    "goal",
    "status",
    "error_code",
    "task_kind",
    "model_mode",
    "model_calls",
    "tool_calls",
    "reserved_tokens",
    "deadline",
    "created_at",
    "finished_at",
)
TAXONOMY = {
    "retrieval": "Search/index failure or independently verified missing relevant evidence.",
    "tool selection": "Wrong/missing tool, invalid arguments or tool protocol contract.",
    "context": "Evidence was available but selection, window or citation context was inadequate.",
    "generation": "Answer, practice or feedback failed grounded quality/goal checks.",
    "permission-state": "Ownership, revision, deletion, cancellation or business-state fence.",
    "infra": "Provider/network/database, timeout or execution budget failure.",
}


def classify(code):
    """A conservative symptom label, not an assertion of semantic root cause."""
    if not code:
        return None
    if any(x in code for x in ("SCOPE", "STALE", "CHANGED", "CANCEL", "NOT_FOUND", "NOT_READY", "CONFLICT")):
        return "permission-state"
    if code.startswith("MCP_"):
        return "infra"
    if any(x in code for x in ("TIMEOUT", "DEADLINE", "BUDGET", "UNAVAILABLE", "MODE_CHANGED")):
        return "infra"
    if any(x in code for x in ("TOOL", "SEARCH_REQUIRED", "MODEL_FEEDBACK_CONTRACT")):
        return "tool selection"
    if any(x in code for x in ("RETRIEV", "INDEX")):
        return "retrieval"
    if any(x in code for x in ("CITATION", "CONTEXT", "EVIDENCE_LIMIT")):
        return "context"
    if any(x in code for x in ("QUALITY", "REPAIR_EXHAUSTED", "ARTIFACT")):
        return "generation"
    return "infra"


def metrics(run, events):
    models = [e["payload"] for e in events if e["event_type"] in {"model_finished", "model_failed"}]
    starts = [e for e in events if e["event_type"] == "model_started"]
    tools = [
        e["payload"]
        for e in events
        if e["event_type"] in {"node_finished", "node_failed"}
        and e["payload"].get("node") in {"tool", "feedback_tool"}
    ]
    searches = [
        e["payload"]
        for e in events
        if e["event_type"] in {"evidence_finished", "evidence_failed"}
        and e["payload"].get("action") == "SEARCH"
    ]
    search_starts = sum(
        e["event_type"] == "evidence_started" and e["payload"].get("action") == "SEARCH" for e in events
    )
    observed = any(e["event_type"] == "node_started" for e in events)

    def tokens(key):
        known = [m[key] for m in models if isinstance(m.get(key), int)]
        missing = max(run["model_calls"], len(starts)) - len(known)
        return {
            "total": sum(known) if missing == 0 else None,
            "known_total": sum(known),
            "missing_calls": missing,
        }

    return {
        "input_tokens": tokens("prompt_tokens"),
        "output_tokens": tokens("completion_tokens"),
        "reserved_tokens_are_not_usage": run["reserved_tokens"],
        "usage_origin": "historical_recording"
        if any(
            e["event_type"] == "replay_linked" and e["payload"].get("mode") == "recorded_model_response"
            for e in events
        )
        else "provider_reported",
        "model_calls": run["model_calls"],
        "logical_tool_calls": run["tool_calls"],
        "llm_latency_ms": [m["duration_ms"] for m in models if "duration_ms" in m],
        "llm_unfinished_calls": len(starts) - len(models),
        "tool_node_latency_inclusive_ms": [t["duration_ms"] for t in tools] if observed else None,
        "retrieval_latency_ms": [s["duration_ms"] for s in searches] if observed else None,
        "tool_node_unfinished_calls": sum(
            e["event_type"] == "node_started" and e["payload"].get("node") in {"tool", "feedback_tool"}
            for e in events
        )
        - len(tools)
        if observed
        else None,
        "retrieval_calls": search_starts if observed else None,
        "retrieval_unfinished_calls": search_starts - len(searches) if observed else None,
        "protocol_retries": sum(e["event_type"] == "protocol_retry_scheduled" for e in events),
        "resumptions": sum(e["event_type"] == "run_resumed" for e in events),
        "notes": "Tool node wall time includes guards, nested LLM and evidence calls; do not add these times. "
        "Missing historical/cancelled-call measurements are unknown, never zero or estimates.",
    }


class RunTrace:
    def __init__(self, store, gateway):
        self.store, self.gateway = store, gateway

    def locate(self, run_id):
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT r.*,s.owner_id,s.course_id,s.revision FROM study_run r "
                "JOIN study_session s USING(session_id) WHERE r.run_id=%s",
                (run_id,),
            ).fetchone()
        if not row:
            raise StudyError("RUN_NOT_FOUND", 404)
        return row

    def authorize(self, row):
        result = self.gateway.command(
            row["course_id"],
            {
                "operation": "READ",
                "session_id": row["session_id"],
                "run_id": row["run_id"],
            },
        )
        if (
            any(result.get(k) != row[k] for k in SCOPE)
            or result.get("run", {}).get("run_id") != row["run_id"]
        ):
            raise StudyError("TRACE_SCOPE_MISMATCH", 403)
        return result

    def read(self, run_id):
        row = self.locate(run_id)
        self.authorize(row)
        with self.store.connect() as conn:
            events = conn.execute(
                "SELECT sequence,event_type, payload || CASE WHEN trace_detail IS NULL THEN '{}'::jsonb "
                "ELSE jsonb_build_object('_trace',trace_detail) END AS payload,created_at "
                "FROM study_event WHERE run_id=%s ORDER BY sequence",
                (run_id,),
            ).fetchall()
            tools = conn.execute(
                "SELECT call_id,tool_name,arguments,result FROM study_tool_result WHERE run_id=%s ORDER BY call_id",
                (run_id,),
            ).fetchall()
            artifact = conn.execute(
                "SELECT artifact_id,content FROM study_artifact WHERE run_id=%s", (run_id,)
            ).fetchone()
            feedback = conn.execute(
                "SELECT content FROM study_feedback WHERE run_id=%s", (run_id,)
            ).fetchone()
        checkpoints = []
        with PostgresSaver.from_conn_string(self.store.dsn) as saver:
            for saved in saver.list({"configurable": {"thread_id": row["session_id"]}}):
                values = saved.checkpoint["channel_values"]
                initial = values.get("__start__") or {}
                belongs = initial.get("run_id") or values.get("run_id")
                if belongs != run_id:
                    continue
                checkpoints.append(
                    {
                        "checkpoint_id": saved.config["configurable"]["checkpoint_id"],
                        "parent_checkpoint_id": (saved.parent_config or {})
                        .get("configurable", {})
                        .get("checkpoint_id"),
                        "created_at": saved.checkpoint["ts"],
                        "step": saved.metadata.get("step"),
                        "state": {"__start__": initial} if initial else values,
                        "pending_writes": saved.pending_writes,
                    }
                )
        # Do not release data if authority changed during projection, or deletion purged it.
        current = self.locate(run_id)
        if any(current[k] != row[k] for k in SCOPE):
            raise StudyError("TRACE_SCOPE_MISMATCH", 403)
        self.authorize(current)
        failure = classify(current["error_code"])
        return {
            "schema_version": 1,
            "captured_at": datetime.now(timezone.utc),
            "scope": {k: current[k] for k in SCOPE},
            "run": {k: current[k] for k in RUN_FIELDS},
            "model_selection": {
                role: {k: config.get(k) for k in ("connection_id", "name", "version", "model")}
                for role, config in (current.get("model_config") or {}).items()
            },
            "question": current["goal"],
            "events": events,
            "tools": tools,
            "checkpoints": list(reversed(checkpoints)),
            "final_answer": (artifact or {}).get("content") if current["status"] == "succeeded" else None,
            "final_feedback": (feedback or {}).get("content") if current["status"] == "succeeded" else None,
            "failure_type": failure,
            "failure_attribution": {
                "kind": "rule_based_symptom",
                "error_code": current["error_code"],
                "semantic_root_cause_requires_review": bool(failure),
            },
            "metrics": metrics(current, events),
            "limitations": "Historical runs have only the fields recorded at execution time. "
            "Checkpoints are original persisted state, never regenerated. "
            "Active runs are a non-atomic observation; read a terminal run for a final trace.",
        }


def compare(before, after):
    if before["scope"] != after["scope"] or before["question"] != after["question"]:
        raise StudyError("REPLAY_SCOPE_OR_GOAL_CHANGED")
    return {
        "before_run_id": before["run"]["run_id"],
        "after_run_id": after["run"]["run_id"],
        "before_status": before["run"]["status"],
        "after_status": after["run"]["status"],
        "before_failure_type": before["failure_type"],
        "after_failure_type": after["failure_type"],
        "before_metrics": before["metrics"],
        "after_metrics": after["metrics"],
        "before_final_answer": before["final_answer"],
        "after_final_answer": after["final_answer"],
        "model_selection_changed": before["model_selection"] != after["model_selection"],
        "quality_pass": None,
        "note": "Execution success is not a semantic quality pass. Live reruns may differ stochastically.",
    }
