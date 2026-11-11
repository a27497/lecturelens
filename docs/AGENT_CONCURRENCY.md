# Agent 服务并发通道（Step 6）

此前 Agent 服务是“单通道”：检索与建索引共用一把非阻塞锁（`Retriever.lock`），任何文档 Embedding 期间所有问答检索都返回 `503 Retrieval busy`（Java 随即回退到词法检索）；Study Run 由唯一的 `study-agent-worker` 线程按顺序执行，一个 Run 的模型 I/O 会让其他用户的 Run 全部排队。

## 行为

| 路径 | 之前 | 现在 | 配置（Python 进程环境） |
| --- | --- | --- | --- |
| 问答检索 `/internal/v1/retrieve` | 与建索引共用 1 个槽位 | 独立的查询槽位，满了立即 `503`，不排队 | `AGENT_RETRIEVAL_CONCURRENCY`，默认 `4`，范围 1–16 |
| 建索引 `/internal/v1/evidence/sync` `APPLY` | 与检索共用 1 个槽位 | 独立的单通道锁；`PLAN`/`DELETE` 仍不需要锁 | 固定 1 |
| Study Run | 1 个线程顺序执行 | 1 个调度线程 + 固定 N 个工作线程；不同 Session 并行，同一 Session 串行且按创建顺序 | `AGENT_RUN_CONCURRENCY`，默认 `2`，范围 1–8；设为 `1` 恢复单通道 |
| Run 事件流 | Java 每秒轮询 `EVENTS` 再转 SSE | 不变；另提供可选服务端 SSE `/internal/v1/study/events/stream` | `AGENT_EVENT_STREAM_ENABLED`，默认 `false` |

非法取值在启动时失败，不会静默回退。

### 一致性与隔离不变

- 同一课程的检索与重建由 PostgreSQL 隔离：检索按 `snapshot_id` 读取，读完再确认快照仍为 `READY`；期间被重建或删除时返回 `409 Evidence index changed`（`Retry-After: 1`，此前为笼统的 `503`）。并发 `APPLY` 仍由 `evidence_index` 行锁和 `sequence` 防护。
- 本地 Embedding（fastembed/ONNX Runtime）在查询与文档并发调用下与串行结果逐项一致（服务器实测 256 段文档 + 40 条查询）。
- 每个 Run 仍有自己的 worker token、截止时间、模型/工具预算、调用日志和 LangGraph 检查点；每次证据读取仍携带该 Run 的 owner/course/revision 并经 Java 授权。取消只隔离被取消的 Run。
- 调度器每轮对每个 Session 只取最早的候选 Run，Session 在途时跳过；PostgreSQL Session 咨询锁仍是跨进程防护。`START` 本身也只允许一个活跃 Run（`SESSION_BUSY`）。
- 关闭时先停调度，再等待各工作线程（共 35 秒）；被中断的 Run 保持 `running` 并在重启后从检查点恢复，与此前一致。

### 资源边界

- 每个执行中的 Run 约占 3 个 PostgreSQL 连接（Run 连接租约、Session 咨询锁、LangGraph 检查点）。默认 2 个通道约 6 个，上限 8 个通道约 24 个，均远低于 Postgres 默认 `max_connections=100`。检索每次请求临时占 1 个连接。
- 线程数固定：调度 1 + 工作 N；检索并发由 Uvicorn 线程池承载，槽位满时立即拒绝。
- 模型供应商限流：并行 Run 会同时向各自冻结的模型连接发请求。若 Run 绑定的是单槽位本地模型（例如 `llama-server -np 1`），请求会在模型端排队并消耗 Run 的截止时间，此时应保持 `AGENT_RUN_CONCURRENCY=1` 或提高模型端并行度。

## 回答流式输出的取舍

Study 回答是经过校验才发布的结构化产物：工具调用参数必须通过 Schema、引用核对（证据 ID 与原文片段）、独立复核，题目答案只在 `ANSWERS` 中返回。把模型 token 直接流给浏览器会绕过这些校验，并可能在复核前泄露 `answer_points` 等答案字段，所以本步骤不做 token 级流式。

现有端到端流式保持不变：Java `GET /api/tasks/{taskId}/study/runs/{runId}/events` 以 SSE 推送公开的步骤事件（`run_started`、`tool_finished`、`artifact_created`、`run_finished` 等），产物在 `artifact_created` 后读取。

新增的服务端能力 `POST /internal/v1/study/events/stream`（默认关闭）：

- 与 Study 命令相同的 HMAC 签名；请求体为 `operation=EVENTS` 且带 `session_id`、`run_id` 的 `StudyCommand`。
- 首字节前先经 Java 校验课程权限并检查 Session 归属；之后每次读取前都重新校验，失败时发送 `stream_error` 并结束。
- 事件内容与 `EVENTS` 完全相同（不含 `_trace`、证据原文、未校验的模型输出或答案）。到达终态且事件读尽后发送 `stream_end`；到达时长上限（25 秒）或客户端断开时发送 `stream_pause`，均带 `cursor`，客户端用 `after=cursor` 续传。

Java 网关仍使用轮询 `EVENTS` 的现有契约；改为转发此流需要单独修改 `StudyController.events` 并保留其每轮重新鉴权，届时再开启开关。

## 源码身份

修改了 `app.py`、`retrieval.py`、`study/runtime.py`，按既有机制登记新的开发身份 `step6-agent-lanes-2eed7cb6c34e7c84`（`study/step6_agent_manifest.json`，63 个模块）。`phase0_agent_manifest.json` 及更早清单保持原字节，Phase 0 身份改由 `verify_phase0_agent` 校验，测试夹具 `tests/fixtures/step6-prior-source.tar.gz` 还原这三个文件的旧字节，再沿原有夹具链重建 P10/P9/P7/FROZEN。新身份不继承任何历史质量结论，也不允许真实 Provider 调用。

## 验证

`agent-service/tests/test_agent_lanes.py` 使用事件和屏障构造并发：如果路径仍是串行，测试会死锁并超时失败，而不是靠 sleep 判断。覆盖：其他课程建索引期间检索照常返回；查询槽位占满时建索引不受影响、查询仍有界拒绝；N 个查询同时处于 Embedding 中、第 N+1 个被拒；两个 Session 的 Run 同时处于模型 I/O 中，且预算计数、引用、答案隐藏、证据范围与串行一致；同一 Session 的 Run 按顺序串行；通道数上限；取消只影响一个 Run；事件流的增量、终止、续传、关闭默认值和鉴权。
