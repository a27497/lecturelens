# LectureLens Study Agent 服务

Python/FastAPI + LangGraph + PostgreSQL/pgvector，负责课程学习任务的模型决策、上下文、工具编排和持久执行。学习闭环已完成有限范围验收，仍属实验能力，尚未发布；线上配置保持不变。质量结论与历史失败见[评测索引](../eval/README.md)。

## 职责与边界

- Python 保存 Session/Run、checkpoint、解释与练习、不可变作答版本、反馈和用户核对记录；PostgreSQL 同时保存派生 Evidence 索引。
- Java/MySQL 负责账号、课程与媒体事实、Evidence 权属/revision/删除检查和浏览器网关。Python 不读写 MySQL，不接收浏览器自报身份或用户 JWT。
- Java 后台推送 Evidence 清单与差量，Python 使用固定版本的本地 ONNX Embedding 建索引；学习请求只消费已就绪索引，不触发全文索引。
- 普通课程 QA 与媒体准备保持独立路径。自动评分、长期学习记忆和复习调度尚未交付。

详细约束见[项目契约](../docs/AGENT_PRODUCT_CONTRACT.md)和[Evidence 同步](../docs/L1_EVIDENCE_SYNC.md)。

## 运行模型

浏览器请求经 Java 鉴权和课程就绪检查后进入签名命令入口。Session 固定 owner/course/revision，同一 Session 最多一个活跃 Run；每个进程的一个后台 worker 从 PostgreSQL 队列依次领取任务。

执行循环是 **model → tool → observation → 下一次决策或停止**。模型通过标准 `tool_calls` 选择检索、相邻证据补读、有界计算、练习草稿或证据不足报告；草稿经过目标条件、字段引用、答案一致性与课程方法范围复核，最多提交两份候选。程序保存解释、练习与私有答案，或保存证据不足产物。受限 Python AST 工具没有导入、I/O、循环或任意方法执行能力；计算正确不等于课程支持。

作答保存为不可变版本。反馈是引用精确 `source_attempt_id` 的独立 Run，复用队列、预算、模型快照和恢复协议；`STUDY_FEEDBACK_ENABLED` 默认关闭，仅控制新反馈请求，已有结果和核对记录仍可读。见[工具与执行协议](../docs/L2_STUDY_AGENT.md)、[复核机制](../docs/L2_QUALITY_REVIEW.md)及[学习交互](../docs/L3_LEARNING_FLOW.md)。

## 授权、停止与恢复

- 内部 HMAC 绑定 audience、方法、实际路径、时间戳和原始请求体。每次工具或生成上下文前后重新检查 Java 当前权限与版本；Java 不可用时拒绝使用缓存证据。
- 默认 Run 上限为 6 次模型调用、8 次逻辑工具执行、64,000 保守 token 预留、90 秒 deadline。调用前持久扣减，deadline 从首次领取开始计时并包含停机时间；provider 实际 usage 单独记录。
- Session 使用专用 autocommit 连接上的 PostgreSQL advisory lock 保护 checkpoint 写入，不持有跨模型请求的业务事务。仍持锁的慢 worker 不被其他 worker 接管。
- 创建请求通过 `request_key` 幂等，同一 key 更换内容会冲突。工具结果按 `run_id + call_id` 唯一，每 Run 最多一个学习产物；副作用已提交而 checkpoint 未保存时，恢复回读工具结果，不重复保存。
- 模型响应尚未 checkpoint 时崩溃可能导致外部请求重发，不承诺 provider 恰好调用一次。恢复保留原预算、deadline 和模型配置。
- 取消立即将 Run 标为 `cancelled`。外部调用可能继续至返回或超时，但 worker token、运行状态和版本检查阻止晚到结果发布。预算耗尽、无效工具/引用、权限或版本变化、provider 失败和修订耗尽均停止执行。
- Java 删除立即关闭访问；Python 持久墓碑阻止晚到同步恢复课程，清理器取得 Session 锁后删除派生状态及 checkpoint，失败继续重试。源 revision 变化使旧 Session 失效。
- 公开事件只展示安全状态与计量，不含隐藏推理、源正文或参考答案；答案通过单独授权命令读取。

执行实现见 [runtime.py](src/lecturelens_agent/study/runtime.py)，持久约束见 [store.py](src/lecturelens_agent/study/store.py)。Agent 崩溃后恢复原 Run；Java 媒体任务租约过期后标为失败，由用户创建新任务重试。

## 本地运行

需要 Python 3.12、uv、PostgreSQL/pgvector 和已启动的 Java Evidence 服务。从仓库根目录准备配置，已有文件不要覆盖：

```bash
test -e .env.agent.local || cp .env.agent.example .env.agent.local
docker compose -f compose.agent.yml up -d
```

启动前完成以下配置：

1. 设置数据库连接和独立 `AGENT_SERVICE_SECRET`，Java/Python 使用同一服务密钥。
2. 两端显式设置 `STUDY_AGENT_ENABLED=true`；Java 加载 `DENSE_RETRIEVAL_ENABLED`、`AGENT_SERVICE_URL` 等配置，Python 设置 `AGENT_JAVA_BASE_URL`。
3. 使用支持标准工具调用的模型。可配置全局 `AGENT_LLM_*` 默认连接，或启动后在 `/settings/models` 配置个人决策/复核用途。新 Run 冻结连接版本和加密凭据，后续编辑不改变已有 Run；加密密钥与允许地址见[模型管理](../docs/MODEL_MANAGEMENT.md)。

```bash
cd agent-service
uv sync --locked
uv run --env-file ../.env.agent.local uvicorn lecturelens_agent.app:create_app --factory --host 127.0.0.1 --port 8090
```

`/healthz` 在 Embedding 模型与数据库初始化后可用。真实模式没有可用模型连接时拒绝新 Run 入队。`AGENT_LLM_MODE=mock` 仅用于显式的确定性流程演示，不是模型故障回退；真实/mock 模式不能交叉恢复已有 Run。完整双服务配置见[部署指南](../docs/DEPLOYMENT.md)和[检索服务说明](../docs/L1_DENSE_RETRIEVAL.md)。

## 验证与诊断

先创建独立 PostgreSQL/pgvector 测试数据库，不能与运行中的服务共用数据库或队列。在 `agent-service/` 执行，连接地址按本地配置替换：

```bash
uv run ruff check src tests
uv run ruff format --check src tests
AGENT_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:PORT/lecturelens_agent_test' uv run pytest -q
```

测试使用确定性模型/向量夹具和真实 PostgreSQL，覆盖权限、取消、幂等、进程恢复、预算及删除。未设置测试数据库时相关用例会 skip，不能报告为完整通过。CI 提供独立数据库；真实模型质量按[质量评测说明](../docs/L2_QUALITY_EVALUATION.md)单独验证，Java `DenseRetrievalLiveIT` 只验证检索契约。

- **Trace / Replay：** `python -m lecturelens_agent.study.trace_cli` 导出私有 Trace、启动授权的新 Run Replay 和比较结果；需要运维数据库访问及 Java 用户登录，读取前后重新授权。[用法与真实失败](../eval/agent-trace-phase-b/README.md)
- **Course MCP：** `AGENT_COURSE_TOOL_TRANSPORT=mcp` 启用官方 SDK stdio Client/Server；默认 `internal`。Server 转发原 Java 签名请求，不持有签名密钥，错误不回退直连。[协议与验证](../eval/course-mcp-phase-c/README.md)
- **离线检索评测：** `lecturelens_agent.benchmark` 比较 Dense、BM25、RRF 和 Cross-Encoder，依赖独立 eval 环境；生产 app 不导入该模块，默认 Dense 不变。[复现说明](../eval/retrieval-phase-a/REPRODUCE.md)
- **验收与历史：** [学习闭环完成报告](../eval/phase-completion/FINAL_AU.md)、[并发与隔离](../eval/multi-user-phase-e/README.md)和[评测索引](../eval/README.md)保留候选身份、失败记录与测量口径。
