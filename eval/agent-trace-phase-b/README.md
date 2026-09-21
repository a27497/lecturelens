# Phase B — Agent Trace / Replay

完成，未进入 Phase C，未部署。只增加运行诊断与受权 Replay；没有改检索默认、模型提示、工具选择策略或 Java authority。Phase A 文件和评测保留。

## 审计与实现

优先复用已有数据，没有新建执行状态表，也没有重置历史 Run。

| 原数据 | Trace 用途 |
| --- | --- |
| `study_session` / `study_run` | Question、owner/course/revision、状态、deadline、持久预算、冻结模型身份 |
| `study_event` | 调用开始/结束/失败、模型真实 usage、重试、恢复、取消、终态 |
| `study_tool_result` | 已执行工具、参数、结果和 Evidence IDs；保持原 call_id 幂等 |
| LangGraph PostgresSaver | 按 Run 过滤原 checkpoint、pending、history、错误写入和父 checkpoint |
| `study_artifact` / `study_feedback` | 成功后的完整最终练习/答案或反馈 |

新增 `study_event.trace_detail JSONB` 保存私有模型输入、schema、结构化决策和节点待执行参数；原 `payload` 的唯一索引保留。完整上下文不能放入原索引列，否则会触发 PostgreSQL 索引行大小限制。迁移为 `ADD COLUMN IF NOT EXISTS`，复用原迁移锁，无表重写或历史回填。

增加节点及 SEARCH/READ/WINDOW 的实际计时事件，用原 worker token / deadline 守卫写入。取消或 deadline 后的返回值不补记为成功。CHECK 仍直接调用原 authority。节点绑定真实输入 `checkpoint_id`；新 Run 的 input checkpoint 按 `__start__.run_id` 归属，避免同 Session 上一个 Run 的残留 channel 值混入。

公开 `EVENTS` 隐藏诊断事件与私有列，保留原持久 sequence 游标（允许间隙）。Trace 是**运维 CLI**：同时需要 PostgreSQL 运维访问和当前 Java 登录，读取前后分别调用既有认证 READ 验证 owner/course/revision。没有新增浏览器或内部免鉴权 API。模型配置只投影公开身份，不输出 credential、base URL 或 worker token。完整 Trace 含题目、答案及课程上下文，写入新的 0600 私有文件，不纳入 Git。

## Trace 示例

真实新 Run：`166d4719-991f-4c65-bbcc-e3152fe6bd60`，revision **2**，Qwen3-Max。

```text
Question: 解释字符串不可变与变量重新绑定，并生成概念题和新字符串输出题
  → checkpoint 1f1b5961-c712-6659-bfff-671c5a55e3c9
  → decide / model attempt 1：选择 search_course_evidence
  → SEARCH：6 个真实 Evidence IDs；63.144 ms
  → 两次 read_evidence_window：补齐变量绑定和字符串操作的相邻讲解
  → create_python_practice：第一次候选因 goal_mismatch 被拒绝
  → 下一次模型决策修复输入，保留原失败工具结果
  → 独立模型复核接受，保存 1 道概念题和 1 道输出题
  → checkpoint 1f1b5962-8f0f-6abd-800a-e94d40aefe20
  → succeeded / final answer / 7 个引用 Evidence IDs
```

例如 `5d1454946169229c09508fa3a8c4e9055491b6d32d3d1fd818295851b5a28e84` 支持不可原地修改字符串，`92c7eb72b4bfba0f0f3e5b89891c3b28b86286a4535a79499434fb05206780f5` 支持重新绑定。完整链路共 **71 个事件、12 个 checkpoint、5 个已提交工具结果**，位于本地 `.data/agent-trace-phase-b/live.trace.json`。原始模型输入、所有候选和最终答案均可检查。

## 真实失败 Replay 与归因

历史 Run `189689f9-4e56-4fb9-87a5-2a673d1ee25b`（2026-09-20，历史验收候选 **AS**）提出同一字符串学习目标。Qwen3-Max 两次返回：

```json
{"name":"search_course_evidence","arguments":{"query":"字符串不可变性与变量重新绑定的区别","practice_kind":"python_strings","linear_request":""}}
```

可选对象 `linear_request` 被错误填为空字符串，两次 Pydantic 校验均为 `model_type`，消耗一次协议重试后 `MODEL_TOOL_CONTRACT`。**归因是 tool selection 中的参数/协议契约失败；尚未执行检索，不应归为 retrieval。** 历史 schema 为非线性任务暴露了这个不相关对象字段。

1. **固定响应回放**：用历史 AS 源码及原始两份 HTTP 响应，创建新的受权 Run `3cb19140-a754-4f2a-8d5a-fc214b896f08`。两次请求的 messages 和 schemas 均与原记录完全相同，复现同一失败、同一重试、同一最后 checkpoint 状态。只替换模型 HTTP 响应；权限、版本、工具和业务状态仍来自当前 Java，未注入旧 Evidence 或工具结果。原 Run 的事件和 checkpoint 经规范化 JSON 比较未变。
2. **修改后真实模型对照**：当前 AU 行为已按学科缩小 schema，非线性任务不再暴露 `linear_request`。通过 Replay CLI 用同一目标、同一 owner/course/revision、当前冻结模型配置启动新 Session 和新 Run，真实调用 Qwen3-Max 后成功。这个 AS → 当前实现的行为修复已存在；Phase B 使其可重放、可观察，没有再改提示或放宽参数校验。

记录响应回放不产生新的模型 token 消费。它的 usage 是原响应携带的历史值，其 33/36 ms 是本地回放耗时，**不能当作真实模型速度**。真实模型对照不是逐字确定性回放；单题改善不能证明整体质量提升。

本次对照仍出现一个被拒绝候选，全部保留。最终输出的概念说明与所引片段一致，代码输出 `sample_9c9558f4`、`yello` 核算正确；新输入可读性普通，模型已经用满 6 次调用预算。未据此声称未见课程泛化或自动评分可靠。

首次启动 Replay 时还真实遇到 `STUDY_INDEX_NOT_READY`：Java 拒绝 CREATE_SESSION，未创建 Run。原同步流程恢复 READY 后才继续，拒绝记录保留在 `.data/agent-trace-phase-b/initial-gate-rejection.json`。

## 指标

| 指标 | 历史真实失败 AS | 固定响应 Replay | 当前实现真实模型 Replay |
| --- | ---: | ---: | ---: |
| 状态 | failed | failed（复现） | succeeded |
| 模型调用 / 工具调用 | 2 / 0 | 2 / 0 | 6 / 5 |
| 输入 / 输出 tokens | 2,086 / 90 | 原记录 2,086 / 90；新增消费 0 | 14,327 / 771 |
| 模型调用累计 wall time | 3,619 ms | 69 ms（本地回放） | 19,290 ms |
| 实际 SEARCH 次数 / 延迟 | 未执行 / 无测量 | 未执行 / 无测量 | 1 / 63.144 ms |
| 工具节点累计 wall time | 无历史测量 | 无测量 | 7,328.309 ms |
| 协议重试 / 候选拒绝 | 1 / 0 | 1 / 0 | 0 / 1 |

token 来自 provider usage，不用 `reserved_tokens` 冒充（当前预留为 60,814）。模型时长沿用原 runtime 口径，包含返回后的守卫检查；工具节点包含守卫、嵌套 LLM 和 Evidence I/O，不能与模型/检索时间相加。SEARCH 为完整 Java Evidence SEARCH 往返，不是纯向量计算时间。未知或被取消的调用用 `null`、`missing_calls`、`unfinished_calls` 显式表示，不估算补齐。

当前 Run 私有 trace 列实际存储约 **50,622 bytes**（`pg_column_size`），事件 payload 合计 14,295 bytes；模型输入重复存储增加空间成本。没有测量相同工作负载下开启/关闭 Trace 的净延迟，因此不声称零开销。优先保留这套最小 CLI 和 journal 方案，没有引入 AgentOps 平台。

## Failure taxonomy

| 类型 | 含义与证据 |
| --- | --- |
| retrieval | 检索/索引失败，或经独立相关性标注确认漏召回；看 SEARCH 参数、返回 IDs |
| tool selection | 未搜索便提交、选错工具、无效参数、工具协议失败；本次历史 Case 属于此类 |
| context | 已有 Evidence 未纳入上下文、窗口不足或引用对应错误；看模型输入与 checkpoint.selected |
| generation | 答案/练习/反馈不受支持、违反目标或耗尽修复；本次第一次候选 `goal_mismatch` 属于此类 |
| permission-state | owner/revision/deletion、取消或课程业务状态的正常拒绝；不绕过也不当成检索差 |
| infra | 模型/网络/数据库、timeout/deadline 或持久预算停止；预算耗尽的上游原因需进一步归因 |

`failure_type` 是终态错误码的保守规则分类，`failure_attribution` 显式要求语义根因人工复核；未知通用执行错误暂归 infra。成功 Run 的终态分类为 null，但逐事件/逐工具失败仍存在。`compare.quality_pass` 不自动赋 true。

## 复现

使用现有隔离服务和真实测试课程。设置 `AGENT_DATABASE_URL` 为相应 Agent PostgreSQL、`LECTURELENS_AUTH_TOKEN` 为该课程所有者当前 Java 登录 token；不要把凭据写入命令或 Git。从仓库根目录执行：

```bash
uv run --directory agent-service python -m lecturelens_agent.study.trace_cli trace \
  --base-url http://127.0.0.1:8084 \
  --run-id 189689f9-4e56-4fb9-87a5-2a673d1ee25b \
  --output ../.data/history-new.trace.json

uv run --directory agent-service python -m lecturelens_agent.study.trace_cli replay \
  --base-url http://127.0.0.1:8084 \
  --run-id 189689f9-4e56-4fb9-87a5-2a673d1ee25b \
  --request-key your-unique-trial-key --wait-seconds 120 \
  --output ../.data/replay-new.json

uv run --directory agent-service python -m lecturelens_agent.study.trace_cli compare \
  --base-url http://127.0.0.1:8084 \
  --run-id 189689f9-4e56-4fb9-87a5-2a673d1ee25b \
  --after-run-id 166d4719-991f-4c65-bbcc-e3152fe6bd60 \
  --output ../.data/comparison-new.json
```

重复同一 source/key 返回同一新 Run；不同 key 是另一次试验。Replay 仅支持 terminal practice，使用新 Session，当前模型配置由原 START 冻结，不恢复旧凭据、不复用旧 checkpoint，也不冒充当前权限。含会话历史的目标必须检查上下文差异；本案例原始 Session 无先前成功 Run，固定回放验证了上下文完全一致。

固定历史响应回放需要保留的私有录制与源码归档，并在**关闭自动 worker 的隔离评测实例**中执行；脚本只执行它创建的新 Run。还需提供该实例的 `AGENT_JAVA_BASE_URL`、`AGENT_SERVICE_SECRET`：

```bash
uv run --directory agent-service python ../eval/agent-trace-phase-b/reproduce.py \
  --base-url http://127.0.0.1:8084 \
  --run-id 189689f9-4e56-4fb9-87a5-2a673d1ee25b --request-key recorded-new-trial \
  --archive ../.data/phase-completion-20260920/AS-source.tar.gz \
  --source-sha256 1c8fe367ff3e1d205c8f4c9af4ade4b80fbb410332e36add1c3e07dc2bbde352 \
  --calls-log ../.data/phase-completion-20260920/calls.jsonl \
  --calls-dir ../.data/phase-completion-20260920/calls \
  --output ../.data/recorded-new-trial
```

历史课程被删除、revision 改变或登录失效时，Replay 必须拒绝；离线归档不代表继续访问授权。新输出目录/文件不能覆盖旧试验。实际执行源码身份、响应 SHA、逐调用计时与边界结果见 [结果摘要](results.json)；完整私有记录位于 `.data/agent-trace-phase-b/`。

## 验证

运行 Trace 专项测试及独立 PostgreSQL 全量 Python regression，另运行原 Java 网关/authority/Dense/QA 回归。最终计数见 `results.json`。核心覆盖：跨 owner/revision、读取途中失效、同 Session checkpoint 隔离、Replay 幂等与源 Run 不变、进程恢复、取消、deadline、删除级联、stale-result isolation、反馈及公开事件隐私。

```bash
AGENT_TEST_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_agent_test \
  uv run --directory agent-service pytest -q
uv run --directory agent-service ruff check src tests ../eval/agent-trace-phase-b/reproduce.py
uv run --directory agent-service ruff format --check src tests ../eval/agent-trace-phase-b/reproduce.py
cd backend
./mvnw -q -Dtest=StudyControllerTest,StudyAuthorityTest,DenseEvidenceClientTest,DenseRetrievalRoutingTest,CourseQaEvidenceRetrieverTest test
```

Phase B 完成后停止；不进入 Phase C，不改变线上默认配置。
