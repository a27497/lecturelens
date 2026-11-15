"""Render the frozen evidence reports offline, without provider requests."""

import collections
import json

from score import stats
from support import PRIVATE, PUBLIC, ROOT


def read(name):
    return json.loads((PUBLIC / name).read_text())


def fmt(value, divisor=1):
    if not value or not value["n"]:
        return "不可得（N=0）"
    sd = (
        f"{value['sample_sd'] / divisor:.3f}"
        if value["sample_sd"] is not None
        else "不可得"
    )
    return f"{value['mean'] / divisor:.3f} ± {sd}（N={value['n']}）"


def main():
    s = read("summary.json")
    base = s["baseline"]
    checks = read("final-check.json")
    dead = read("dead-handling.json")
    segments = read("translation-segment-counts.json")
    calls = read("database-call-diagnostics.json")
    diagnostics = read("http-400-diagnostics.json")
    failures = collections.Counter(
        c["error_code"] for c in calls if c["status"] == "FAILED"
    )
    known = sum(t["completed_batch_total_tokens"] for t in s["trials"])
    batch_count = sum(t["completed_batch_count"] for t in s["trials"])
    lines = [
        "# P1-3b：DeepSeek 翻译基线重测",
        "",
        f"正式任务 {s['finished_trials']}/10；完整任务成功 {s['overall']['successes']}/10；全文翻译成功 {s['overall']['translation_successes']}/10。失败均保留，没有重投、替换样本或修复业务代码。",
        "",
        "## 与 P1-3 对比",
        "",
        "| 指标 | P1-3 | 本轮 |",
        "|---|---|---|",
        f"| 完整任务成功 | 0/10 | {s['overall']['successes']}/10 |",
        f"| 全文翻译成功 | 1/10 | {s['overall']['translation_successes']}/10 |",
        f"| 失败终态 | 10 | {s['task_status_counts'].get('FAILED', 0)} |",
        f"| 学习资料 HTTP 400 | 1 | {len(diagnostics)} |",
        "| 配置 | 本机 qwen2.5-3b | 版本 10，DeepSeek deepseek-flash，仅全文翻译 |",
        "",
        "## 阶段耗时：秒，均值 ± 样本标准差",
        "",
        "| 阶段 | P1-3（完成或失败） | 本轮（完成或失败） | 本轮成功完成该阶段 |",
        "|---|---|---|---|",
    ]
    for key, label in [
        ("EXTRACT_AUDIO", "提取音频"),
        ("TRANSCRIBE", "转写"),
        ("TRANSLATE_SUBTITLES", "全文翻译"),
        ("GENERATE_LEARNING_PACKAGE", "学习资料生成"),
    ]:
        lines.append(
            f"| {label} | {fmt(base['stage_ms'].get(key), 1000)} | {fmt(s['overall']['stage_seconds'].get(key))} | {fmt(s['overall']['successful_stage_seconds'].get(key))} |"
        )
    observed = stats([t["processing_to_index_seconds"] for t in s["trials"]])
    lines += [
        f"| 提交至终止/就绪观测 | {fmt(base['processing_ms'], 1000)} | {fmt(observed)} | 不等同成功处理时延 |",
        "",
        "失败前耗时下降不能解释为性能改善；未运行的资料/索引阶段不记为 0。两轮使用同一冻结媒体，当前参数未改；旧轮为较早 JAR、独立 schema/topic 和响应 tee，本轮为既有系统模型版本与在线服务，因此不是只替换模型的严格 A/B。",
        "",
        "## 单节翻译与费用",
        "",
        "| 课程 | P1-3 翻译阶段秒 | 本轮翻译阶段秒 | 翻译成功 | 本轮完整 DeepSeek 目录费用 |",
        "|---|---|---|---|---|",
    ]
    for name, v in s["per_lecture"].items():
        old = base["per_lecture"][name]["stage_ms"].get("TRANSLATE_SUBTITLES")
        cost = (
            "不可得（完整用量缺失）"
            if not v["deepseek_cost_lower_usd"]["n"]
            else f"均值区间 ${v['deepseek_cost_lower_usd']['mean']:.6f}–${v['deepseek_cost_upper_usd']['mean']:.6f}，缓存拆分未知"
        )
        lines.append(
            f"| {name} | {fmt(old, 1000)} | {fmt(v['stage_seconds'].get('TRANSLATE_SUBTITLES'))} | {v['translation_successes']}/{v['n']} | {cost} |"
        )
    lines += [
        "",
        "## 逐次记录",
        "",
        "| 试次 | 状态 / 阶段 | 转写秒 | 翻译秒 | 源段/已持久化译段 | 成功批次/已知 token 小计 | 任务重试/ASR分片重试/翻译重试 | 冻结版本 |",
        "|---|---|---:|---:|---|---|---|---|",
    ]
    for t in s["trials"]:
        seg = segments[t["trial_id"]]
        asr = t["stages"].get("TRANSCRIBE", {}).get("seconds")
        translation = t["stages"].get("TRANSLATE_SUBTITLES", {}).get("seconds")
        retry = (
            t["translation_retries"] if t["translation_retries"] is not None else "未知"
        )
        lines.append(
            f"| {t['trial_id']} | {t['status']} / {t['failure_stage']} | {asr if asr is not None else '未运行'} | {translation if translation is not None else '未运行'} | {seg['source_segments']}/{seg['persisted_translated_segments']} | {t['completed_batch_count']}/{t['completed_batch_total_tokens']} | {t['task_retry_count']}/{t['asr_chunk_retry_events']}/{retry} | {t['config_version']} |"
        )
    lines += [
        "",
        f"失败调用分类（来自 DB）：`{json.dumps(dict(failures), ensure_ascii=False)}`。运行时安全分类不能证明供应商究竟返回了截断、错误 JSON、空内容或其他被映射的异常；没有上游正文就不进一步推断。",
        "",
        "## 用量与目录价的可观测边界",
        "",
        f"日志中 {batch_count} 个成功批次的 totalTokens 小计为 **{known}**。完整翻译阶段有输入/输出/总 token 的试次为 **{s['usage_complete_trials']}/10**。失败调用用量没有持久化，成功批次的输入/输出拆分也未写日志；小计不是全部收费 token。逐次值在 summary.json。",
        "",
        "价格来源：[DeepSeek 官方目录价](https://api-docs.deepseek.com/quick_start/pricing/)，抓取 UTC 日期 2026-10-15，原页面及哈希留在私有目录。deepseek-flash 非高峰每百万 token：输入缓存命中 $0.003、未命中 $0.15、输出 $0.60；高峰分别为 $0.006/$0.30/$1.20。本轮请求时段为非高峰。",
        "",
        "有完整输入/输出用量 P、C 时，目录费用区间为 `(P×0.003+C×0.60)/1e6` 至 `(P×0.15+C×0.60)/1e6` USD；缓存命中拆分缺失，所以不宣称精确账单。",
        f"仅对上述成功批次已知总 token T={known}，把所有 T 当最低价输入或最高价输出，可得极宽的小计边界 **${known * 0.003 / 1e6:.8f}–${known * 0.6 / 1e6:.8f}**；它排除用量未知的失败调用，不能充当整轮或单节总费用。未把缺失 token、费用或重试数填成零。",
        "",
        "本轮 ASR 正常走既有百炼配置，生产调用记录没有 ASR 计费 token；没有为计量重启或注入 tee，因此 ASR 费用及含 ASR 的单节总费用不可得。旧基线 ASR 已知目录小计为人民币，不能与本轮 USD 数字直接相加。免费额度、折扣、机器成本和账单均未计入。",
        "",
        "## HTTP 400",
        "",
        f"本轮资料生成 HTTP 400 试次为 {len(diagnostics)}。若未进入资料阶段，不做额外诊断模型调用来制造该样本。原始响应采集仅监听本机 llama 的响应方向，不监听请求或鉴权头，不保存 pcap。具体摘要/响应见 http-400-diagnostics.json；如有捕获，保留响应原文结构并脱敏。",
        "",
        "## DEAD 与最终状态",
        "",
        f"测量前失败任务 {dead['failed_task_count']} 个，其中正式基线 {dead['formal_baseline_count']}、非基线 {dead['non_baseline_failed_count']}，完整列表见 ALL_FAILED_TASKS.md。基线 outbox 已 DEAD（8 次尝试），不会被投递器领取；MQ 重试已消费至末尾，死信 topic 不存在，积压/在途均为 0，所以无需改写或消费旧记录。所有非基线 DEAD 保留。",
        "",
        f"原基线 10 行 DB 状态前后一致。测量结束保留 DeepSeek 全文翻译绑定，版本 {checks['version']}；Java/Agent/llama PID 和启动时刻、部署 JAR 均未变。最终磁盘 {checks['disk']['percent']:.4f}%。页面操作步骤见 PAGE_STEPS.md。",
    ]
    (PUBLIC / "SUMMARY.md").write_text("\n".join(lines) + "\n")
    inventory = read("failed-task-inventory.json")["tasks"]
    rows = [
        "# 测量前全部失败任务（只读）",
        "",
        "| schema / 任务 ID | 阶段 | 原因 | 创建时间（DB） | 正式 P1-3 基线 |",
        "|---|---|---|---|---|",
    ]
    for r in inventory:
        reason = (
            (r.get("error_message") or r.get("error_code") or "")
            .replace("|", " / ")
            .replace("\n", " ")
        )
        rows.append(
            f"| {r['schema']} / {r['task_id']} | {r['stage']} | {reason} | {r['created_at']} | {r['baseline_trial_id'] or '否'} |"
        )
    (PUBLIC / "ALL_FAILED_TASKS.md").write_text("\n".join(rows) + "\n")
    name = PUBLIC.name
    verify = f"""# P1-3b VERIFY

本轮业务源码/业务配置文件改动：**无**。新增内容只在 `eval/{name}/`；文件与结果哈希逐一列在 SHA256SUMS。系统数据库只通过管理员接口把 TRANSLATION_FULL_TEXT 从无绑定改为已保存模型 1，生成版本 10，完成后保留；不读取/录入供应商密钥。未改超时、并发、代码，未部署、重启、合并、push。

结果、逐次失败、均值/样本 SD、单节翻译耗时、费用可观测缺口及旧基线对比：SUMMARY.md。管理员页面具体点击步骤：PAGE_STEPS.md。

## 每个数字的证据与复算

| 数字/结论 | 原始记录 | 离线复算命令 |
|---|---|---|
| 10 次、5 课各 2 次、成功率、终态 | trials.jsonl、results/*.json | python3 eval/{name}/score.py |
| 各阶段秒数、均值 ± 样本 SD（ddof=1） | events/*.json；私有 logs/*.json | 同上，overall/per_lecture/trials |
| 分段数与已知批次 token | translation-segment-counts.json、events/*.json、results/*.json | 同上；原始计数在 segment-counts 与逐次文件 |
| 未知失败调用 token/重试、完整费用不可得 | database-call-diagnostics.json、summary.json | 同上；NULL 不填 0 |
| 官方价格、费用区间 | pricing.json；私有 deepseek-pricing.html | 同上；SUMMARY.md 中 P/C/T 公式 |
| 全部失败任务 30 / 正式基线 10 / 其余 20 | failed-task-inventory.json | python3 eval/{name}/verify.py |
| MQ 重试/死信积压 0，旧 DB 不变 | mq-*.json、dead-handling.json、original-baseline-db-before/after.json | 同上 |
| 版本 10，DATABASE，deepseek-flash，绑定保留 | binding-preflight.json、snapshots/*.json、catalog-final.json | 同上 |
| 磁盘始终不超过 85%、单任务不超过 30 分钟 | disk-observations.jsonl、trials.jsonl、final-check.json | 同上 |
| 旧基线对比数字 | eval/baseline-asr-20261015/summary.json；本目录 summary.json | score.py；render_report.py |
| 原始资料 HTTP 400（若出现） | local-http-400-responses.jsonl、http-400-diagnostics.json | python3 eval/{name}/diagnose_400.py（仅离线） |

```bash
cd {ROOT}
python3 eval/{name}/score.py > /tmp/{name}-summary.json
cmp /tmp/{name}-summary.json eval/{name}/summary.json
python3 eval/{name}/verify.py
sha256sum -c eval/{name}/SHA256SUMS
sha256sum -c eval/{name}/RAW_SHA256SUMS
agent-service/.venv/bin/ruff check eval/{name}
agent-service/.venv/bin/ruff format --check eval/{name}
```

render_report.py 可从冻结记录重新生成 SUMMARY.md、ALL_FAILED_TASKS.md 与本文件。collect_final.py/inventory.py 会读取实时数据库，不能用来改写历史快照；不属于离线复算。run_measurement.py 会真实收费，不能当验证命令自动重放。

## 原始记录与保密

原始结果全文、按任务筛选后脱敏的 Java 日志、nohup 驱动日志、响应观察器日志、官方价格网页在 `{PRIVATE}/`，路径索引见 raw-locations.json，哈希见 RAW_SHA256SUMS。媒体沿用 `eval/baseline-asr-20261015/assets.lock.json` 中的原路径和 SHA256；没有下载替代媒体，也不重新发布视频或全文。MIT OCW 原来源与 CC BY-NC-SA 4.0 署名沿用旧基线 SOURCES.md。

后台测量命令为 nohup + timeout（总上限 20000 秒），每个任务独立 1800 秒观察上限，串行、无重投。仅 GET /api/me 阶段的初次驱动失败（字符串成功码 0 处理错误）发生在上传/任务创建之前，原驱动、回执和冻结哈希保留为 driver-attempt-01-*；不计入 10 次模型试验。首次绑定检查的来源标签 DB/DATABASE 差异见 binding-preflight.json，绑定只保存一次，没有偷偷增加版本。

## 验证范围

本轮是实际供应商端到端失败/耗时测量，不是学习质量或新课程泛化验收。未运行 Java/前端/Python 业务全量测试，因为业务代码和部署未变。离线证据验证、eval 脚本 ruff 与哈希校验结果见 checks/。冻结的错误试次不改判为成功，失败终止耗时不叫成功时延，未进入阶段不记零，缺失用量不估成零。
"""
    (PUBLIC / "VERIFY.md").write_text(verify)


if __name__ == "__main__":
    main()
