"""Read-only operator accounting from recorded metadata, never private task content.

This is execution accounting, not semantic evaluation. Cohorts retain source,
implementation, model mode and scenario identity. Missing measurements stay null.
"""

import argparse
import hashlib
import json
import math
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

from .contracts import TOOLS as PRACTICE_TOOLS
from .failures import failure_category
from .feedback import TOOLS as FEEDBACK_TOOLS
from .trace import metrics as trace_metrics

RUN_KEYS = (
    "run_id",
    "session_id",
    "status",
    "error_code",
    "model_mode",
    "task_kind",
    "model_calls",
    "tool_calls",
    "reserved_tokens",
    "created_at",
    "finished_at",
)
EVENT_KEYS = (
    "call_id",
    "tool",
    "node",
    "span_id",
    "evidence_call_id",
    "action",
    "attempt",
    "purpose",
    "duration_ms",
    "prompt_tokens",
    "completion_tokens",
    "error_code",
    "failure_category",
    "mode",
)
EVENT_TYPES = {
    "model_started",
    "model_finished",
    "model_failed",
    "tool_started",
    "tool_finished",
    "node_started",
    "node_finished",
    "node_failed",
    "evidence_started",
    "evidence_finished",
    "evidence_failed",
    "tool_read_failed",
    "tool_rejected",
    "dependency_stopped",
    "tool_retry_started",
    "tool_retry_backoff",
    "protocol_retry_scheduled",
    "run_resumed",
    "replay_linked",
}
OUTCOMES = ("success", "abstention", "failed", "cancelled", "budget_exceeded", "nonterminal", "unknown")


def timestamp(value):
    if value is None:
        return None
    parsed = value if isinstance(value, datetime) else datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("Timezone required")
    return parsed.astimezone(timezone.utc)


def number(value):
    return type(value) in {int, float} and math.isfinite(value) and value >= 0


def project(row, source):
    """Whitelist before accounting/export; never retain arguments, goals or model prose."""
    run = {key: row["run"][key] for key in RUN_KEYS if key in row["run"]}
    if not run.get("run_id"):
        raise ValueError("Missing run_id")
    for key in ("model_calls", "tool_calls", "reserved_tokens"):
        if key in run and (type(run[key]) is not int or run[key] < 0):
            raise ValueError("Invalid persisted counter")
    for key in ("created_at", "finished_at"):
        run[key] = timestamp(run.get(key))
    events = []
    for event in row.get("public_events", row.get("events", [])):
        if event["event_type"] not in EVENT_TYPES:
            continue
        payload = {key: value for key, value in event.get("payload", {}).items() if key in EVENT_KEYS}
        for key in ("duration_ms", "prompt_tokens", "completion_tokens"):
            if key in payload and (
                not number(payload[key]) or (key != "duration_ms" and type(payload[key]) is not int)
            ):
                raise ValueError("Invalid recorded measurement")
        events.append({"event_type": event["event_type"], "payload": payload})
    identity = row.get("identity", row.get("runtime"))
    identity_hash = (
        hashlib.sha256(json.dumps(identity, sort_keys=True).encode()).hexdigest() if identity else None
    )
    artifact_kind = row.get("artifact_kind")
    routing = {
        role: {key: config[key] for key in ("connection_id", "version", "model") if key in config}
        for role, config in (row["run"].get("model_selection") or {}).items()
    }
    if artifact_kind is None:
        artifact_kind = (row.get("artifact") or row.get("feedback") or {}).get("kind")
    elapsed = row.get("elapsed_ms")
    if elapsed is None and number(row.get("elapsed_seconds")):
        elapsed = row["elapsed_seconds"] * 1000
    if elapsed is not None and not number(elapsed):
        raise ValueError("Invalid execution latency")
    return {
        "run": run,
        "events": events,
        "artifact_kind": artifact_kind,
        "elapsed_ms": elapsed,
        "mcp_events": [
            {key: e[key] for key in ("tool", "action", "duration_ms", "error_code") if key in e}
            for e in row.get("mcp_events", [])
            if e.get("event") == "tools/call"
        ],
        "has_mcp_events": "mcp_events" in row,
        "cohort": {
            "source": source,
            "label": row.get("label", "saved"),
            "source_sha256": row.get("source_sha256"),
            "fixture_sha256": row.get("fixture_sha256"),
            "dataset_sha256": row.get("dataset_sha256", (identity or {}).get("dataset_sha256")),
            "identity_sha256": identity_hash,
            "routing_sha256": hashlib.sha256(json.dumps(routing, sort_keys=True).encode()).hexdigest()
            if routing
            else None,
            "model_mode": run.get("model_mode"),
            "task_kind": run.get("task_kind"),
            "scenario": row.get("scenario", "unspecified"),
        },
    }


def load_records(paths):
    rows, sources = [], []
    for path in paths:
        data = path.read_bytes()
        source = str(path)
        parsed = [json.loads(line) for line in data.splitlines() if line.strip()]
        rows.extend(project(row, source) for row in parsed)
        sources.append({"source": source, "sha256": hashlib.sha256(data).hexdigest(), "records": len(parsed)})
    return rows, sources


def load_database(dsn, *, since=None, until=None, run_ids=()):
    """One immutable snapshot; SQL never selects private payload fields or task content.

    The caller needs operator DB access, preferably a SELECT-only role. This does
    not export RunTrace's private replay data or offer a browser authorization API.
    """
    rows = []
    filters, params = [], []
    for boundary, operator in ((since, ">="), (until, "<")):
        if boundary is not None:
            filters.append(f"r.created_at {operator} %s")
            params.append(boundary)
    if run_ids:
        filters.append("r.run_id = ANY(%s)")
        params.append(list(run_ids))
    where = " WHERE " + " AND ".join(filters) if filters else ""
    with psycopg.connect(dsn, row_factory=dict_row) as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        conn.execute("SET LOCAL statement_timeout='60s'")
        runs = conn.execute(
            "SELECT "
            + ",".join("r." + key for key in RUN_KEYS)
            + ",(SELECT jsonb_object_agg(role,jsonb_build_object('model',config->>'model', "
            "'version',config->'version','connection_id',config->>'connection_id')) "
            "FROM jsonb_each(COALESCE(r.model_config,'{}'::jsonb)) AS c(role,config)) AS model_selection, "
            "a.content->>'kind' AS artifact_kind FROM study_run r "
            "LEFT JOIN study_artifact a USING(run_id)" + where + " ORDER BY r.created_at,r.run_id",
            params,
        ).fetchall()
        # Feedback is optional on older practice-only databases.
        feedback_exists = conn.execute("SELECT to_regclass('study_feedback') AS table_name").fetchone()[
            "table_name"
        ]
        kinds = {}
        if feedback_exists:
            kinds = {
                row["run_id"]: row["kind"]
                for row in conn.execute(
                    "SELECT f.run_id,f.content->>'kind' AS kind FROM study_feedback f "
                    "JOIN study_run r USING(run_id)" + where,
                    params,
                )
            }
        events = defaultdict(list)
        for event in conn.execute(
            "SELECT e.run_id,e.event_type,(SELECT jsonb_object_agg(key,value) FROM jsonb_each(e.payload) "
            "WHERE key=ANY(%s)) AS payload FROM study_event e JOIN study_run r USING(run_id)"
            + where
            + (" AND " if where else " WHERE ")
            + "e.event_type=ANY(%s) ORDER BY e.run_id,e.sequence",
            [list(EVENT_KEYS), *params, sorted(EVENT_TYPES)],
        ):
            events[event["run_id"]].append(
                {"event_type": event["event_type"], "payload": event["payload"] or {}}
            )
        for run in runs:
            kind = run.pop("artifact_kind") or kinds.get(run["run_id"])
            rows.append(
                project({"run": run, "events": events[run["run_id"]], "artifact_kind": kind}, "postgresql")
            )
    return rows, [{"source": "postgresql", "records": len(rows), "snapshot": "repeatable read, read only"}]


def window(rows):
    starts = [r["run"]["created_at"] for r in rows if r["run"].get("created_at")]
    ends = [r["run"]["finished_at"] or r["run"]["created_at"] for r in rows if r["run"].get("created_at")]
    return {
        "from": min(starts).isoformat() if starts else None,
        "through": max(ends).isoformat() if ends else None,
        "runs_with_timestamps": len(starts),
        "runs_without_timestamps": len(rows) - len(starts),
        "basis": "contributing Run lifetimes; unfinished Runs use created_at, not an estimated end",
    }


def measure(samples, population):
    """Nearest-rank P50/P95, all observed outcomes; no interpolation/imputation."""
    values = sorted(value for _, value in samples)
    contributing = list({row["run"]["run_id"]: row for row, _ in samples}.values())
    return {
        "availability": "可得" if values else "不可得",
        "sample_count": len(values),
        "population_count": population,
        "time_range": window(contributing),
        "total": sum(values) if values else None,
        "p50": values[math.ceil(len(values) * 0.5) - 1] if values else None,
        "p95": values[math.ceil(len(values) * 0.95) - 1] if values else None,
    }


def distribution(counts, rows):
    return {"counts": dict(counts), "sample_count": sum(counts.values()), "time_range": window(rows)}


def outcome(row):
    status = row["run"].get("status")
    if status == "succeeded":
        if row["artifact_kind"] is None:
            return "unknown"
        return "abstention" if row["artifact_kind"] == "insufficient_evidence" else "success"
    if status in {"failed", "cancelled", "budget_exceeded"}:
        return status
    return "nonterminal" if status in {"queued", "running"} else "unknown"


def category(payload):
    return payload.get("failure_category") or (
        failure_category(payload["error_code"]) if payload.get("error_code") else "unknown"
    )


def tool_name(payload):
    name = payload.get("tool")
    return (
        name
        if isinstance(name, str)
        and name in {*PRACTICE_TOOLS, *FEEDBACK_TOOLS}
        and payload.get("error_code") != "UNKNOWN_TOOL"
        else "unknown"
    )


def tool_attempts(row, *, requested=False):
    """Executed calls, optionally extended with observed pre-execution rejections.

    Decision spans can carry the *previous* pending call_id, so their rejections
    must not be attached to that completed call. One anonymous rejection event
    is one observed rejection boundary; unrecorded response contents are unknown.
    Read retries and duplicate inner/outer rejection events do not add calls.
    """
    starts, finished, failed, rejected, before_execution = {}, set(), {}, {}, {}
    for event in row["events"]:
        typ, p = event["event_type"], event["payload"]
        call = p.get("call_id")
        if call is None:
            continue
        if typ == "tool_started":
            starts[call] = tool_name(p)
        elif typ == "tool_finished":
            finished.add(call)
        elif typ == "node_failed" and p.get("node") in {"tool", "feedback_tool"}:
            failed[call] = category(p)
        elif typ == "dependency_stopped":
            failed[call] = category(p)
    for index, event in enumerate(row["events"]):
        if event["event_type"] != "tool_rejected":
            continue
        p = event["payload"]
        call = p.get("call_id")
        decision = p.get("node") in {"decide", "feedback_decide"}
        # A top-level CHECK/authority validation is not a model tool request.
        if p.get("action") and call is None and not decision:
            continue
        if call in starts and not decision:
            rejected[call] = category(p)
        else:
            key = ("event", index) if decision or call is None else ("call", call)
            before_execution[key] = (tool_name(p), "rejected", category(p))
    calls = [
        (
            tool,
            "success"
            if call in finished
            else "rejected"
            if call in rejected
            else "failed"
            if call in failed
            else "unknown",
            None if call in finished else rejected.get(call, failed.get(call)),
        )
        for call, tool in starts.items()
    ]
    return calls + list(before_execution.values()) if requested else calls


def summarize_attempts(attempts):
    counts = Counter(result for _, result, _ in attempts)
    observed = counts["success"] + counts["failed"] + counts["rejected"]
    failure_groups = {"failed": defaultdict(list), "rejected": defaultdict(list)}
    for row, result, failure in attempts:
        if result in failure_groups:
            failure_groups[result][failure or "unknown"].append(row)
    output = {
        "availability": "可得" if attempts else "不可得",
        "sample_count": len(attempts),
        "success": counts["success"],
        "failed": counts["failed"],
        "rejected": counts["rejected"],
        "unknown": counts["unknown"],
        "rate_denominator": observed,
        "time_range": window(list({r["run"]["run_id"]: r for r, _, _ in attempts}.values())),
    }
    for result, rate in (
        ("success", "success_rate"),
        ("failed", "failure_rate"),
        ("rejected", "rejection_rate"),
    ):
        output[rate] = counts[result] / observed if observed else None
    for result, prefix in (("failed", "failure"), ("rejected", "rejection")):
        output[prefix + "_categories"] = {
            cat: len(affected) for cat, affected in sorted(failure_groups[result].items())
        }
        output[prefix + "_category_samples"] = {
            cat: distribution(
                Counter({cat: len(affected)}), list({r["run"]["run_id"]: r for r in affected}.values())
            )
            for cat, affected in sorted(failure_groups[result].items())
        }
    return output


def attempt_summary(samples):
    grouped = defaultdict(list)
    for row, tool, result, failure in samples:
        grouped[tool].append((row, result, failure))
    return {tool: summarize_attempts(attempts) for tool, attempts in sorted(grouped.items())}


def summarize(rows):
    per_run, durations, logical, requests, mcp, evidence = [], defaultdict(list), [], [], [], []
    failure_events = defaultdict(list)
    for row in rows:
        run, events = row["run"], row["events"]
        accounting = trace_metrics(
            {
                "model_calls": run.get("model_calls", 0),
                "reserved_tokens": 0,
                "tool_calls": run.get("tool_calls", 0),
            },
            events,
        )
        usage = {}
        for key, trace_key in (("prompt_tokens", "input_tokens"), ("completion_tokens", "output_tokens")):
            usage[key] = accounting[trace_key]
            if "model_calls" not in run:
                usage[key]["total"] = None
        total_tokens = (
            usage["prompt_tokens"]["total"] + usage["completion_tokens"]["total"]
            if all(u["total"] is not None for u in usage.values())
            else None
        )
        persisted_ms = None
        if run["created_at"] and run["finished_at"]:
            persisted_ms = (run["finished_at"] - run["created_at"]).total_seconds() * 1000
            if persisted_ms < 0:
                raise ValueError("Negative Run lifetime")
            durations["run_created_to_finished_ms"].append((row, persisted_ms))
        if row["elapsed_ms"] is not None:
            durations["evaluation_execute_ms"].append((row, row["elapsed_ms"]))
        logical.extend((row, *attempt) for attempt in tool_attempts(row))
        requests.extend((row, *attempt) for attempt in tool_attempts(row, requested=True))
        for p in row["mcp_events"]:
            mcp.append(
                (row, p.get("tool", "unknown"), "failed" if p.get("error_code") else "success", category(p))
            )
            if number(p.get("duration_ms")):
                durations["mcp:" + p.get("tool", "unknown")].append((row, p["duration_ms"]))
        for event in events:
            typ, p = event["event_type"], event["payload"]
            if typ in {"tool_read_failed", "tool_rejected", "dependency_stopped", "model_failed"}:
                failure_events[typ + ":" + category(p)].append(row)
            if typ in {
                "model_finished",
                "model_failed",
                "node_finished",
                "node_failed",
                "evidence_finished",
                "evidence_failed",
            } and number(p.get("duration_ms")):
                name = (
                    "model:" + p.get("purpose", "unspecified")
                    if typ.startswith("model_")
                    else "node:" + p.get("node", "unspecified")
                    if typ.startswith("node_")
                    else "evidence:" + p.get("action", "unspecified")
                )
                durations[name].append((row, p["duration_ms"]))
            if typ in {"evidence_finished", "evidence_failed"}:
                evidence.append(
                    (
                        row,
                        p.get("action", "unknown"),
                        "success" if typ == "evidence_finished" else "failed",
                        category(p),
                    )
                )
        per_run.append(
            {
                "run_id": run["run_id"],
                "outcome": outcome(row),
                "model_calls": run.get("model_calls"),
                "budget_tool_calls": run.get("tool_calls"),
                "usage_origin": accounting["usage_origin"],
                "model_events_started": sum(e["event_type"] == "model_started" for e in events),
                "model_events_completed": sum(
                    e["event_type"] in {"model_finished", "model_failed"} for e in events
                ),
                **usage,
                "total_tokens": total_tokens,
                "monetary_cost": None,
                "read_retries": accounting["read_retries"],
                "end_to_end_ms": persisted_ms,
                "evaluation_execute_ms": row["elapsed_ms"],
                "time_range": window([row]),
            }
        )
    metrics = {}
    for key in (
        "model_calls",
        "model_events_started",
        "model_events_completed",
        "budget_tool_calls",
        "total_tokens",
        "read_retries",
    ):
        metrics[key] = measure(
            [(row, p[key]) for row, p in zip(rows, per_run, strict=True) if p[key] is not None], len(rows)
        )
    for key in ("prompt_tokens", "completion_tokens"):
        metrics[key] = measure(
            [
                (row, p[key]["total"])
                for row, p in zip(rows, per_run, strict=True)
                if p[key]["total"] is not None
            ],
            len(rows),
        )
        metrics[key]["known_total_including_partial_runs"] = sum(p[key]["known_total"] for p in per_run)
        metrics[key]["missing_model_calls"] = sum(p[key]["missing_calls"] for p in per_run)
    metrics["monetary_cost"] = {
        **measure([], len(rows)),
        "reason": "当前持久化格式没有金额、币种或计费账单；不根据 token/预留预算估算。",
        "selected_runs_time_range": window(rows),
    }
    for required in (
        "run_created_to_finished_ms",
        "evaluation_execute_ms",
        "node:decide",
        "node:tool",
        "node:feedback_decide",
        "node:feedback_tool",
    ):
        durations.setdefault(required, [])
    return {
        "runs": len(rows),
        "sessions": len({r["run"].get("session_id") for r in rows} - {None}),
        "runs_without_session_id": sum(not r["run"].get("session_id") for r in rows),
        "time_range": window(rows),
        "terminal_outcomes": distribution(
            Counter({key: sum(outcome(r) == key for r in rows) for key in OUTCOMES}), rows
        ),
        "raw_statuses": distribution(Counter(r["run"].get("status", "unknown") for r in rows), rows),
        "per_run_metrics": metrics,
        "per_run": per_run,
        "logical_tools": attempt_summary(logical),
        "executed_tools": attempt_summary(logical),
        "requested_tools": attempt_summary(requests),
        "tool_totals": {
            "executed": summarize_attempts([(r, result, cat) for r, _, result, cat in logical]),
            "requested": summarize_attempts([(r, result, cat) for r, _, result, cat in requests]),
        },
        "mcp_transport_attempts": attempt_summary(mcp),
        "mcp_recorded_runs": sum(r["has_mcp_events"] for r in rows),
        "evidence_completed_attempts_excluding_CHECK": attempt_summary(evidence),
        "failure_event_counts": {
            key: distribution(
                Counter({key: len(affected)}), list({r["run"]["run_id"]: r for r in affected}.values())
            )
            for key, affected in sorted(failure_events.items())
        },
        "latencies_ms": {key: measure(samples, len(rows)) for key, samples in sorted(durations.items())},
    }


def build_report(rows, sources, *, since=None, until=None, labels=(), scenarios=()):
    if since and until and since >= until:
        raise ValueError("since must precede until")
    seen = set()
    selected = []
    for row in rows:
        run_id = row["run"]["run_id"]
        if run_id in seen:
            raise ValueError(
                "Duplicate run_id; select disjoint snapshots, not worker and merged files together"
            )
        seen.add(run_id)
        if labels and row["cohort"]["label"] not in labels:
            continue
        if scenarios and row["cohort"]["scenario"] not in scenarios:
            continue
        created = row["run"]["created_at"]
        if (since or until) and created is None:
            raise ValueError("Cannot apply time filter to a Run without created_at")
        if (since and created < since) or (until and created >= until):
            continue
        selected.append(row)
    groups = defaultdict(list)
    for row in selected:
        groups[json.dumps(row["cohort"], sort_keys=True)].append(row)
    return {
        "schema_version": 1,
        "sources": sources,
        "input_runs": len(rows),
        "selected_runs": len(selected),
        "filters": {
            "since_inclusive": since.isoformat() if since else None,
            "until_exclusive": until.isoformat() if until else None,
            "labels": list(labels),
            "scenarios": list(scenarios),
        },
        "quantile_method": "nearest rank; all observed outcomes; no interpolation",
        "notes": [
            "运行成功不等于教学质量通过；故障注入与 mock 只验证机制。各来源/实现/模型/场景分别统计，不合并宣传。",
            "端到端=持久化 created_at→finished_at，含排队/恢复；evaluation_execute_ms 是评测执行计时，两者不混用。",
            "工具请求=requested_tools，含执行前 tool_rejected；执行口径=executed_tools，仅有 tool_started 的逻辑调用；logical_tools 是后者的兼容别名。",
            "两种工具口径分别以成功+失败+拒绝为比率分母，unknown 单列；读取重试不新增逻辑调用。缺失/非法工具名归 unknown。",
            "请求口径仅统计可观察的执行起点与拒绝边界，不重建未记录的模型响应；匿名/整段协议拒绝计一个边界，无法取得其中原始工具数/名称。",
            "MCP 传输成功仅表示调用返回；响应内容校验失败见 tool_read_failed，不能视为依赖语义成功。",
            "public EVENTS 导出可能分页/截断，缺失工具结束记 unknown；分节点延迟需要已保存的 node 事件。",
            "延迟 population_count 为队列 Run 数，sample_count 为已记录调用/节点次数；嵌套耗时不可相加。",
            "部分 token 已知总量单列；无完整 usage 的 Run 不进入完整 token 总量/P50/P95。预留 token 不是用量。",
            "model_calls/tool_calls 是现有持久预算计数；model_events_started/completed 是记录到的调用事件，取消窗口可能不一致。",
            "time_range 为贡献样本所属 Run 的 UTC 生命周期；时间戳缺失数量明确列出，未推算事件时间。",
            "拒答以最终产物 kind=insufficient_evidence 判断；成功但产物类型缺失归 unknown。",
            "数据库历史记录未存代码 SHA 时 source_sha256 不可得；已记录模型路由仅输出安全字段指纹，不推断代码版本。",
        ],
        "cohorts": [
            {"identity": json.loads(key), **summarize(group)} for key, group in sorted(groups.items())
        ],
    }


def markdown(report):
    lines = [
        "# Study Agent 持久记录指标",
        "",
        f"输入 {report['input_runs']} Run；选中 {report['selected_runs']} Run。",
        "",
        "以下均为执行指标，不认证内容质量。金额无持久化记录，标为不可得。",
        "",
        "|来源 / 标签 / 场景|N|成功 / 拒答 / 失败 / 取消 / 预算 / 其他|UTC 范围|持久化端到端 P50/P95 ms (N)|执行计时 P50/P95 ms (N)|模型调用总数 (Run N)|完整 token (Run N)|",
        "|---|---:|---|---|---|---|---|---|",
    ]

    def latency(metric):
        if not metric["sample_count"]:
            return "不可得 (0)"
        return f"{metric['p50']:.3f}/{metric['p95']:.3f} ({metric['sample_count']})"

    for cohort in report["cohorts"]:
        identity, metrics = cohort["identity"], cohort["per_run_metrics"]
        counts, time = cohort["terminal_outcomes"]["counts"], cohort["time_range"]
        outcomes = (
            "/".join(str(counts[k]) for k in OUTCOMES[:5]) + f"/{counts['nonterminal'] + counts['unknown']}"
        )
        models, tokens = metrics["model_calls"], metrics["total_tokens"]
        token_text = str(tokens["total"]) if tokens["sample_count"] else "不可得"
        lines.append(
            f"|{Path(identity['source']).name} / {identity['label']} / {identity['scenario']}|"
            f"{cohort['runs']}|{outcomes}|{time['from']} → {time['through']}|"
            f"{latency(cohort['latencies_ms']['run_created_to_finished_ms'])}|"
            f"{latency(cohort['latencies_ms']['evaluation_execute_ms'])}|"
            f"{models['total']} ({models['sample_count']})|{token_text} ({tokens['sample_count']})|"
        )
    lines.extend(
        [
            "",
            "工具请求与执行口径（S/F/R/U = 成功/失败/拒绝/未知；百分比顺序为成功/失败/拒绝，分母不含未知）：",
            "",
            "|来源 / 标签 / 场景|请求 N，S/F/R/U|请求比率 %|执行 N，S/F/R/U|执行比率 %|",
            "|---|---|---|---|---|",
        ]
    )
    for cohort in report["cohorts"]:
        identity = cohort["identity"]
        cells = []
        for scope in ("requested", "executed"):
            total = cohort["tool_totals"][scope]
            cells.append(
                f"{total['sample_count']}，"
                + "/".join(str(total[k]) for k in ("success", "failed", "rejected", "unknown"))
            )
            cells.append(
                "/".join(
                    f"{total[k] * 100:.2f}" if total[k] is not None else "不可得"
                    for k in ("success_rate", "failure_rate", "rejection_rate")
                )
            )
        lines.append(
            f"|{Path(identity['source']).name} / {identity['label']} / {identity['scenario']}|"
            + "|".join(cells)
            + "|"
        )
    lines.extend(
        [
            "",
            "完整的每 Run 用量、每工具成功率/失败类别、每节点 P50/P95、各指标样本与时间范围见 report.json。",
            "",
        ]
    )
    lines.extend("- " + note for note in report["notes"])
    lines.extend(["", "数据来源（SHA256 与逐项身份保存在 report.json）：", ""])
    lines.extend(f"- {s['source']}：{s['records']} Run" for s in report["sources"])
    return "\n".join(lines) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--records", type=Path, action="append", default=[], help="Explicit JSONL snapshot; repeatable"
    )
    parser.add_argument("--database", action="store_true", help="Read AGENT_DATABASE_URL; no DSN in output")
    parser.add_argument("--run-id", action="append", default=[], help="Database Run selector")
    parser.add_argument("--since", type=timestamp, help="Run created_at inclusive, timezone required")
    parser.add_argument("--until", type=timestamp, help="Run created_at exclusive")
    parser.add_argument("--label", action="append", default=[])
    parser.add_argument("--scenario", action="append", default=[])
    parser.add_argument("--output-dir", type=Path, required=True, help="New directory; never overwrite")
    args = parser.parse_args()
    if not args.records and not args.database:
        parser.error("select --records or --database")
    if args.run_id and not args.database:
        parser.error("--run-id requires --database")
    try:
        rows, sources = load_records(args.records)
        if args.database:
            db_rows, db_sources = load_database(
                os.environ["AGENT_DATABASE_URL"], since=args.since, until=args.until, run_ids=args.run_id
            )
            rows.extend(db_rows)
            sources.extend(db_sources)
        report = build_report(
            rows, sources, since=args.since, until=args.until, labels=args.label, scenarios=args.scenario
        )
        args.output_dir.mkdir(mode=0o700, parents=True, exist_ok=False)
        for name, content in (
            ("report.json", json.dumps(report, ensure_ascii=False, indent=2) + "\n"),
            ("REPORT.md", markdown(report)),
        ):
            with open(
                args.output_dir / name,
                "x",
                encoding="utf-8",
                opener=lambda p, flags: os.open(p, flags, 0o600),
            ) as f:
                f.write(content)
    except (OSError, ValueError, KeyError, psycopg.Error) as error:
        # Do not print DB exceptions/DSNs or bad records that may contain secrets.
        parser.exit(
            2,
            f"Report failed: {type(error).__name__}; check inputs, disjoint Run IDs and new output directory.\n",
        )
    print(
        json.dumps(
            {
                "selected_runs": report["selected_runs"],
                "cohorts": len(report["cohorts"]),
                "report": str(args.output_dir / "report.json"),
            },
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
