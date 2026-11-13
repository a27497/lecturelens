# 验证与复现

仓库 `/home/dev/projects/lecturelens`，起点 `b82bebf6b15e33b25e7ffcb822133f97481e6073`。本轮没有修改 Python Agent、迁移脚本、配置、冻结候选或历史验收文件。

## 改动文件

| 路径（backend/src/ 下） | 作用 |
| --- | --- |
| main/java/com/example/courselingo/systemmodel/SystemModelChatClient.java | legacy 全文翻译的结构化响应解码；保留已有 HTTP 重试及其计数 |
| main/java/com/example/courselingo/ai/llm/TranslationResponseDecoder.java | 共用截断优先解码；legacy finish 兼容与 V2 stop 门禁 |
| main/java/com/example/courselingo/ai/llm/TranslationFailure.java | 非对象细分原因及已消耗的传输重试计数 |
| main/java/com/example/courselingo/ai/llm/LlmStageException.java | 固定字段安全诊断 |
| main/java/com/example/courselingo/subtitle/service/SubtitleTranslationServiceImpl.java | 截断进入已有拆分路径；失败调用独立统计；安全日志 |
| test/java/com/example/courselingo/systemmodel/SystemModelLegacyTranslationTest.java | HTTP 200 空 content/length 的复现、正常与无效输出、路由无降级、HTTP 重试兼容 |
| test/java/com/example/courselingo/systemmodel/SystemModelTranslationObservationTest.java | 固定原因与状态码；stop 成功样例；传输重试保持原边界 |
| test/java/com/example/courselingo/subtitle/SubtitleTranslationServiceTest.java | 有限恢复、不可拆、深度耗尽、格式错误拒绝、失败调用统计与发布门禁 |
| test/java/com/example/courselingo/task/runner/TranslateSubtitleSegmentsStepTest.java | 包装异常仍记录失败及安全细分原因 |
| test/java/com/example/courselingo/systemmodel/SystemModelRuntimeMySqlTest.java | 更新结构化无效输出的 typed 异常断言；本轮未运行 MySQL 集成测试 |

## 实跑记录

| 运行 | tests | failures | errors | skipped | 退出 |
| --- | ---: | ---: | ---: | ---: | ---: |
| translation-output-red（修复前） | 2 | 1 | 1 | 0 | 1 |
| translation-output-targeted（错误的新增算术期望，已保留） | 123 | 1 | 0 | 0 | 1 |
| translation-output-targeted-v2 | 126 | 0 | 0 | 0 | 0 |
| translation-output-regression（最终代码） | 311 | 0 | 0 | 0 | 0 |

最终 24 个测试类覆盖客户端、provider 适配、响应解析、诊断存储、legacy/V2 翻译、预算与拆分协调、checkpoint 执行、失败记录刷新和任务失败状态。测试采用 fake/mock provider；H2 仅进程内创建，未访问在线数据库。全量 Java/MySQL、Python/PostgreSQL 与真实供应商行为均未测，不将本次回归描述为全栈验收。

公开计数与报告哈希：`red-check.json`、`translation-output-*-check.json`。私有完整日志为 `.data/translation-output-20261016T183359Z/<运行名>/output.log`，退出/清理记录为同目录 `run.json`；对应 Surefire XML 在 `.data/translation-output-20261016T183359Z/<运行名>-reports/`。报告按各次开始时间筛选后立即归档，未用旧报告补数。每次调用都由 `scripts/dev/run_check.py` 监督，`nohup + timeout` 作为外层期限；所有 cleanup.complete=true、remaining=[]，runner 和 Maven PID 均已消失，见 `closeout.json`。

准确的各次 argv 与 shell 命令保存在 `commands.json`。重新运行最终回归时使用新名字，避免覆盖证据：

```bash
cd /home/dev/projects/lecturelens
nohup timeout --kill-after=10s 360s python3 scripts/dev/run_check.py \
  --name translation-output-regression-recheck \
  --output-root .data/translation-output-20261016T183359Z --cwd backend --timeout 300 -- \
  ./mvnw -o -B \
  '-Dtest=SystemModelLegacyTranslationTest,SystemModelTranslationObservationTest,SystemModelTranslationV2Test,SubtitleTranslationServiceTest,TranslateSubtitleSegmentsStepTest,TranslationCallDiagnosticsTest,SubtitleTranslationResponseParserTest,PipelineTranslationServiceTest,TranslationBatchCoordinatorTest,TranslationAdaptiveBatchTest,AdaptiveTranslationControllerTest,TranslationFailureDiagnosticTest,LlmProviderFailureClassifierTest,ObservedModelCallTest,OpenAiCompatibleLlmProviderTest,LangChain4jLlmProviderTest,OpenAiCompatibleRequestOptionsAdapterTest,SubtitleTranslationPromptFactoryTest,SubtitleTranslationPropertiesTest,PipelineAnalysisTaskRunnerFailureTest,PipelineAnalysisTaskWorkExecutorTest,PipelineCheckpointExecutionTest,PipelineF6FailureFlushTest,AiModelRouterTest' \
  test > .data/translation-output-20261016T183359Z/regression-recheck-launcher.log 2>&1 < /dev/null &
```

等待新运行的终态后，先归档新鲜报告，再做其他测试：

```bash
python3 eval/translation-output-20261016T183359Z/archive_check.py translation-output-regression-recheck
```

## 诊断与保护

`diagnosis.json` 保存 11 个任务的脱敏事件、时间、历史 PID、阶段与配置版本，以及唯一细分诊断和部署包身份。`diagnosis-collector-attempt01.json` 是已作废的第一次采集（ANSI 颜色重置破坏了 event 的单词边界匹配，错误结果为 0）；修正为匹配固定事件名后得到 11，不覆盖原尝试。它不是另一个故障样本或有效空队列结论。

只读重查固定历史窗口（新输出路径）如下；结果依赖 journal 保留期限。脚本只保存白名单字段，不输出原始日志、课程或响应正文；当前在线 PID 的检查固定为本次已核实的 4866，未来进程变化不能据此继续假定相同部署。

```bash
python3 eval/translation-output-20261016T183359Z/collect_diagnostics.py \
  --since '2026-10-14 18:36:00 UTC' --until '2026-10-16 18:36:52 UTC' \
  --output .data/translation-output-20261016T183359Z/diagnosis-recheck.json
```

无需重新访问在线日志即可复核已保存计数：

```bash
python3 - <<'PY'
import json
from pathlib import Path
x = json.loads(Path('eval/translation-output-20261016T183359Z/diagnosis.json').read_text())
assert len(x['tasks']) == len({t['task_id'] for t in x['tasks']}) == 11
assert sum(bool(t['archived_diagnostics']) for t in x['tasks']) == 1
for t in x['tasks']:
    for d in t['archived_diagnostics']:
        print(d['http_status'], d['finish_reason'], d['provider_reason'],
              d['prompt_tokens'], d['completion_tokens'], d['total_tokens'])
PY
sha256sum --check --quiet eval/translation-output-20261016T183359Z/SHA256SUMS
git diff --check
```

`before.json` 与 `closeout.json` 比较 141 个历史证据文件哈希、在线 JAR 与 P2-1c 冻结 JAR 哈希、在线 PID/启动时刻，以及原有未提交 DIAGNOSIS.md 的 inode/大小/mtime。该未提交文件正文未读取，元数据保持一致；没有将它提交。本次源码变化不改写旧验收结论，也不能要求旧源码哈希等于修复后的工作树。SHA256SUMS 从仓库根目录复核本轮文件、源码、私有日志与报告，不包含它自身。

收尾磁盘使用率为 75.552%，距 85% 阈值约 13.628 GiB（具体字节数在 `closeout.json`，按字节计算）；各测试的前后磁盘门禁记录在 run.json。未启动或重启在线服务，未触发真实供应商调用，未部署、push 或 merge。
