# Phase C — 一个 Course MCP Integration

完成，未部署，未进入 Phase D。复用现有 Study Agent 工具和 Java Authority，没有新增权限层、业务状态表或其他 MCP 集成。

## 架构与工具

```text
Study Agent（原模型决策、工具预算、checkpoint、幂等与停止条件）
  → McpEvidenceAuthority（官方 MCP ClientSession；复用 stdio 会话）
  → Course MCP Server（官方 MCP Server；只转发已签名请求）
  → Java /internal/v1/study/evidence（原 HMAC 校验 + 权属/版本/删除/就绪检查）
  → 原 Evidence / MySQL 业务事实 / Dense 检索
```

Python MCP SDK **1.30.0** 锁在 `agent-service/uv.lock`，本次协商协议 **2025-11-25**。实际执行了 `initialize`、`tools/list` 和 `tools/call`，使用标准 `structuredContent` / `isError`，不是自定义接口改名。实现依据：[官方工具规范](https://modelcontextprotocol.io/specification/2025-11-25/server/tools)、[stdio 传输规范](https://modelcontextprotocol.io/specification/2025-11-25/basic/transports)。

| MCP 工具 | 原 Authority action | 语义 |
| --- | --- | --- |
| `get_course_revision` | CHECK | Java 验证请求的课程 revision；不自动接受新 revision |
| `search_course_evidence` | SEARCH | 原 Dense 检索、时间过滤和相邻上下文，最多 8 条 |
| `get_course_evidence` | READ | 按 IDs 读取当前 Evidence，最多 8 条，包括原空列表行为 |
| `get_evidence_context` | WINDOW | 原 anchor 及前后同源片段 |

这些能力已满足这次最小集成。没有为 metadata 复制 Java 业务查询；课程 ID/revision 仍来自原 scope。模型继续选择已有 Study 工具和参数，adapter 将 Evidence action 转成 MCP 调用，练习生成、计算和复核不被重写。

权限边界：owner/course/revision 来自 Java 认证后保存的 Run，模型不能覆盖。Agent 用原共享密钥对原 action/payload 签名；MCP 传递 proof，Server 不持有签名密钥，也不访问数据库或缓存 Evidence。Java 验证签名，并在检索前后重新检查 ownership、revision、deleted state、业务就绪。MCP 仅做格式校验及转发，client 的 scope/结果 schema 检查沿用并加强传输一致性保护，不替代 Java 授权。子进程只显式接收 `AGENT_JAVA_BASE_URL`，不继承数据库、模型或服务凭据。

默认 `AGENT_COURSE_TOOL_TRANSPORT=internal` 保持原路径；显式设为 `mcp` 才启用。未知配置直接启动失败。MCP 模式下任何错误都不回退 direct，不使用缓存冒充成功；同一失败调用不自动重试。之后的新调用可以重建坏会话，但仍完整经过 MCP 和 Java。

## 真实端到端证据

课程：真实 MIT 字符串片段 `task_1e293d54d1234ba4b32a101e944a0e37`，owner **4**，revision **2**。学习目标沿用已消费的历史字符串练习目标，没有消耗新保留数据。

Run **`4b863c46-885a-4208-afc2-2e5fba8426d8`**：经认证 Java START 创建 → Qwen3-Max 选择搜索 → MCP SEARCH → MCP WINDOW/READ 补充上下文 → 第一次候选因 `goal_mismatch` 被原检查拒绝 → 模型修复 → 原独立复核接受 → 保存概念题和输出题。

- `succeeded`，**59 个持久事件、10 个 checkpoint、7 个 Evidence 引用**。
- **5 次真实模型调用、4 次逻辑工具调用**；实际输入/输出 **11,960 / 738 tokens**。
- 模型累计 wall time **16,114 ms**；该 Run 的 SEARCH span **55.715 ms**。
- 原失败候选未删除；输出 `sample_0c2ee60e`、`yello` 核算正确，但生成输入可读性普通。单题机制与功能验证不证明质量提升或泛化。
- Observer 记录了整个评测 driver 的 **49 次 MCP tools/call**（含 parity、拒绝测试、Run 的 CHECK 和故障试验；不含网关服务自己的 observer 未开启调用）。

例如 Evidence ID `5d1454946169229c09508fa3a8c4e9055491b6d32d3d1fd818295851b5a28e84` 支持字符串不可变，`92c7eb72b4bfba0f0f3e5b89891c3b28b86286a4535a79499434fb05206780f5` 支持重新绑定。完整 Trace、握手、工具调用及原结果在 `.data/course-mcp-phase-c/live-v1/`，私有数据不进入 Git。

## Internal tool parity 与 Java 拒绝

同一真实 Java 后端、同一 owner/course/revision，直接调用与 MCP 调用的**完整 JSON 结果相等**，含文本、IDs、顺序、时间及 source_type；结果 SHA 保存在 `results.json`。

| 真实对照 | 结果 | direct / MCP wall time |
| --- | --- | ---: |
| CHECK | 相等 | 12.056 / 18.514 ms |
| SEARCH | 相等 | 50.703 / 61.015 ms |
| SEARCH + 时间窗口 | 相等 | 48.569 / 60.433 ms |
| READ 两条 | 相等 | 20.348 / 27.760 ms |
| READ 空列表 | 相等 | 15.444 / 24.342 ms |
| WINDOW | 相等 | 18.415 / 25.481 ms |

六组观察中 MCP 多约 6–12 ms，不能把这个小样本当成通用性能结论；首次握手/启动还有额外开销。模型计时沿用原 runtime 口径，包含返回后的 guard；工具 span 包含内部调用，各层耗时不能相加。

三项真实拒绝均返回与 direct 相同的 `StudyError(COURSE_UNAVAILABLE_OR_CHANGED, 409)`：

| 情形 | Java 权威事实 | 结果 |
| --- | --- | --- |
| 越权 | owner 5 请求 owner 4 的课程 | 两路拒绝 |
| 旧 revision | 对 revision 2 的课程提交 revision 1 | 两路拒绝 |
| 已删除课程 | `task_21e72179a0eb4d68acda7189a2b62719`，owner 5，revision 2，实际已删除 | 两路拒绝 |

已删除课程是原历史测试数据，本轮没有删除或改写真实课程来制造结果。测试库另自动验证检索期间 revision/deletion 变化时晚到结果被拒绝。Java 原权限、签名和删除代码没有修改。

## MCP failure case

故障 Run **`64452d57-1de4-4e09-a240-c46b420201e3`**：经真实 Java START，真实 Qwen3-Max 选择 SEARCH，测试专用 MCP Server **先完成真实 Java Authority 调用，再故意破坏其返回结构**。client 检出 schema 错误，原 Run 失败处理落盘 `MCP_MALFORMED_RESPONSE`，failure_type 为 infra。

- 输入/输出 **989 / 34 tokens**，1 次模型调用、1 次已预留的逻辑工具调用。
- `evidence_failed`、`node_failed`、`run_finished` 持久化；**没有已提交工具结果，没有最终 artifact**。
- 没有使用 direct fallback、旧 Evidence 或假的成功结果。
- 这是一项明确标记的受控故障注入，不是把自然质量失败改名。坏 Server 只在 eval 文件中，生产 server 无故障开关。

自动化还通过真实 stdio 测试超时、进程退出、输出 scope 不符、文本/结构化结果不符、工具目录/schema 错误和 `isError`；既覆盖启动时失败，也覆盖模型已经选择 SEARCH 后的失败。MCP 错误统一进入既有 StudyError / Run 终态和 Trace 的 infra 分类；Java 权属/版本拒绝保持 permission-state。

每次 MCP 请求及握手分别有 10 秒边界，SDK 负责取消和子进程关闭，退出时还有受限清理等待。Run 原 deadline、worker token 和 cancel 守卫照常决定是否提交结果；超时返回不获得副作用豁免。客户端允许并发 CHECK，避免慢 SEARCH 把取消入口的前置检查堵住。

## Regression 与复现

专项 **26 项**使用实际 MCP 子进程、HTTP 边界夹具及独立 PostgreSQL，覆盖 parity、HMAC 拒绝、ownership/revision/deletion、晚到 MCP I/O、deadline/cancel、checkpoint 恢复、工具提交幂等、删除级联、反馈与公开事件隐私。HTTP 夹具测试和上面的真实 Java 验证分别报告。全量 Python **605 项**、相关 Java **62 项**通过，无跳过；Ruff 检查/格式通过。唯一 warning 为已有 Starlette/AnyIO 弃用提示。明细见 [结果摘要](results.json)。

启用实际服务：

```bash
# 沿用原 Java URL、服务密钥、Agent DB 和模型配置；密钥只从环境/私有配置注入。
AGENT_COURSE_TOOL_TRANSPORT=mcp \
  uv run --directory agent-service --frozen uvicorn lecturelens_agent.app:create_app --factory \
  --host 127.0.0.1 --port 8094
```

Agent 自动启动 stdio 子进程；不需要独立开放 MCP HTTP 端口。不改原浏览器/Java 启动方式，MCP Server 可单独通过 `python -m lecturelens_agent.course_mcp.server` 被标准 stdio Client 启动。必填工具输入由 scope、原 action 参数和 `authorization.timestamp/signature` 组成；proof 使用原 Java HMAC contract，不能由模型生成或解释为新权限。

运行测试：

```bash
AGENT_TEST_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_agent_test \
  uv run --directory agent-service --frozen pytest -q tests/test_course_mcp.py
AGENT_TEST_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_agent_test \
  uv run --directory agent-service --frozen pytest -q
uv run --directory agent-service ruff check src tests ../eval/course-mcp-phase-c
uv run --directory agent-service ruff format --check src tests ../eval/course-mcp-phase-c
cd backend
./mvnw -q -Dtest=StudyControllerTest,StudyAuthorityTest,DenseEvidenceClientTest,DenseRetrievalRoutingTest,CourseQaEvidenceRetrieverTest test
```

真实验收 driver 需要原私有课程/模型配置、当前 `LECTURELENS_AUTH_TOKEN`、`AGENT_DATABASE_URL`、`AGENT_JAVA_BASE_URL`、`AGENT_SERVICE_SECRET`。在**自动 Study worker 已暂停的隔离实例**运行，仅由 driver 执行它通过 Java 新建的两个 Run；正常产品运行不用暂停 worker。MCP 模式在隔离 app 中也应开启：

```bash
# 在独立终端替代该隔离实例的普通 Agent 启动命令；Java 指向 8094。
AGENT_COURSE_TOOL_TRANSPORT=mcp \
  uv run --directory agent-service --frozen python ../eval/course-mcp-phase-c/serve.py --port 8094

# API 就绪后，在已配置相同隔离环境的另一终端执行。
uv run --directory agent-service --frozen python ../eval/course-mcp-phase-c/run.py \
  --base-url http://127.0.0.1:8084 \
  --source-run-id 189689f9-4e56-4fb9-87a5-2a673d1ee25b \
  --request-key your-new-trial-key \
  --deleted-course-id task_21e72179a0eb4d68acda7189a2b62719 \
  --deleted-owner-id 5 --deleted-revision 2 \
  --output ../.data/course-mcp-new-trial
```

输出目录不可覆盖旧试验。课程删除、revision 变化或登录失效时必须拒绝，不能用历史快照恢复权限。已有 Phase A/B 结果保留；本轮停止在 Phase C。
