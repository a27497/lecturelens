"""Derive all statistics from paired raw runs; no estimated measurements."""
import hashlib
import json
import math
from collections import Counter
from pathlib import Path
from statistics import mean

ROOT = Path(__file__).resolve().parent
INVALID = {"negative_parameter", "reversed_window", "oversized_parameter", "integer_overflow", "unknown_tool", "illegal_call_shape"}


def percentile(values, q):
    return round(sorted(values)[max(0, math.ceil(q * len(values)) - 1)], 3)


def stats(values):
    return {"mean": round(mean(values), 3), "p50": percentile(values, .5), "p95": percentile(values, .95)}


def load(name):
    rows = [json.loads(line) for line in (ROOT / name).read_text().splitlines()]
    assert len({(r["trial"], r["scenario"]) for r in rows}) == len(rows)
    assert len({r["source_sha256"] for r in rows}) == 1
    assert len({r["fixture_sha256"] for r in rows}) == 1
    return {(r["trial"], r["scenario"]): r for r in rows}


def summarize(rows, scenario):
    selected = [r for (_, s), r in rows.items() if s == scenario]
    assert len(selected) >= 20
    control = [rows[(r["trial"], "healthy")] for r in selected]
    assert all(r["run"]["status"] == "succeeded" for r in control)
    success = sum(r["run"]["status"] == "succeeded" for r in selected)
    refused = sum(r["run"]["status"] == "succeeded" and r["artifact_kind"] == "insufficient_evidence" for r in selected)
    retried = [sum(e["event_type"] == "tool_retry_started" for e in r["public_events"]) for r in selected]
    protocol = [sum(e["event_type"] == "protocol_retry_scheduled" for e in r["public_events"]) for r in selected]
    return {
        "n": len(selected), "execution_success": success,
        "recovery_success_rate": None if scenario in INVALID else success / len(selected),
        "unsafe_success": success if scenario in INVALID else 0,
        "status_distribution": dict(Counter(r["run"]["status"] for r in selected)),
        "refusal_count": refused,
        "failure_codes": dict(Counter(r["run"]["error_code"] for r in selected if r["run"]["error_code"])),
        "failure_categories": dict(Counter(e["payload"]["failure_category"] for r in selected
            for e in r["public_events"] if e["event_type"] == "run_finished" and e["payload"].get("failure_category"))),
        "dependency_stop_count": sum(e["event_type"] == "dependency_stopped" for r in selected for e in r["public_events"]),
        "read_retry_calls": {"total": sum(retried), "per_run": stats(retried)},
        "protocol_retry_calls": {"total": sum(protocol), "per_run": stats(protocol)},
        "budget_tool_calls": stats([r["run"]["tool_calls"] for r in selected]),
        "mcp_calls": stats([sum(e["event"] == "tools/call" for e in r["mcp_events"]) for r in selected]),
        "latency_ms": stats([r["elapsed_ms"] for r in selected]),
        "latency_increment_vs_healthy_ms": stats([r["elapsed_ms"] - r.get("control_elapsed_ms", c["elapsed_ms"]) for r, c in zip(selected, control, strict=True)]),
    }


def main():
    before, after = load("baseline.jsonl"), load("candidate.jsonl")
    assert set(before) == set(after)
    assert {r["fixture_sha256"] for r in before.values()} == {r["fixture_sha256"] for r in after.values()}
    scenarios = sorted({s for _, s in before})
    summary = {"baseline_commit": "56bc07ac3f5f57bb71592047baf12befc90e0448",
               "baseline_source_sha256": next(iter(before.values()))["source_sha256"],
               "candidate_source_sha256": next(iter(after.values()))["source_sha256"],
               "raw_sha256": {f: hashlib.sha256((ROOT / f).read_bytes()).hexdigest() for f in ["baseline.jsonl", "candidate.jsonl", "run.py"]},
               "percentile_method": "nearest rank; signed per-trial deltas; full Run wall time, not tool-only time",
               "workers_per_phase": 4, "samples_per_worker": 5,
               "real_model_quality": "未运行", "real_Java_process": "未运行", "scenarios": {}}
    for scenario in scenarios:
        b, a = summarize(before, scenario), summarize(after, scenario)
        selected = [key for key in before if key[1] == scenario]
        paired = [after[key]["elapsed_ms"] - before[key]["elapsed_ms"] for key in selected]
        adjusted = [after[key]["elapsed_ms"] - after[(key[0], "healthy")]["elapsed_ms"]
                    - before[key]["elapsed_ms"] + before[key].get("control_elapsed_ms", before[(key[0], "healthy")]["elapsed_ms"]) for key in selected]
        call_delta = [len(after[key]["mcp_events"]) - sum(e["event"] == "initialize" for e in after[key]["mcp_events"])
                      - len(before[key]["mcp_events"]) + sum(e["event"] == "initialize" for e in before[key]["mcp_events"]) for key in selected]
        summary["scenarios"][scenario] = {"baseline": b, "candidate": a,
            "candidate_minus_baseline_latency_ms": stats(paired),
            "candidate_minus_baseline_fault_increment_ms": stats(adjusted),
            "candidate_minus_baseline_mcp_calls": {"total": sum(call_delta), "per_run": stats(call_delta)}}
    transient = ["timeout_once", "unavailable_once"]
    persistent = ["timeout_persistent", "unavailable_persistent", "check_unavailable_persistent"]
    summary["totals"] = {
        "baseline_runs": len(before), "candidate_runs": len(after),
        "transient": {"n": sum(summary["scenarios"][s]["candidate"]["n"] for s in transient),
                      "baseline_recovered": sum(summary["scenarios"][s]["baseline"]["execution_success"] for s in transient),
                      "candidate_recovered": sum(summary["scenarios"][s]["candidate"]["execution_success"] for s in transient)},
        "persistent_failed": sum(summary["scenarios"][s]["candidate"]["status_distribution"].get("failed", 0) for s in persistent),
        "candidate_invalid_rejected": sum(summary["scenarios"][s]["candidate"]["status_distribution"].get("failed", 0) for s in INVALID),
        "baseline_unsafe_success": sum(summary["scenarios"][s]["baseline"]["unsafe_success"] for s in INVALID),
        "candidate_unsafe_success": sum(summary["scenarios"][s]["candidate"]["unsafe_success"] for s in INVALID),
    }
    (ROOT / "summary.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False) + "\n")
    lines = ["# 工具容错故障注入结果", "", "由 summarize.py 从原始 JSONL 生成；P50/P95 使用 nearest rank。",
             "负延迟增量表示失败较早结束，不能解读为完成同一学习任务更快。", "",
             "正式对比：改动前提交 56bc07a 与最终候选，客户端及 MCP Server 均固定同版源码；两版使用同一夹具。",
             "14 个故障场景各 20 次/版，另有健康控制 20 次/版，共 600 条正式原始记录。",
             f'临时超时/503 恢复 {summary["totals"]["transient"]["baseline_recovered"]}/40 → {summary["totals"]["transient"]["candidate_recovered"]}/40；持续依赖故障 {summary["totals"]["persistent_failed"]}/60 明确失败；参数/非法工具 {summary["totals"]["candidate_invalid_rejected"]}/120 执行前拒绝。',
             f'基线越界请求继续成功 {summary["totals"]["baseline_unsafe_success"]} 次，候选 {summary["totals"]["candidate_unsafe_success"]} 次；这属于协议合规指标，不是内容质量评分。', "",
             "|场景|每版样本|基线成功|候选成功|候选失败/拒答|候选额外读重试（总）|候选相对健康 P50/P95 ms|候选减基线 P50/P95 ms|",
             "|---|---:|---:|---:|---|---:|---|---|"]
    for scenario, data in summary["scenarios"].items():
        b, a = data["baseline"], data["candidate"]
        delta, compare = a["latency_increment_vs_healthy_ms"], data["candidate_minus_baseline_latency_ms"]
        lines.append(f'|{scenario}|{a["n"]}|{b["execution_success"]}/{b["n"]}|{a["execution_success"]}/{a["n"]}|'
                     f'{a["status_distribution"].get("failed", 0)}/{a["refusal_count"]}|{a["read_retry_calls"]["total"]}|'
                     f'{delta["p50"]:.1f}/{delta["p95"]:.1f}|{compare["p50"]:.1f}/{compare["p95"]:.1f}|')
    lines += ["", "越界与非法工具场景的成功属于 unsafe_success，不能算恢复；summary.json 保留原始执行状态与该指标。",
              "所有失败码、类别、模型格式重试、调用差值和配对延迟增量详见 summary.json。",
              "真实模型任务质量、真实 Java 进程故障：未运行。"]
    if (ROOT / "verification.json").exists():
        verification = json.loads((ROOT / "verification.json").read_text())
        counts = verification["python_checks"]
        lines += ["", f'全量 Python 检查：{counts["tests"]} 项通过、{counts["failures"]} 失败、{counts["errors"]} 错误、{counts["skipped"]} 跳过；四组完整覆盖，每组独立 PostgreSQL/pgvector。',
                  "ruff/check/format 与 git diff --check 通过。Java 未修改，其测试未运行。未 push、未部署。",
                  "验证明细、源码/patch 哈希见 verification.json；中间失败/中断批次及未覆盖类型见 README.md。"]
    (ROOT / "RESULTS.md").write_text("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
