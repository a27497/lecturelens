# Study Agent 持久记录指标

`scripts/eval/report-study-metrics.py` 是只读运维汇总入口。它从现有 PostgreSQL 元数据或明确指定的已保存 JSONL 快照生成 `report.json` 和 `REPORT.md`，不启动 Agent、不补写事件、不修改 checkpoint 或存储格式。优化与对外数字应引用报表中的具体 cohort、指标名、样本量和 UTC 范围；内容质量仍按独立的语义评测报告判断。

## 命令

在仓库根目录执行，先按 `agent-service/README.md` 安装锁定依赖：

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

该命令的文件参数和输出目录按执行命令的当前目录解析；`uv --project` 选择 Python 项目并保留当前目录。已有环境也可用 `agent-service/.venv/bin/python scripts/eval/report-study-metrics.py ...`。输出目录必须不存在。可重复 `--records`、`--label`、`--scenario`；不递归搜索目录，以免重复读入 worker 文件、合并文件和历史试跑。相同 Run ID 重复输入会失败。

读取当前数据库时，从环境变量提供运维数据库连接，建议使用仅有 SELECT 权限的账号。连接字符串不进入日志或报表：

```bash
# AGENT_DATABASE_URL 已由本地安全环境提供。
uv run --project agent-service python scripts/eval/report-study-metrics.py \
  --database --since 2026-10-14T00:00:00Z --until 2026-10-15T00:00:00Z \
  --output-dir .data/study-metrics-20261014
```

`--since` 包含边界，`--until` 不包含边界，均按 Run 的 `created_at` 选择，必须带时区。`--run-id ID` 可重复，只限制数据库输入。没有时间戳的文件记录仍可汇总并列出缺失数量，但不能应用时间过滤。空数据生成 N=0、测量不可得的报表。

数据库读取使用单个 `REPEATABLE READ READ ONLY` 快照，SQL 只投影状态、计数、时间戳、产物类型和白名单事件字段。不读取目标、课程正文、参数、答案、`_trace`、`trace_detail` 或 provider 凭据。不提供面向浏览器的接口，也不替代私有 Trace/Replay 的 Java 授权。输出目录权限 0700，文件权限 0600；分享前仍应检查来源路径、Run ID 和队列身份等元数据，不提交私有原始快照。

## 统计口径

|指标|来源与含义|缺失处理|
|---|---|---|
|Run 终态|`study_run.status`；成功产物 `kind=insufficient_evidence` 单列拒答|成功但无产物类型归 unknown；queued/running 单列 nonterminal|
|模型请求工具口径 `requested_tools`|已观察到的逻辑调用起点，加执行前 `tool_rejected` 拒绝边界|拒绝进入分母；匿名、非对象、缺失或非法工具名归工具组 unknown；不读取私有响应以猜名称或原始工具个数|
|已执行逻辑口径 `executed_tools`|仅有 `tool_started`，按 `call_id` 关联结束、工具节点失败、依赖停止和执行内部拒绝|执行前拒绝不进入该口径；已开始调用在内部被拒绝时计 rejected；缺失结局归 unknown|
|失败类别|优先使用持久化 `failure_category`，历史错误码复用现有分类函数|未知分类明确列 unknown；症状分类不代表语义根因|
|底层调用|夹具 `mcp_events` 的 `tools/call`；DB 的 `evidence_finished/failed` 另列，后者不含 CHECK|不与模型选择工具混算；MCP 返回不证明响应内容合法|
|模型调用与重试|持久 `model_calls`、模型 started/completed 事件、`tool_retry_started`|预算计数与调用事件并列，取消窗口可能不一致；历史事件可能缺失|
|token|复用 `study/trace.py::metrics`，包含 model_finished/failed 中实际记录的 prompt/completion usage|完整 Run 总量仅在全部调用字段齐全时可得；部分已知用量与缺失调用另列；reserved_tokens 不是用量|
|金额|当前持久化格式没有金额、币种或实际计费账单|不可得；不根据价格表、字符数、预留预算或 token 估算。`study/costs.py` 是学习题目的算法复杂度，不是财务费用|
|持久化端到端 ms|`finished_at-created_at`，含排队、准备、重启与恢复|无起止时间的 Run 不进入分位数，不以当前时钟填补|
|评测执行 ms|JSONL 的 `elapsed_ms` 或旧格式 `elapsed_seconds*1000`|独立指标，不替代持久化端到端|
|分节点 ms|已保存 node_finished/node_failed 的 duration_ms；另列模型、证据、MCP 调用耗时|公开 EVENTS 不含节点事件，因此仅有公开快照时标不可得；取消前未记录终点的节点无可用耗时|

P50/P95 使用已有评测的 nearest-rank：排序后的第 `ceil(N*p)` 个观测值，包含成功、失败及拒答的已记录测量，不插值。每项附 `sample_count`、统计窗口；延迟的样本是节点/调用次数，`population_count` 是该队列 Run 数，二者不能直接作为完整率。节点耗时包含嵌套模型/证据调用，不能相加作为总耗时。时间范围为贡献样本所属 Run 的 UTC 生命周期，不虚构没有保存的事件时间。

两种工具口径分别提供 `success/failed/rejected/unknown` 计数，按工具名称分组，并将失败和拒绝类别分别拆入 `failure_categories/rejection_categories`（各自附样本量与时间范围）。比率的共同分母是 `success+failed+rejected`：成功率、失败率、拒绝率分别用对应计数除以该分母；未知结局单列，分母为 0 时比率不可得。`tool_totals.requested/executed` 提供队列级计数和比率。`logical_tools` 保留为已执行口径的兼容别名，不再把它称为全部模型请求的成功率。

工具组 `unknown` 与结局 `unknown` 不同：一个匿名拒绝的结局仍明确是 rejected，会进入请求分母。决定节点可能携带上一轮 `call_id`，它的拒绝不能归到上一轮已完成工具；同一已开始调用的内层依赖拒绝和外层节点拒绝只计一次；读取重试不新增逻辑调用；顶层 CHECK 参数拒绝不算模型工具请求。先有拒绝观察但最终同一调用完成时，以持久完成结果为准。

请求口径只计算现有事件能确认的起点和拒绝边界，不重建未保存的模型响应。匿名或整个协议响应的 `tool_rejected` 计一个可观察拒绝边界，响应中原始工具数、名字不可得。旧日志没有拒绝事件时，不能把请求计数理解为完整模型输出工具总数，也不能根据 Run 的最终失败、场景名或私有内容推算；这仍是数据覆盖局限。

按文件来源、标签、实现 SHA、夹具/数据集身份、模型模式、模型路由安全字段指纹、任务种类和故障场景分 cohort。DB 未记录代码 SHA 时明确保留 null，不用当前 Git SHA 追认历史版本。`usage_origin=historical_recording` 的回放用量不能当作新发生的 provider 计费。输入来源 SHA256、筛选条件、每 Run 的用量和缺失字段都在 JSON 中，Markdown 只展示便于阅读的总览。

## 已运行证据

[本轮报表与复现](../eval/study-metrics-20261014/README.md)读取两批 P0-1 共 1,260 条已保存 Run，保留 63 个独立 cohort。未修改旧评测记录。原故障评测的候选延迟受并发 pytest 污染，不能用于空闲健康路径性能数字；使用 `serial-clean/healthy-*` 的同批串行对照，并区分持久化端到端与执行计时。

请求/执行两种工具口径的修正及真实持久化 DB/JSONL 对照见[补充验收](../eval/study-metrics-requests-20261014/README.md)：重新读取原 1,260 Run，63 个 cohort 的终态、模型用量与所有延迟保持一致；另在独立临时 PostgreSQL 中实际执行并保留 15 个合成 Run，完成两条 CLI 路径的逐项对照。旧报表未覆盖。

这些是确定性 provider 的机制数据，没有真实金额；公开快照缺少节点事件。本轮未读取生产用户数据，不重新认定模型质量。历史冻结质量脚本 `report-study.py`、`report-study-quality.py` 保持原有评分职责，本命令只复用其计数和分位数口径。
