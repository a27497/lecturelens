"""Render the technical report only from saved, recomputed observations."""

import json
from collections import Counter
from pathlib import Path

from score import records

REPORT = Path(__file__).resolve().parent


def number(value, digits=3):
    return "不可得" if value is None else f"{value:.{digits}f}"


def mean_sd(value, scale=1, digits=3):
    if not value["n"]:
        return "不可得（N=0）"
    return f"{number(value['mean'] * scale, digits)} ± {number(value['sample_sd'] * scale if value['sample_sd'] is not None else None, digits)}（N={value['n']}）"


def main():
    result = json.loads((REPORT / "summary.json").read_text())
    manifest = json.loads((REPORT / "assets.lock.json").read_text())
    audit = json.loads((REPORT / "cost-audit.json").read_text())
    coverage = json.loads((REPORT / "coverage-asr.json").read_text())
    lines = [
        "# P1-3 当前课程处理链路基线",
        "",
        f"冻结 {result['lecture_count']} 节完整 MIT OCW 课程，共 {result['unique_audio_hours']:.6f} 小时；每节两次串行，共 {result['finished_trials']} 次正式试验。所有失败保留。当前任务终态：`{json.dumps(result['task_status_counts'])}`；翻译终态：`{json.dumps(result['translation_status_counts'])}`；索引 READY {result['successful_index_ready_ms']['n']}/{result['finished_trials']}。",
        "",
        f"已完成转写的规范化 CER **{number(coverage['completed_transcription_weighted_cer'] * 100)}%**，N={coverage['completed_transcription_scored_trials']}，字符编辑数 {coverage['edit_distance']:,} / 参考字符数 {coverage['reference_characters']:,}。这是按参考字符加权的 CER。概率课第二次任务在 MQ 投递阶段失败，未运行 ASR，因此该课只有一次有效 CER，波动不可得；没有删掉该失败试次。",
        "",
        f"冻结的全任务空输出惩罚口径仍为 **{number(result['weighted_cer'] * 100)}%**，N={result['cer_scored_trials']}，编辑数 {result['edit_distance']:,} / 参考字符数 {result['reference_characters']:,}；该口径将未执行 ASR 的空任务结果也记为 100%。它不是纯 ASR 识别错误率。原 summary.json 和全部终态不变；追加的 coverage-asr.json 按已完成 TRANSCRIBE 的日志提供可用性视图，规则和手算测试公开。",
        "",
        f"提交任务至观测终止/索引就绪耗时 **{mean_sd(result['processing_ms'], 0.001)} 秒**；其中成功到达索引 READY 的耗时为 **{mean_sd(result['successful_index_ready_ms'], 0.001)} 秒**。失败终止不能称为成功处理延迟。上传时间另列，下载和离线去除字幕轨不计入处理时间。",
        "",
        f"用量完整试次的外部 API 目录价 **¥{mean_sd(result['asr_list_price_cny'], digits=6)} / 次**。所有已知成功 ASR 请求目录价合计 ¥{result['known_successful_asr_call_fee_cny']:.6f}；另有 {result['asr_usage_missing_calls']} 次缺 usage 的失败调用，费用不可得，未当作零或估算。因而该已知小计不是完整账单。翻译和 embedding 都在本地，外部 API 费用为零，机器/电力成本不可得。",
        "",
        f"统计窗口（UTC）：{result['time_range_utc']['from']} 至 {result['time_range_utc']['to']}。`±` 是样本标准差 ddof=1，N=2 仅描述这两次波动，不外推总体。",
        "",
        "## 每节课",
        "",
        "|课|完整分钟|尝试 N|ASR 完成 CER % 均值±SD|冻结空输出惩罚 CER %|终止/就绪秒 均值±SD|用量完整 API 元 均值±SD|",
        "|---|---:|---:|---|---|---|---|",
    ]
    for source in manifest["sources"]:
        group = result["per_lecture"][source["id"]]
        lines.append(
            f"|{source['id']}|{source['duration_ms'] / 60000:.3f}|{group['n']}|{mean_sd(coverage['per_lecture_completed_transcription_cer'][source['id']], 100)}|{mean_sd(group['cer'], 100)}|{mean_sd(group['processing_ms'], 0.001)}|{mean_sd(group['asr_list_price_cny'], digits=6)}|"
        )
    lines += [
        "",
        "## 分阶段均值与波动（秒）",
        "",
        "|课|抽音频|转写|翻译（含失败）|学习资料生成|索引 HTTP|",
        "|---|---|---|---|---|---|",
    ]
    for key, group in [*result["per_lecture"].items(), ("总体", result)]:
        empty = {"n": 0, "mean": None, "sample_sd": None, "min": None, "max": None}
        node = group["stage_ms"]
        values = [
            mean_sd(node.get(step, empty), 0.001)
            for step in (
                "EXTRACT_AUDIO",
                "TRANSCRIBE",
                "TRANSLATE_SUBTITLES",
                "GENERATE_LEARNING_PACKAGE",
            )
        ]
        lines.append(
            "|"
            + key
            + "|"
            + "|".join(values)
            + "|"
            + mean_sd(group["index_http_ms"], 0.001)
            + "|"
        )
    lines += [
        "",
        "## 逐次及分阶段记录",
        "",
        "|试次|终态 / 翻译|ASR CER %|冻结空输出惩罚 CER %|转写 s|翻译 s（含失败）|索引 HTTP s|观测终止/就绪 s|完整 API 元|ASR 失败/调用|",
        "|---|---|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for row in result["trials"]:
        stages = row["stage_ms"]
        available_cer = (
            number(row["cer"] * 100)
            if row["stage_outcomes"].get("TRANSCRIBE") == "completed"
            and row["cer"] is not None
            else "未运行/不可得"
        )
        cost = number(row["asr_list_price_cny"], 6)
        if row["asr_list_price_cny"] is None:
            cost += f"（已知请求小计 {row['known_successful_asr_call_fee_cny']:.6f}）"
        index = (
            (
                (row["index_status"] or {}).get("status", "未知")
                + " / "
                + number(
                    row["index_http_ms"] / 1000
                    if row["index_http_ms"] is not None
                    else None
                )
            )
            if row["index_status"]
            else "未运行"
        )
        lines.append(
            f"|{row['trial_id']}|{row['status']} / {row['translation_status']}|{available_cer}|{number(row['cer'] * 100 if row['cer'] is not None else None)}|{number(stages.get('TRANSCRIBE', 0) / 1000) if 'TRANSCRIBE' in stages else '未运行'}|{number(stages.get('TRANSLATE_SUBTITLES', 0) / 1000) if 'TRANSLATE_SUBTITLES' in stages else '未运行'}|{index}|{row['processing_to_index_ms'] / 1000:.3f}|{cost}|{row['asr_failed_calls']}/{row['asr_http_calls']}|"
        )
    lines += [
        "",
        f"ASR 传输失败 {result['asr_failed_calls']} 次，现有分片重试 {result['asr_chunk_retries']} 次。原始任务 retryCount、翻译可见批次/语义重试、提供方 retryCount 以及全部节点结果在 `summary.json` 逐次列出。失败翻译的持久记录可能没有已完成批次的输入/输出 token 明细或完整底层 HTTP 重试数；保留可见批次 totalTokens，不从总 token 或字符数反推缺失值。",
        "",
        "## 实际用量与可见重试",
        "",
        "ASR token/音频秒数只累加有 usage 的响应；缺 usage 的请求单列，以下不代表完整账单用量。本地 LLM 输入/输出 token 只列已有成本记录中的已知部分，缺失调用不补为零，完整试次用量可能仍不可得。",
        "",
        "|试次|ASR 输入/输出 token|ASR 响应音频秒|缺 usage 调用|ASR 分片重试|任务重试|翻译可见失败批次/已启动批次|翻译语义重试|翻译底层重试|本地 LLM 已记录输入/输出 token|",
        "|---|---:|---:|---:|---:|---:|---|---:|---|---|",
    ]
    for row in result["trials"]:
        tokens = row["asr_tokens"]
        model = row["model_tokens"]
        lines.append(
            f"|{row['trial_id']}|{tokens['input_tokens']}/{tokens['output_tokens']}|{number(row['asr_usage_duration_seconds'])}|{row['asr_usage_missing_calls']}|{row['asr_chunk_retries']}|{number(row['task_retry_count'], 0)}|{row['translation_batches_failed']}/{row['translation_batches_started']}|{row['translation_semantic_retries']}|{number(row['translation_provider_retry_count'], 0)}|{number(model['promptTokens'], 0)}/{number(model['completionTokens'], 0)}|"
        )
    lines += [
        "",
        "## 任务失败原因",
        "",
        "下表逐字聚合正式 trials.jsonl 的终态 errorMessage，不从耗时推断原因；节点结果仍见逐次 stage_outcomes。提供方 INVALID_REQUEST/HTTP 400 的更细原因若未记录，则不可得。",
        "",
        "|已记录终态原因|次数|",
        "|---|---:|",
    ]
    failures = Counter(
        row["task"].get("errorMessage") or "未记录"
        for row in records(REPORT / "batch-v2/trials.jsonl")
        if row["phase"] == "finished" and row["task"]["status"] == "FAILED"
    )
    for message, count in failures.items():
        lines.append(f"|{message.replace('|', '&#124;')}|{count}|")
    lines += [
        "",
        "## 方法与计量边界",
        "",
        "- 原音视频来源、字幕和 SHA-256 冻结于 `assets.lock.json`；逐讲署名、许可和人工字幕来源限制见 [SOURCES](SOURCES.md)。五课均为英文，没有本轮独立盲审的人类逐字复标或口音标签。",
        "- 原视频包含英文字幕。评测仅 stream-copy 第一条音视频轨，原包哈希不变；移除字幕轨避免当前 EMBEDDED_SUBTITLE_FIRST 复制参考。参考不上传。不做静音切分、降噪、时间戳修复、翻译参数调整或模型优化。",
        "- 概率课原容器有字幕尾部，使容器总时长比原音频长 0.197324 秒；去掉字幕轨后容器时长相应变化。原音频 start_time/time_base/duration_ts 和音视频包 SHA 均相同，未剪去音频。素材总量仍超过三小时，见 media-container-observation.json 和 checks/media-packets-final.json。",
        "- CER 按冻结 protocol：HTML/Unicode NFKC、casefold，去标记、非语音方括号和 speaker-style 前缀；逗号数字分组去除，独立整数/小数以 num2words 0.5.14 英文基数词统一；仅保留 Unicode 字母/数字，去空白和标点。Levenshtein 编辑距离除以参考字符数。无术语纠错；数字读法歧义和字幕编辑省略仍影响结果。",
        "- 使用在线同字节 JAR 和处理参数的本地临时实例，独立 MySQL schema/MQ namespace/loopback 端口；未重启或改配置在线服务。原 JAR 条目逐字节一致；额外 Java 观察器只对原 transport 响应读取 usage，返回原响应/异常，不增发请求、不缓存。观察器少量开销包含在基线内。",
        "- ASR 为百炼 qwen-audio-3.1-asr-flash，原 180s 固定分块、并发 2；翻译为本地 Qwen2.5-3B-Instruct Q4_K_M，alias lecturelens-local-qwen，4 线程、上下文 8192。翻译 batch concurrency 为 1，总时限 15 分钟。Embedding 使用既有本地 multilingual MiniLM。不能将本地推理按同名云 API 价格计费。",
        "- ASR 按实际 usage.input_tokens × 0.8/百万 + output_tokens × 2.7/百万计人民币目录价，来源为 [阿里云官方价格](https://help.aliyun.com/zh/model-studio/model-pricing)，核对日期 2026-10-15（北京）。`pricing.json` 保存来源与页面哈希。免费额度、折扣、最终账单和本机成本不在本指标中；音频秒数也不替代缺失 token。",
        "- 每节以完整输入尝试处理两次，串行运行；不并行运行 pytest/其他评测。共用常驻本地模型和基础服务，不声明专用硬件、线上 SLA、未见课程泛化、中文语音表现或时间戳准确性。缓存、网络和模型随机性均可能影响两次波动。",
        "",
        "## 保留的工具失败与预检",
        "",
        "根目录 `trials.jsonl/http-calls.jsonl/predictions/` 是无效 HTTP 代理批次：七个任务，两个长请求 ReadTimeout 后代理保护返回 402；不能用于生产失败率/CER/耗时比较。`attempt-01-status.json` 和最终任务状态保留解释。180s 直连诊断 6.521501 秒成功，之后改为直接委托原 Java transport 的响应 tee；正式数据仅 `batch-v2/`。未执行的开发驱动与初始语法错误源身份保留，不纳入样本。",
        "",
        "3s 静音预检、5s 语音预检及 180s 直连诊断分别保存在 readiness-probe.json、readiness-spoken-probe.json、direct-long-diagnostic.json，不计入十次正式试验；其已知用量与未知失败费用另列，不把预检当作完整课程样本。",
        "",
        f"正式批次、无效代理实际转发及预检的费用范围分别见 `cost-audit.json`。全部已观察成功响应的目录价小计 ¥{audit['all_observed_known_list_price_cny']:.9f}；总计 {audit['all_observed_usage_missing_calls']} 次失败调用缺 usage，费用不可得。预算保护为未知失败保留余额，保留额不是已发生费用，也没有并入单节成本。未读取账户账单。",
        "",
        "[VERIFY](VERIFY.md)提供结果文件哈希、每个数字的实际复算命令、测试和局限；[REPRODUCE](REPRODUCE.md)区分无 API 复算与付费重采集。",
        "",
        "MQ 失败的八次投递尝试（首次加七次重试）见 delivery-audit.json / batch-v2/delivery-log.txt，属于投递层，task.retryCount 仍为 0。broker 拒绝响应记录 CL/CQ/INDEX=0.91，测量后主机 df 为 91%。未清理用户文件、调高磁盘保护阈值、重试替换该失败或把未执行 ASR 计为一次成功转写。",
    ]
    print("\n".join(lines) + "\n", end="")


if __name__ == "__main__":
    main()
