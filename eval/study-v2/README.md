# Study v2：草稿复核的真实模型回放试验

## 范围与冻结

- 来源：[MIT 6.0001 Fall 2016 第 4 讲](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-4-decomposition-abstraction-and-functions/)，Ana Bell；采用官方英文字幕中约 20:54–24:25 的函数返回值片段。许可、下载地址与 SHA-256 见 [sources.json](sources.json)。没有将模型生成的材料当作课程。
- [cases.json](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/study-v2/cases.json)：6 个新的保留任务，4 个课程内目标、2 个课程外目标；覆盖解释、对比、输入变化、纠错与证据不足。题目由 AI 根据字幕设计，未向运行模型提供评分要点。
- 固定模型 Qwen2.5-3B-Instruct Q4_K_M，llama.cpp b10977，4 线程，单并发，8192 上下文；默认 90 秒和原有调用/token 预算不变。[完整配置](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/study-v2/runtime.json)
- 旧候选是上一轮冻结运行时 `.data/l22-eval/final-src`；新候选在查看本轮任何模型产物前冻结至 `.data/study-v2/review-src`。每行记录候选、任务集、字幕和 Evidence 摘要；新 label 不得覆盖旧记录。

这是 **真实本地模型 + 生产 Python LangGraph + 真实 PostgreSQL** 的运行时试验。Evidence 边界使用从官方字幕顺序合并的六条固定片段，检索时始终返回这个范围，包括课程外问题；没有用预设答案或 HTTP mock 替代模型。它不是媒体上传、向量召回、Java 权限或浏览器全链路验收。不能用固定片段的引用一致性证明真实检索质量。

两个候选依次执行全部任务；没有随机顺序或多次重复。两个候选首题分别短暂与前端/Python 验证重叠，并共用 CPU；延迟仅用于诊断，不是严格受控的性能比较。没有为避免超时而扩大预算。

## 评分与报告

完整产物另由 Codex 对照原始字幕进行 AI 复核，包含私有答案和每题引用；不是盲评或人工金标。运行时模型自己的接受/拒绝判断不充当语义评分。沿用 Study v1 的解释/答案、引用支持、题型区别、正确拒答、严重错误与 90 秒要求，并保留全部失败。

结果：[旧运行时](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/study-v2/baseline-report.json)、[复核候选](review-report.json)。这些是六题诊断试验的分数；`full_l2_gate_assessed=false`，不替代完整的 L2.2 质量准入评测。新保留题经阅读后只能用于回归分析，后续调参需要另外选取未见任务。

## 本轮结果与决定

| 指标 | 旧运行时 | 复核候选 |
| --- | --- | --- |
| Run 成功 | 5/6（其中 1 份是课程外幻觉练习） | 0/6，全部预算耗尽 |
| 课程内完整语义任务达标 | 0/4 | 0/4，没有可评分产物 |
| 课程外正确拒答 | 0/2 | 0/2 |
| 全结果 P50 / P95 | 54.86 / 79.28 秒 | 90.05 / 90.11 秒 |
| 模型调用 / 工具调用 | 12 / 11 | 18 / 11 |
| 完成复核 / 拒绝草稿 / 修订后成功 | 0 / 0 / 0 | 1 / 1 / 0 |

复核候选发起 5 次复核，只有一次返回可提交的判断。`return-04` 的拒绝反馈触发了第 4 次模型决策，但没有时间完成修订。该复核部分理由错误：它对 practice 草稿标注了 `unjustified_abstention`，并否认草稿已解释的打印/返回区别；虽在文字中发现题型重复，也未选对应错误代码。不能把这次拒绝当作可靠的事实校验。

候选实际记录到的 usage 为 14,638 输入 / 1,943 输出 tokens；6 次调用缺少完整 usage，不能记为零成本。旧运行时有 1 次缺失。保守预算预留仍与实际 usage 分开统计。

**结论：执行机制已实现，质量修复和默认延迟验收失败。** 没有产物发布只说明运行未完成，不能声称纠错成功或可靠拦截全部错误。四个课程内任务的 0/4 是任务达标率，不代表四份已完成答案都被判错。

本轮保留机制与失败试验供后续验证；Study Agent 仍默认关闭，这套本地推理配置不能作为通过验收的演示配置。下一步先用开发任务比较生成与复核的准确性、输入成本和总延迟，选定更合适的模型/推理配置后，再冻结新的保留任务；L3 继续暂缓。

12 个回放会话的 Session、Run、产物、事件、工具结果及三个 checkpoint 表均已清理为零；原始失败记录和冻结源码保留。验证见 [verification.json](verification.json)。

## 复现

先启动已配置的本地模型服务和隔离 PostgreSQL，设置 `AGENT_TEST_DATABASE_URL`（数据库名必须为 `lecturelens_agent_test`）、`AGENT_LLM_BASE_URL`、`AGENT_LLM_MODEL`。不要同时运行 Agent worker 或其他模型评测。

```bash
# PYTHONPATH 指向本次要验收的冻结 src 目录；同一组不得变更模型、代码或预算。
PYTHONPATH=/absolute/frozen/src uv run --directory agent-service python \
  ../scripts/eval/replay-study-quality.py --label new-cohort \
  --output ../.data/study-v2/new-cohort.jsonl

# 每题提供 grounded / answers_correct / questions_distinct / serious_unsupported
# 布尔值，以及 reviewer / reason。不能把运行时质量事件直接转换成评分。
python3 scripts/eval/report-study-quality.py \
  --results .data/study-v2/new-cohort.jsonl \
  --reviews .data/study-v2/new-cohort-reviews.json \
  --output /tmp/study-quality-report.json
```

回放脚本校验字幕 hash、冻结运行时身份、拒绝覆盖已有试验；报告脚本沿用既有汇总逻辑，禁止混合候选或任务集。原始结果为 0600，包含草稿、反馈、私有答案、工具记录和事件，保留在 Git 忽略目录。每题记录落盘后清理自己的 Session/Run/checkpoint，保留失败结果文件。
