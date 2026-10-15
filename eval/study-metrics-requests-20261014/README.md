# P0-2 工具请求口径与持久化数据库对照

本批修正只读报表的工具分母，不改变 runtime、存储格式或 Java。旧 `eval/study-metrics-20261014` 和两批 P0-1 文件未覆盖。原记录重新汇总见 [REPORT.md](saved-evaluations/REPORT.md) 和 [report.json](saved-evaluations/report.json)；完整口径见 [STUDY_METRICS.md](../../docs/STUDY_METRICS.md)。

## 工具字段变化

旧 `logical_tools` 只统计有 `tool_started` 的调用，漏掉执行前拒绝，不能称为全部模型请求的成功率。本批分别提供：

- `requested_tools`：已观察到的调用起点，加执行前 `tool_rejected`。匿名、非对象、缺失或非法工具名归工具组 `unknown`，结局仍明确是 rejected。
- `executed_tools`：仅有 `tool_started` 的逻辑调用。执行前拒绝不进入该口径；开始后被内部校验拒绝的调用计 rejected。
- `logical_tools`：保留为 `executed_tools` 的兼容别名。
- `tool_totals.requested/executed`：各队列总计；两种口径均提供成功/失败/拒绝/未知计数，成功/失败/拒绝率，并按工具名和失败或拒绝类别拆分，附样本量、UTC 范围。

三种比率的共同分母为 **成功+失败+拒绝**；未知结局单列，零分母的比率不可得。拒绝不并入 failed，读取重试不新增逻辑调用。决定节点携带上一轮调用 ID 时，不能把新请求拒绝归入上一轮成功工具；已开始调用的内外层重复拒绝只算一次；顶层 CHECK 参数拒绝不算模型工具请求。

请求口径是可观察的请求/拒绝边界，不能重建历史未保存的模型响应。匿名或整个协议响应的拒绝记一个观察边界，原始工具数和名称不可得。旧日志若未记录拒绝事件，请求计数完整度不可得，不能宣称统计了所有模型输出工具。这些缺失不根据场景名或私有原文补估。

## 原 1,260 Run 回归

仍为 **1,260 Run / 63 cohort**，输入 SHA256 与旧报表一致。逐项比较每个 cohort 的所有原有非工具字段：终态、模型/预算/usage、每 Run 资源、统计时间范围、失败事件计数以及全部端到端/模型/MCP 延迟 **完全一致**。核对结果在 [regression-comparison.json](regression-comparison.json)。只新增或调整上述工具口径字段及工具比率说明。

14 个候选 cohort 新增执行前拒绝：`candidate-final` 和 `faults-candidate` 各 7 类场景，各 **N=20**（integer_overflow、negative_parameter、oversized_parameter、reversed_window、unknown_tool、illegal_call_shape、protocol_persistent）。例如 integer_overflow、unknown_tool 均由“旧逻辑工具为空”变为“请求 unknown 工具组拒绝 20、成功率 0%、拒绝率 100%；执行 N=0，比率不可得”。实际工具名没有保存，未猜测为检索工具。

|批次标签（各 300 Run，各场景 20）|口径|调用 N|成功|失败|拒绝|未知|成功率|失败率|拒绝率|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
|candidate-final|请求|440|240|60|140|0|54.55%|13.64%|31.82%|
|candidate-final|执行|300|240|60|0|0|80.00%|20.00%|0.00%|
|faults-candidate|请求|440|240|60|140|0|54.55%|13.64%|31.82%|
|faults-candidate|执行|300|240|60|0|0|80.00%|20.00%|0.00%|

上表只演示分母变化，混合场景比率不是生产成功率或教学质量；各场景贡献样本的精确 UTC 范围在 JSON 和 Markdown 中。基线历史缺失的拒绝事件不补造，也不将基线非法请求后的运行成功改判为教学质量通过。旧受并发负载污染的延迟仍保留原值，不用于空闲性能结论。

复现这份完整报表：使用 [上一批七个 --records 参数](../study-metrics-20261014/README.md#复现)，输出到新的不存在目录。本批已实际用 `uv run --project agent-service python scripts/eval/report-study-metrics.py` 复跑，JSON/Markdown 逐字节一致。

## 真实持久化 Run 对照

[persisted-runs.py](persisted-runs.py) 通过实际 `StudyStore` 和 `StudyRuntime` 创建、执行并保留 Run，复用冻结故障夹具的 `FaultProvider`。Authority 是本地内部桩，SEARCH 第一次实际抛出 `MCP_AUTHORITY_UNAVAILABLE`，由现有持久预算内重试恢复；不是向表中手工插入伪造执行结果，不调用生产 Java 或真实模型。

独立临时 PostgreSQL 17.11/pgvector 容器中，5 类各 **N=3，共 15 Run**。Run、Session、事件和 checkpoint 在两条 CLI 汇总前后均保留；审计记录见 [persistence-audit.json](persistence-audit.json)。统计范围 **2026-10-14 11:07:19.400690–11:07:23.998029 UTC**。

|场景|Run N|成功 Run / 失败 Run|模型调用|请求：成功/失败/拒绝|执行：成功/失败/拒绝|
|---|---:|---|---:|---|---|
|healthy|3|3 / 0|12|9 / 0 / 0|9 / 0 / 0|
|unavailable_once|3|3 / 0|12|9 / 0 / 0|9 / 0 / 0|
|integer_overflow|3|0 / 3|3|0 / 0 / 3|0 / 0 / 0|
|unknown_tool|3|0 / 3|3|0 / 0 / 3|0 / 0 / 0|
|illegal_call_shape|3|0 / 3|3|0 / 0 / 3|0 / 0 / 0|

DB 和对应 JSONL 两条 CLI 路径结果一致：**6 成功、9 失败、33 模型调用、21 工具预算计数、3 次读重试**；请求 **27 次，18 成功、9 拒绝**，成功率 **66.67%**、拒绝率 **33.33%**；执行 **18 次，全部成功**。三个拒绝类别（invalid_parameters、model_tool_selection、model_protocol）各 3 次，工具名均归 unknown。

[compare-persisted.py](compare-persisted.py) 实际调用报告 CLI 的 `--database` 与 `--records`，并按清单的 Run ID 对每个场景再次调用 `--database --run-id ...`。逐 Run 对照终态与资源计数，逐场景对照工具计数、比率、类别、模型调用、持久化端到端及模型延迟。结果在 [comparison.json](persisted-comparison/comparison.json)；两路原始报表在 [DB 报表](persisted-comparison/database/REPORT.md) 和 [JSONL 报表](persisted-comparison/jsonl/REPORT.md)。读取前后 **15 Run / 720 事件**及 Session/产物/checkpoint 数量、Run 行版本和审计 SHA256 一致，没有写入。

数据范围差异已明确记录：

- DB 不持久化评测 `elapsed_ms`，所以 evaluation_execute_ms 不可得；JSONL 记录了该计时。
- DB 保留 node/evidence 耗时元数据，公开 JSONL 不含这些私有事件，故该节点/证据耗时仅 DB 路径可得。只投影元数据，没有导出私有 Trace 内容。
- DB 未保存场景、标签、fixture 身份，完整 DB 报表为一个队列，JSONL 为五个。对照用显式 Run ID 清单分组，不给 DB 伪造历史身份。
- 内部 Authority 桩没有 MCP observer，两路 MCP 传输指标均不可得。金额和有模型调用的 mock usage 均不可得。

复现新持久化批次时，先启动一个空的本地 PostgreSQL/pgvector 临时实例，数据库名 `lecturelens_agent_test`；将 `AGENT_TEST_DATABASE_URL` 和 `AGENT_DATABASE_URL` 都指向该实例，再执行：

```bash
# 输出目录须新建；以下示例选择一条新的记录路径。
mkdir -p .data/study-metrics-persisted-local
uv run --project agent-service python eval/study-metrics-requests-20261014/persisted-runs.py \
  --samples 3 --output .data/study-metrics-persisted-local/runs.jsonl
uv run --project agent-service python eval/study-metrics-requests-20261014/compare-persisted.py \
  --records .data/study-metrics-persisted-local/runs.jsonl \
  --output-dir .data/study-metrics-persisted-local/comparison
```

生成器拒绝已有 Run 的数据库，不删除任何 Run。对照程序要求库内 Run 与输入清单完全一致，避免混入其他数据。本轮临时实例 `lecturelens-metrics-requests-0` 在 localhost:15508 保留供复核；不属于服务部署，完成复核后可 `docker stop lecturelens-metrics-requests-0` 清理该临时实例。

## 测试与未覆盖项

新增 **9 项**手算/边界测试（指标模块共 27 项），覆盖执行前拒绝只进入请求分母、未知/非对象工具、决定节点旧 call_id、重复拒绝去重与顶层 CHECK 排除。全量 **691 passed / 0 failed / 0 errors / 0 skipped**；四个独立 PostgreSQL 容器运行测试，与另一个持久化样本实例分离，收集清单和 JUnit 逐项核对恰好运行一次。[verification.json](verification.json) 保存验证结果和源码身份。ruff check 与 format --check 均通过。

没有实测生产用户数据、真实模型/Java/MCP 持久化批次、取消/预算耗尽/拒答、checkpoint 恢复或历史截断事件的 DB/JSONL 对照，这些补充场景 **未运行**。持久样本只验证内部桩故障下的机制与报表一致性；未重新认定模型质量，未估算金额，未 push。
