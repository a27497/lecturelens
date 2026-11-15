"""Render an acceptance index from completed measurements and actual checks."""

import json
import xml.etree.ElementTree as ET

from score import REPORT


def main():
    result = json.loads((REPORT / "summary.json").read_text())
    coverage = json.loads((REPORT / "coverage-asr.json").read_text())
    checks = {
        p.stem: json.loads(p.read_text()) for p in (REPORT / "checks").glob("*.json")
    }
    assert checks and all(
        c["exit_code"] == 0
        for name, c in checks.items()
        if name != "media-packets" and "exit_code" in c
    )
    assert checks["media-packets-final"]["exit_code"] == 0
    suite = ET.parse(REPORT / "checks/mechanism-final.xml").getroot().find("testsuite")
    assert suite is not None
    assert not int(suite.get("skipped", "0"))
    assert not int(suite.get("failures", "0"))
    assert not int(suite.get("errors", "0"))
    lines = [
        "# P1-3 VERIFY：基线验收索引",
        "",
        "所有命令均从仓库根目录执行。以下正式数字只来自 `batch-v2/`；根目录旧代理批次、预检和开发失败均保留，未混入正式指标。离线复算不启动服务、不产生 API 费用。",
        "",
        "## 改动范围与结果哈希",
        "",
        "- `.gitignore` 单独提交 `455d944`：新增 `work/`、`*.pstats`，被忽略文件仍留在本机。",
        "- 本轮其余新增文件仅在 `eval/baseline-asr-20261015/`：来源/参考字幕、冻结身份、采集观察器和驱动、离线计量/机制测试、原始记录、报告及本验收索引。未修改运行时源码、生产配置或既有冻结评测结果。`checks/tracked-file-diff.json` 是测量后实际 Git 检查。",
        "- 完整新增文件清单见 `SHA256SUMS` 的路径列，逐文件列出报告、脚本、参考和原始记录 SHA-256；不对清单自身作循环哈希。媒体、凭据和本地完整日志留在 Git 忽略的 `.data/`。",
        "",
        "```bash",
        "sha256sum -c eval/baseline-asr-20261015/SHA256SUMS",
        "```",
        "",
        "## 每个数字的来源与复算",
        "",
        "|指标|本次结果|原始来源|复算入口|",
        "|---|---|---|---|",
        f"|课程、总时长|{result['lecture_count']} 节；{result['unique_audio_hours']:.9f} 小时|assets.lock.json 的 duration_ms；原文件/字幕 SHA|prepare.py；verify-media.py；verify.py|",
        f"|正式样本|{result['finished_trials']} 次，每课 2 次|batch-v2/trials.jsonl 的 submitted/finished 及 predictions/*.json|verify.py 的样本量断言；score.py 全量输出|",
        f"|已完成 ASR 的 CER|{coverage['completed_transcription_weighted_cer'] * 100:.9f}%；{coverage['edit_distance']} / {coverage['reference_characters']}，N={coverage['completed_transcription_scored_trials']}|参考字幕、原始输出及 TRANSCRIBE 完成日志|coverage_asr.py；概率课仅 1 个有效 CER，SD 不可得|",
        f"|冻结空输出惩罚 CER|{result['weighted_cer'] * 100:.9f}%；{result['edit_distance']} / {result['reference_characters']}，N={result['cer_scored_trials']}|references/*.vtt.txt 与 batch-v2/predictions/*.json 的 sourceFullText|verify.py；score.py 的 per_lecture/trials；包含 MQ 未执行 ASR 的空结果 100% 惩罚|",
        f"|终止/就绪耗时|均值 {result['processing_ms']['mean'] / 1000:.6f} 秒，N={result['processing_ms']['n']}|trials.jsonl 的 processing_to_index_ms，单调时钟原始观测|score.py 的 processing_ms/per_lecture/trials；样本 SD 为 ddof=1|",
        f"|成功索引 READY 耗时|N={result['successful_index_ready_ms']['n']}；缺失不估算|trials.jsonl 的 task/index_status|score.py 的 successful_index_ready_ms；失败耗时不冒充成功延迟|",
        "|分阶段均值、SD、逐次耗时|全部节点见 summary.json|batch-v2/pipeline-log.txt 的原始 durationMillis；pipeline-events.jsonl；index-http-calls.jsonl|collect-stages.py；score.py 的 stage_ms/per_lecture/trials|",
        f"|按目录价计费|完整用量试次 N={result['asr_list_price_cny']['n']}；已知成功请求小计 ¥{result['known_successful_asr_call_fee_cny']:.9f}；缺用量 {result['asr_usage_missing_calls']} 调用|batch-v2/http-calls.jsonl 的 usage；pricing.json 的官方 2026-10-15 北京价格|verify.py；score.py 的 asr_list_price_cny/asr_tokens/asr_usage_duration_seconds|",
        f"|失败与重试|终态 {json.dumps(result['task_status_counts'])}；ASR 失败 {result['asr_failed_calls']}，分片重试 {result['asr_chunk_retries']}|trials.jsonl、http-calls.jsonl、pipeline-log.txt、predictions 的 aiCallRecords|verify.py；score.py 的 *_retry*/translation_batches_*；缺失底层重试计数为不可得|",
        f"|机制测试|{suite.get('tests')} 通过，0 skip|checks/mechanism-final.xml；checks/mechanism-tests.json|下列 pytest 命令；不是模型质量测试或全量服务测试|",
        "|Ruff|实际 exit_code=0|checks/ruff.json；checks/ruff-format.json|下列 Ruff 命令|",
        "|MQ 投递失败|1 次任务；8 次投递尝试、7 次重试；broker 记录磁盘比率 0.91|batch-v2/delivery-log.txt；host-disk-after-measurement.json|delivery-audit.py|",
        "",
        "```bash",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/verify.py",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/score.py \\",
        "  | cmp - eval/baseline-asr-20261015/summary.json",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/collect-stages.py \\",
        "  --log eval/baseline-asr-20261015/batch-v2/pipeline-log.txt \\",
        "  --trials eval/baseline-asr-20261015/batch-v2/trials.jsonl \\",
        "  | cmp - eval/baseline-asr-20261015/batch-v2/pipeline-events.jsonl",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/prepare.py",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/verify-media.py",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/cost-audit.py \\",
        "  | cmp - eval/baseline-asr-20261015/cost-audit.json",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/render-report.py \\",
        "  | cmp - eval/baseline-asr-20261015/README.md",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/coverage_asr.py \\",
        "  | cmp - eval/baseline-asr-20261015/coverage-asr.json",
        ".data/baseline-asr-20261015/.venv/bin/python eval/baseline-asr-20261015/delivery-audit.py \\",
        "  | cmp - eval/baseline-asr-20261015/delivery-audit.json",
        ".data/baseline-asr-20261015/.venv/bin/python -m pytest \\",
        "  eval/baseline-asr-20261015/test_score.py -q -p no:cacheprovider",
        "agent-service/.venv/bin/ruff check agent-service eval/baseline-asr-20261015",
        "agent-service/.venv/bin/ruff format --check eval/baseline-asr-20261015",
        "```",
        "",
        "`checks/*.json` 保存实际命令、开始/结束 UTC、退出码和完整输出；测试在最后一个正式试次结束之后才运行。`checks/byte-recompute.json` 保存完整重新计算的 JSON，`checks/byte-comparison.json` 保存实际 cmp 的退出码。阶段投影也可完全从公开日志行复算。原 per_lecture/trials token、费用、均值、SD、min/max 仍由冻结 score.py 产生；追加的执行可用性和 MQ 计数由公开的独立脚本产生，没有改原始记录或冻结 summary。",
        "",
        "初版媒体校验错误地要求去字幕后的容器总时长严格相同，checks/media-packets.json 的失败回执保留。概率课有 0.197324 秒字幕尾时长，音频样本数和起始时刻不变；修正校验以实际音频时间字段和原音视频包 SHA 为准，最终通过回执为 checks/media-packets-final.json。初版报告的空任务 100% 惩罚展示保留在 report-initial-empty-penalty.md；最终 README 同时列冻结全任务惩罚和已完成 ASR 的 CER。可用性视图是在观察到 MQ 未执行情况后追加，未改变规范化、参考、模型输出或任何失败终态。",
        "",
        "## 原链路、来源与历史记录",
        "",
        "- `assets.lock.json` 冻结五个原视频 URL、官方英文 VTT URL/原字节 SHA、原视频与无字幕轨输入 SHA/时长/音视频流 SHA。`SOURCES.md` 列逐讲 MIT OCW 署名、CC BY-NC-SA 4.0 和许可链接。algorithms 主讲者初始元数据错误在 `metadata-errata.json` 更正为 Srini Devadas，未改冻结参考或原清单。",
        "- 原视频内嵌字幕会被生产 EMBEDDED_SUBTITLE_FIRST 直接使用，故仅 stream-copy 去掉字幕轨，未转码、截断或删除静音。`checks/media-packets-final.json` 实际验证音频 start_time/time_base/duration_ts 不变、无字幕轨及音视频原包 SHA 相同；概率课的容器元数据时长变短仅来自字幕尾。`checks/asset-hashes.json` 实际验证媒体/参考文件 SHA。",
        "- `batch-v2/freeze-v2.json` 是正式试次之前的冻结；原始 JAR SHA 与 943 条目逐字节校验在 `batch-v2/runtime-observer-identity.json`。追加的 `BaselineBootstrap.java` 仅在临时 JVM 观察原 Java transport 的响应 usage；原 class、请求、返回值、重试、模型及超时不变。原线上 PID 未重启。观察器开销计入测量。",
        "- `batch-v2/executed-driver-identity.json` 是完成首个试次后、其余九次执行前记录的实际 run-final.py 身份。首个有效试次由冻结 run-v2.py 运行；新驱动仅修复观测侧预算 null 处理与跨小时登录续期，未改变生产处理。verify.py 核对冻结文件与实际驱动 SHA。",
        "- `protocol.json`/`batch-v2/protocol.json` 的规范化在试次前冻结，不依结果改术语或数字。旧 cost 描述继承了 transparent proxy，正式批次追加 asr_meter 明确为原 transport 响应 tee。失败节点 durationMillis 与不可得字段的报告实现补全在首轮完整 CER 评分前完成，身份见 score-identity-final.json；没有改参考、规范化或样本。",
        "- 根目录 trials.jsonl/http-calls.jsonl/predictions 是旧代理无效批次，七个提交；attempt-01-final-task-status.json 保留最终读取。两次代理长请求 ReadTimeout、其余保护拒绝不能算生产故障样本。180s 直连诊断成功后换为 Java 响应 tee，未抹掉这些失败。",
        "- readiness-probe.json（3s 静音失败、费用不可得）、readiness-spoken-probe.json（5s 语音）和 direct-long-diagnostic.json（180s）是预检，费用与十个正式试次分开，不能混入课程样本。开发语法错误及未执行驱动源身份保留，不能算试次。",
        "",
        "## 局限与未运行项",
        "",
        "5 节英文公开课、每课仅 2 次尝试。实际完成 ASR 为 9 次，概率课第二次遭 MQ 拒收，只有 1 个可用 CER，未取得每课 2 个有效 ASR 样本；没有删除、替换失败或外推。不同讲者覆盖多种英语发音，但没有独立人类口音标注，不能外推中文、其他课程或线上分位数。MIT 官方专业字幕流程包含人工编辑/复核，但无这五文件的逐文件编辑日志，也无本轮独立盲审逐字重标；字幕编辑省略、公式与数字读法仍影响 CER。",
        "",
        "当前翻译超时与学习资料生成阶段的真实失败全部保留，具体终态原因逐字聚合于 README；不从 INVALID_REQUEST/400 推断未记录的细因。失败后没有进入的索引等节点为未运行，成功完成延迟 N=0 时为不可得。完整底层翻译 HTTP 重试和失败调用 token 不能从现有记录还原，未估算；本地 LLM 的已记录 token 是部分用量，不冒充完整试次用量。目录价不是扣费账单；缺 usage 的失败费用、免费额度、折扣、机器/电力成本不可得。共用常驻模型/基础设施，不声明独占主机；正式任务串行，未与测试/其他评测并跑。未做链路优化、静音切分改造、批翻译改造、续跑改造、时间戳准确率评测或生产部署；全量 Python/PostgreSQL、Java、前端测试本轮未运行，因为未改其运行时代码。付费重新采集顺序与依赖见 REPRODUCE.md。",
    ]
    print("\n".join(lines) + "\n", end="")


if __name__ == "__main__":
    main()
