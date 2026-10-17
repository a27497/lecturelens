# P0-1 健康路径延迟修复

在当前未提交 P0-1 上继续修复；分支保持 main，Java、冻结资产、旧故障记录/结果不改。新报告与原始证据只写本目录。真实模型质量、发布和部署均不属于本轮。

## 回退来源及修复

修改前先分别对原始基线与已验收 P0-1 做五次真实健康 Run profiling。`profile-*.jsonl` 保留 Store 方法、连接创建、SQL 分类的调用次数与耗时；`profile-*.pstats` 保留 cProfile 原始统计。方法累计耗时包含连接/SQL，不能再相加。每 Run 实际读取 25 次，新增 100 次 Store 连接创建请求：两次 guard、尝试预约、成功事件各一次/读取。

基线 Store 连接请求 72 次，P0-1 为 172 次，平均连接创建耗时约 610/1436ms；SQL 平均耗时约 220/537ms，其中三次 `operation_key` 查询/读取合计 75 次、约 58ms。总体平均墙钟差约 1267ms。连接创建是主要来源，重复状态/事件 SQL 是次要来源；不能把这部分归因于 MCP 或退避。

修复将 `StudyStore.connect()` 的普通事务连接限定在当前 Run 内复用，跨 LangGraph 节点线程传播时串行租用。每个 Store 操作仍各自 BEGIN/COMMIT/ROLLBACK，模型和工具 I/O 期间无事务和行锁；Session advisory lock 继续用独立 autocommit 连接。新 Run 新建租约，结束关闭；已关闭的旧节点上下文不能重新打开租约，坏连接在后续操作重建。

持久尝试、预算扣减、三个事件查询和全部取消/deadline/版本/停机围栏仍执行，没有使用成功证据缓存、批量延迟提交或内存预算。写入不进入重试策略，公开失败分类仍保留。修复后 profiling 的 Store 实际物理连接为每 Run 两次（事务租约、Session lock），平均墙钟约 1306ms；checkpoint saver 的独立连接不包含在这两次里。

原始 profiling 使用 `profile_run-v1.py` 的连接代理；修复后 `profile_run.py` 适配事务租约，并分别测量借用请求和实际 `psycopg.connect`。profiling 结果只用于归因，不混入正式未插桩的 P50/P95。

## 延迟口径更正

旧目录 `tool-resilience-20261014` 的 +1.91/+3.44s 是四 worker 环境的候选减基线 P50/P95，不能解释为干净的代码回退：候选评测 06:59–07:03 UTC 与 07:00:55 UTC 起的四组全量 pytest 重叠，而基线在空闲阶段。这里明确更正此解释，旧文件保持原样。

验收方提供的空闲串行控制（每版 20 次）：基线 1405/2022ms，修复前 2636/3215ms，约 +1.2s。这些数字为用户提供，原始记录未在本目录，不能计作本轮自己的实跑数据。

本轮在同一主机、同一独立 `lecturelens_latency_fault_test` 库串行执行基线、修复前归档、修复后。每次启动同一 `run.py --scenarios healthy --samples 20`，固定 Client 和 MCP Server 对应的 PYTHONPATH，使用同一锁定 Python 环境、确定性 provider、合成课程、2 秒 MCP timeout。

| 版本 | 样本量 | P50 ms | P95 ms |
|---|---:|---:|---:|
| 原始基线 56bc07a | 20 | 1514.622 | 1591.813 |
| 修改前 P0-1 归档 | 20 | 2668.664 | 3257.275 |
| 修复后 | 20 | 871.212 | 941.159 |

每组各 Run 均为 4 次模型、3 次工具预算、25 次 HTTP/MCP 调用，读重试为零。正式记录在 `serial-clean/healthy-*.jsonl`，时窗与进程/CPU采样在 `serial-clean/healthy-audit.json`。CPU 采样包含本次测量自身与常驻服务，不能当作测量开始前的空闲 CPU。测量窗口没有并发 pytest 或其他评测；测试在所有正式测量结束后另跑。

首次健康批次检测到 07:50:01–03 UTC 外部 pytest，审计保留在顶层 `healthy-audit.json`。该批次标记污染，不进入正式结果；没有停止外部进程或隐藏这段重叠。重新跑的完整干净批次才进入本报告。

## 故障与测试证据

完整 14 个故障场景及额外健康控制在 `serial-clean/faults-*.jsonl`，每版本每场景 20 次，逐版串行，不与测试重叠。最终恢复/失败/拒绝分布、延迟与调用统计由 `summarize.py` 从这些记录生成。最终数字见 [RESULTS.md](RESULTS.md)，检查明细见 [verification.json](verification.json)。

除原 P0-1 覆盖外，新增真实 PostgreSQL 测试验证：单独提交/回滚、工具 I/O 期间无事务和行锁、连接复用后仍观察外部取消、传播到节点线程的租约不混用事务、旧节点上下文不能重开已关闭的租约。全量检查采用与评测分离的 PostgreSQL/pgvector 测试库；库名遵守现有 pilot 的限制，不放宽保护。

## 复跑

从仓库根目录创建两个源码快照：原始 `git archive 56bc07a agent-service/src`，以及修改前 P0-1 的 `cp -a agent-service/src`。后者必须在修复前保存，不能用 HEAD 替代当前未提交的 P0-1。快照身份及当前候选身份由原始记录、源码清单记录。

```bash
export AGENT_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:PORT/lecturelens_latency_fault_test'
agent-service/.venv/bin/python eval/tool-resilience-latency-20261014/measure.py \
  --phase healthy --output-dir /tmp/new-healthy-measurement \
  --baseline-source /ABS/BASELINE/src --before-source /ABS/P0-1-BEFORE/src \
  --candidate-source "$PWD/agent-service/src"
agent-service/.venv/bin/python eval/tool-resilience-latency-20261014/measure.py \
  --phase faults --output-dir /tmp/new-fault-measurement \
  --baseline-source /ABS/BASELINE/src --before-source /ABS/P0-1-BEFORE/src \
  --candidate-source "$PWD/agent-service/src"
```

审计如发现其他 pytest/评测，保留批次并拒绝将其作为干净结果；使用新输出目录重跑。不得同时运行全量测试。所有正式数据完成后再跑 `AGENT_TEST_DATABASE_URL=.../lecturelens_agent_test uv run pytest -q` 和 ruff。

## 未覆盖

真实模型教学质量、真实 Java 进程故障、真实网络多地域/高 RTT：未运行。14 场景继续以 SEARCH/CHECK 为矩阵；READ/WINDOW 只在机制测试中覆盖，20 次故障矩阵未运行。HTTP 429、慢流、DNS/TLS、数据库/磁盘停机、重试风暴/跨 Run 熔断：未运行。连接断开后的重建有实现，本轮不把它当作完整数据库故障恢复验收。
