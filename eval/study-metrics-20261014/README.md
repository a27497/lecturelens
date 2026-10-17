# Study Agent 只读指标汇总

新增 `scripts/eval/report-study-metrics.py`，从现有记录生成执行指标，未更改 runtime、数据库格式、Java 或旧评测文件。它复用 `study/trace.py` 的实际 usage 缺失判断、现有失败分类和旧评测的 nearest-rank 口径；`study/costs.py` 是学习任务的复杂度计算，没有可复用的金额账本。完整用法与定义见 [STUDY_METRICS.md](../../docs/STUDY_METRICS.md)。

## 本轮数据与报表

- [REPORT.md](saved-evaluations/REPORT.md)：队列总览。
- [report.json](saved-evaluations/report.json)：完整指标、逐 Run 用量、工具及失败类别、节点/模型/MCP 延迟、各项样本量与 UTC 范围、输入 SHA256。
- [verification.json](verification.json)：实际测试计数、完整 collection 覆盖核对、工具源码 SHA256 和字节级复现核对。

读取 7 个已保存 JSONL 文件，共 **1,260 Run / 63 cohort**；UTC 范围 **2026-10-14 06:55:32.707808–08:11:57.484434**。均为公开合成目标、确定性 provider、本地 HTTP/MCP 故障夹具的记录，不是生产用户数据或真实模型教学质量评测。没有新跑故障评测，也没有将本轮测试运行混入这 1,260 条记录。

|来源与标签|Run N|成功|拒答|失败|取消|预算耗尽|持久模型预算计数|
|---|---:|---:|---:|---:|---:|---:|---:|
|原故障批次 baseline-final-56bc07a|300|100|0|200|0|0|620|
|原故障批次 candidate-final|300|80|0|220|0|0|560|
|串行复核 faults-baseline|300|100|0|200|0|0|620|
|串行复核 faults-candidate|300|80|0|220|0|0|560|
|串行健康 healthy-baseline|20|20|0|0|0|0|80|
|串行健康 healthy-before|20|20|0|0|0|0|80|
|串行健康 healthy-candidate|20|20|0|0|0|0|80|

每个故障批次包含 14 类故障各 20 次以及健康控制 20 次；JSON 按场景分队列，没有把不同故障分布合并成一个可靠性成功率。基线对部分非法参数的继续成功仍按原记录保留，不改判为质量通过。两批候选各记录 160 次读重试；逻辑工具、MCP 传输尝试和失败事件各有独立分母。

## 健康路径延迟口径

同一串行健康批次，以下各指标均 **N=20**，nearest-rank，包含所有已保存终态。时间范围以该标签 20 个 Run 的完整生命周期为界：

|标签|UTC 范围|持久化端到端 P50/P95 ms|评测 execute P50/P95 ms|
|---|---|---:|---:|
|healthy-baseline|07:53:17.874042–07:53:50.525333|1528.927 / 1609.390|1514.622 / 1591.813|
|healthy-before|07:53:52.503484–07:54:49.273730|2677.884 / 3269.230|2668.664 / 3257.275|
|healthy-candidate|07:54:51.244019–07:55:11.204459|886.935 / 956.287|871.212 / 941.159|

持久化端到端从 `created_at` 到 `finished_at`，包括开始执行前的准备与排队；历史性能报告的 `elapsed_ms` 计时包围 `runtime.execute`。**两组数值不是同一指标。** 本轮没有重新测量这些延迟，数字全部重新计算自保存记录。

原报告中的 **+1.91/+3.44 s** 受候选评测与四组全量 pytest 并发污染；空闲主机验收方复跑的基线 1405/2022 ms、候选 2636/3215 ms 是用户提供的独立复核结论，其逐 Run 原始文件本轮没有获得，未混入报表。上表来自仓库已保存的串行批次，作为可核对的修复前后依据。旧批次仍可读取，但不用于空闲健康路径性能结论。污染过程及 profiling 证据见 [上一轮延迟报告](../tool-resilience-latency-20261014/RESULTS.md)。

## 复现

仓库根目录，安装锁定 Python 依赖后执行一条命令；换一个不存在的输出目录，不覆盖本轮结果：

```bash
uv run --project agent-service python scripts/eval/report-study-metrics.py \
  --records eval/tool-resilience-20261014/baseline.jsonl \
  --records eval/tool-resilience-20261014/candidate.jsonl \
  --records eval/tool-resilience-latency-20261014/serial-clean/healthy-baseline.jsonl \
  --records eval/tool-resilience-latency-20261014/serial-clean/healthy-before.jsonl \
  --records eval/tool-resilience-latency-20261014/serial-clean/healthy-candidate.jsonl \
  --records eval/tool-resilience-latency-20261014/serial-clean/faults-baseline.jsonl \
  --records eval/tool-resilience-latency-20261014/serial-clean/faults-candidate.jsonl \
  --output-dir eval/study-metrics-local
```

已实际用该 `uv --project` 命令在另一个临时目录复跑；JSON 和 Markdown 均与本轮文件逐字节相同。没有基于报告里的手写数字生成指标。

## 验证与局限

新增 **18 项**指标测试，包含手算 token 与 P50/P95、拒答/失败/取消/预算分布、部分 usage、未完成调用、重试恢复与最终失败分离、版本/场景分组、重复 Run 拒绝、时间过滤、正文/凭据隔离、输出不覆盖和真实 PostgreSQL 只读快照。

全量 **682 passed / 0 failed / 0 errors / 0 skipped**。四个独立 PostgreSQL 17.11/pgvector 容器的测试库隔离运行；收集到的每项测试与 JUnit 逐项核对，恰好执行一次。分组命令/计数在 [verification-groups.json](verification-groups.json)，日志和 XML 为 `tests-group-{0..3}.log/xml`。`ruff check agent-service scripts/eval/report-study-metrics.py` 通过；`ruff format --check agent-service/src agent-service/tests scripts/eval/report-study-metrics.py` 通过（82 文件）。未修改 Java，Java 测试未运行。

金额均 **不可得**：现有记录没有金额和币种。含模型调用的本批 mock Run 没有 provider usage，token 不可得；零模型调用 Run 的实际用量可确认是 0。公开事件不含私有节点耗时，本批分节点指标 **不可得**；从数据库读取已存在的 node 事件可生成该指标，已由 PostgreSQL 集成测试验证，本轮未导出生产数据库或私有 Trace。

本批实际数据没有拒答、取消或预算耗尽案例；这些统计分支由单元测试验证，真实评测覆盖 **未运行**。公共 EVENTS 可能分页/截断，工具未知结局单列 unknown，不能把缺失事件当成成功或失败。没有验证 provider 计费一致性、生产排队延迟或真实模型质量；没有补充记录字段，无法追认历史记录没有保存的代码版本与测量值。后续对外数字应引用具体 cohort、指标名、N、UTC 范围及来源 SHA256。
