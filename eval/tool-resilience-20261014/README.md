# Study Agent 工具容错故障注入

新的未发布候选；不修改 AU、旧冻结源码或质量结果。学习目标为“解释停止条件并出两道题”。确定性 provider 选择检索、相邻补读和练习工具，真实 HTTP/MCP 观察进入 LangGraph/PostgreSQL Run；可恢复时保存合成课程练习，无法恢复时保留明确失败及公开 Trace。该评测验证执行机制，不证明模型智能或教学质量。

数字见 [RESULTS.md](RESULTS.md)，完整指标见 [summary.json](summary.json)，检查依据见 [verification.json](verification.json)。正式原始数据是 `baseline.jsonl` / `candidate.jsonl`，各自 worker 文件和 manifest 保留来源及文件哈希。

## 策略

- CHECK/SEARCH/READ/WINDOW 对 timeout、MCP server unavailable、Java authority timeout/unavailable 最多重试两次，退避 50/100ms。重试和逻辑工具共享现有八次预算，尝试预约与预算扣减在 PostgreSQL 同一事务提交。
- 未完成读取跨 checkpoint 恢复保留尝试上限；成功读取可以重新授权，但新调用仍先持久预约。每次实际请求保留 Java scope/签名，不用缓存代替授权。取消、worker token、deadline、停机围栏约束调用前后和退避后。
- scope、时间参数及响应时间限定 Java 有符号 64 位范围。工具参数在执行前严格校验，包括之后会被目标约束移除的时间过滤器。参数错误、错误工具选择、畸形响应和权属/版本错误直接拒绝；持续依赖故障明确失败，不将不可用当作课程证据不足。写入/发布不自动重试。
- 公开 `tool_retry_started`、`tool_retry_backoff`、`tool_read_failed`、`tool_rejected`、`dependency_stopped` 及模型重试/终态事件包含安全错误码和 `failure_category`。参数原文、证据、答案不公开。读预约/成功标记仅供运维 Trace 使用。
- Trace 分开报告逻辑工具次数、读重试与实际工具预算。重试键基于 Run 内 node/turn/call_id/读取序号/参数哈希。已有模型格式纠正仍限制一次并消耗持久模型预算。

## 方法与口径

基线是提交 `56bc07ac3f5f57bb71592047baf12befc90e0448` 的归档 Python 包。基线客户端和 MCP Server 均使用这份归档；候选客户端和 Server 均使用最终工作区包。夹具给 Server 显式设置对应 `PYTHONPATH`，避免可编辑安装混入另一版本。每条记录包含包源码与夹具哈希，两版使用相同夹具及锁定依赖。

14 个故障场景，每版每场景 20 次；另有每版 20 次健康控制，共 600 条正式 Run。每版四个独立本地 fixture worker，各跑五轮；数据库 schema/checkpoint 在启动 worker 前一次性准备，避免并发 DDL。基线和候选两版依次运行，全量机制测试按文件分四组，在四个互相隔离的 PostgreSQL/pgvector 容器中完整覆盖；它们与评测库分离。

HTTP fixture 经真实官方 MCP Server 转发合成 Evidence：HTTP 503 注入 Java authority 不可用；2.1 秒延迟超过实际 MCP 客户端 2 秒超时；畸形 Evidence 数组验证响应拒绝。模型夹具注入负数、反向窗口、过长查询、整数溢出、未知工具、非对象工具调用和一次/持续协议错误。没有真实模型调用、下载媒体或私有课程数据。

- 恢复率为安全成功 Run / 样本数；非法工具或越界场景的成功单列 `unsafe_success`，不算恢复。保留原始执行状态，不把失败或错误输出重标为成功。
- 拒答仅指保存 `insufficient_evidence` 产物；依赖故障按策略失败，不保存拒答产物。汇总列出失败码及终态分布。
- 额外读重试以实际预约事件计数，格式重试单列。正式矩阵没有调用中取消，因此预约重试与实际发出重试相符；机制测试中的取消可能在扣减后、发出前阻断。候选减基线 MCP 调用差还包含恢复后继续执行的正常调用，不全是重试成本。
- 延迟为 `runtime.execute` 实测墙钟，包括数据库、MCP 建连、模型桩、检查与退避。健康控制按 worker/trial 配对，可由同轮多个场景共用。P50/P95 使用 nearest rank；报告故障减同版健康控制、候选减基线和调整健康控制后的差值。
- 负延迟增量代表较早失败，不代表同一任务更快完成。不同终态的墙钟差不是成功任务的纯重试开销；共享主机上四 worker 的观测不是生产 SLA 或无负载性能基准。

## 复跑

从仓库根目录，使用单独且名字以 `fault_test` 结尾的评测库。机制测试使用独立 PostgreSQL/pgvector 中的 `lecturelens_agent_test`；已有 pilot 脚本限定此库名，不能与服务库共用。

```bash
cd agent-service
uv sync --locked
cd ..
baseline_dir=$(mktemp -d /tmp/lecturelens-read-baseline.XXXXXX)
git archive 56bc07ac3f5f57bb71592047baf12befc90e0448 agent-service/src | tar -x -C "$baseline_dir"
export AGENT_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:PORT/lecturelens_resilience_eval_fault_test'
PYTHONPATH="$baseline_dir/agent-service/src" agent-service/.venv/bin/python eval/tool-resilience-20261014/run-batch.py --label baseline --output /tmp/lecturelens-baseline.jsonl
PYTHONPATH="$PWD/agent-service/src" agent-service/.venv/bin/python eval/tool-resilience-20261014/run-batch.py --label candidate --output /tmp/lecturelens-candidate.jsonl
```

将新输出分别命名 baseline.jsonl / candidate.jsonl 放入一个新目录，复制 `summarize.py` 到该目录运行汇总。不得覆盖已有 trial 文件。`run.py` 默认可串行独立运行 20 轮；`run-batch.py` 的 `--workers 1` 也可串行，但与此次四 worker 延迟口径不同。

## 保留的诊断批次

这些文件不进入正式汇总；保留原状态和失败，不改旧评分：

- `pilot-baseline-shared-db.jsonl` / `pilot-run.py`：共库验证的 DDL 锁竞争批次；HTTP selector 计数也会命中健康/模型场景，不能当实际注入次数。
- `baseline-v1.jsonl` / `run-v1.py`：20 次 protocol_once 失败来自 MockProvider 将修复 prose 当 JSON。修正桩后另跑 `baseline-protocol-repair.jsonl`，没有重标原失败。
- `baseline-integer-overflow-mixed-server.jsonl`：归档 Client 意外加载工作区 Server，schema 不匹配，健康和溢出场景均失败；因此正式评测改为显式固定 Client/Server 同版源码。
- `baseline-composed-v2.jsonl`、旧 `baseline-selection*.json`、`run-v2.py` / `run-v3.py` 和 `candidate-v*-partial.jsonl`：上述修正过程的组合/中断诊断，正式两版完整矩阵已重新运行。
- 首次全量检查被既有 pilot 的数据库名称保护拒绝；没有放宽保护或计为通过。最终检查用独立容器内的规范库名。通用 `scripts/eval/replay-study-quality.py` 的 FixedEvidence 夹具只返回课程 scope 与 Evidence，避免后来追加的 Session 上下文混入 authority envelope；冻结资产不改。另一个旧 WINDOW 测试夹具缺少课程 scope，已补齐有效 envelope；缺 scope 的畸形响应仍由新测试验证拒绝。

## 覆盖边界

- 真实模型任务质量、真实 Java 进程故障、线上运行：**未运行**。
- SEARCH/CHECK 的每类 20 次故障矩阵已运行；READ/WINDOW 的故障仅在 PostgreSQL 机制测试覆盖，20 次矩阵：**未运行**。
- MCP 子进程崩溃、catalog 不匹配、畸形 MCP 内容、scope 变化、调用中取消/删除/超期及恢复由机制测试覆盖；各自 20 次矩阵：**未运行**。
- HTTP 429、慢流/部分传输、坏 JSON-RPC、DNS/TLS、数据库/磁盘故障、并发重试风暴和跨 Run 熔断：**未运行**。该候选采用每 Run 有界重试和终止，没有跨 Run 熔断或其他检索降级。
