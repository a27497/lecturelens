# C0–C3 清理执行记录

日期：2026-09-11。起点：`main@f71641e`。工作分支：`codex/c0-c3-cleanup`。

这是本轮实际实现与验收记录。原始问题证据保留在 [AGENT_MIGRATION_AUDIT.md](AGENT_MIGRATION_AUDIT.md)；后续 Agent 建设见 [STUDY_AGENT_BLUEPRINT.md](STUDY_AGENT_BLUEPRINT.md)。本轮完成工程基线清理，尚未实现向量 RAG、Agent Loop 或 Memory。

## 已实现

| 工作包 | 交付内容 |
| --- | --- |
| C0 基线 | CI 增加前端单测、依赖审计、真实基础设施 Mock E2E；Vite/插件归入开发依赖，更新 nanoid、Vitest 及 brace-expansion 相关锁文件；纠正迁移与架构说明；补齐 Demo Mock QA |
| C1 事务与运行配置 | QA、章节、学习资料的模型调用不持有业务事务；短事务发布校验 owner、删除/取消状态、source revision、最新 generation；QA 失败独立落库；禁用 Pipeline 不再返回假成功；消费端缺 Pipeline/Flyway/ASR/LLM 或多 Provider 冲突明确失败 |
| C2 任务可靠性 | 创建/取消与 outbox 同事务；异步投递、稳定事件 ID、重试和过期 claim；数据库执行租约去重、心跳、超时恢复、过期 worker 禁止成功发布；删除操作持久化清理意图、MinIO 失败后重试；SSE 不使用与数据库状态冲突的旧缓存 |
| C3 证据契约 | 不可变 CourseEvidence 快照，来源/版本/hash/时间/原文/规范文本/派生标记/质量原因；权限隔离的分页和变更游标；源数据变更产生 invalidation，删除产生 tombstone；生产 QA 使用统一证据，移除前后端样本黑名单；引用与模型实际可见片段一致 |

### 事务与并发语义

- 模型生成使用 `NOT_SUPPORTED` 暂停调用者事务。`GenerationFence` 用独立短事务领取 generation 和发布结果。章节/学习资料同 scope 最新领取者胜出；QA 为追加记录，并发提问互不作废。
- 发布时重新锁定任务并检查来源 revision。生成期间替换字幕、翻译、OCR、VLM 或融合段，旧生成结果不得覆盖新来源。取消、软删除和租约失效也拒绝发布。
- QA 失败记录通过独立事务提交，外层调用抛异常或回滚仍可查询；任务已经删除则不新增失败内容。
- OCR 识别也移出持久化事务；自适应关键帧的图像处理和对象上传在数据库事务外，关键帧/OCR 两条记录与 revision 一起提交。
- Redis 仅作快速 claim/进度缓存；执行唯一性以 `task_execution` 为准。状态写入提交后才刷新缓存，SSE 以数据库状态裁决终态。

### 交付和恢复语义

系统提供 **至少一次消息投递、每个 task ID 一次执行资格**，不宣称跨 MySQL/RocketMQ/MinIO 的 exactly-once。

- `task_outbox`：`PENDING → DELIVERING → SENT`；claim 有效期 5 分钟，可恢复崩溃后的投递。重发保留 event ID，也保留 sourceLanguage 和 traceId。
- MQ 发送失败指数退避，最多 8 次，单次退避最高 300 秒。耗尽后事件为 `DEAD`，仍在排队的创建任务标为 `FAILED/MQ_DELIVERY_EXHAUSTED`，用户通过现有 retry API 创建新 task ID。
- `task_execution`：租约 90 秒，每 15 秒续约，每 30 秒检查过期。进程崩溃或执行器异常退出后，任务成为 `FAILED/TASK_EXECUTION_INTERRUPTED`；不会自动复用旧 worker 的工作目录。最终成功发布也要校验租约仍有效。
- 用户删除终态任务时，在同一事务中写 `deleted_at`、`DELETE` 变更和清理事件。外部对象删除在提交后执行；失败保留重试意图，清理事件不因达到 8 次而放弃。关键帧对象清理成功后才删除证据投影。
- 重复删除允许成功返回 0 条新删除，必要时补发幂等清理任务。删除范围是课程视觉证据与其索引投影，不删除可能被重试任务共享的原始上传。

运维可查询 `task_outbox.status/attempts/available_at/claim_until/last_error` 和 `task_execution.lease_until/completed_at`。`last_error` 只存异常类型，不存原始响应、密钥或对象路径。当前提供表级诊断和结构化日志；图形化运维界面不在本轮。

### 证据出口

- `GET /api/tasks/{taskId}/evidence?revision={revision}&after={evidenceId}&limit=100`
- `GET /api/evidence/changes?after={sequenceId}&limit=100`

两者均需要当前用户的 Bearer access token，不能由请求体指定 owner。第一页可省略 revision；之后必须沿用返回 revision 和 nextCursor。固定 revision 分页不会混合新旧快照；重新读取旧版本会得到 `stale=true`。每页最多 200 条。

`CourseEvidence` 包含 `evidenceId/courseId/ownerId/revision/sourceType/sourceId/sourceRefs/startMs/endMs/language/rawText/normalizedText/imageRef/derived/normalizationVersion/contentHash/retrievable/qualityReason/extractionConfidence/rawTextTruncated`。`courseId` 当前就是 task ID。翻译和视觉描述属于派生证据，不能冒充字幕原文。`rawText` 是当前源表保存的原文；OCR 在摄取时有长度上限，`rawTextTruncated` 明示截断，无法恢复旧代码已经丢弃的原文。

来源为字幕、字幕翻译、OCR、VLM；融合段继续服务时间轴/学习资料，避免把融合摘要当成另一份独立原始证据重复索引。`evidence-v1` 只做空白规范化，OCR 依据通用结构、置信度等规则决定可检索性，低质文本仍留在快照中供复查。这是规则质量基线，不是算法效果承诺。

快照按首次读取/QA 惰性物化。源写入在同一事务中产生 `INVALIDATE`，物化后产生 `UPSERT`，删除产生 `DELETE`。索引消费者收到 INVALIDATE 后拉取最新快照，按 `(courseId, revision)` 幂等构建；收到 DELETE 后删除投影。全局分配序列用数据库锁串行化，避免“先提交较大游标、后提交较小游标”导致永久漏读。无变化事件的历史课程首次按用户任务列表拉取即可补齐。

旧快照保留至课程删除，旧视觉对象可能因重处理被清理，因此 `imageRef` 不是永久图片归档。删除立即禁止读取旧/新快照，异步清理保留墓碑。尚未建立长期自动保留期限或 Python 索引消费者，后者属于 L1。

## 验收与复现

```bash
# 后端包含真实事务/H2故障窗口回归；须安装 Java 21、FFmpeg
cd backend
bash mvnw -B package

# 前端
cd ../frontend
npm ci
npm run test:unit
npm run build
npm audit

# 在仓库根目录运行全链路；使用独立实例和 no-key Demo 配置
cp .env.demo.example .env.demo.local
LECTURELENS_DEMO_INSTANCE=cleanup bash scripts/demo/start-infrastructure.sh
python3 scripts/ci/mock-e2e.py --project lecturelens-demo-cleanup
```

如 `.env.demo.local` 已存在，保留并检查配置和端口；不要覆盖自己的真实服务配置。E2E 脚本拒绝真实 AI 模式及已占用的后端端口，只负责启动/停止自身的后端进程。基础设施使用单独 Compose project，结束后可通过现有停止脚本关闭。

回归重点：外层事务回滚后 QA 失败仍在、慢/失败模型不持有事务、生成代次竞争、来源变更、取消/删除拒绝旧写入、MQ 发送失败重试、publisher claim 崩溃、重复投递、worker 租约失效、MinIO 清理失败重试、固定版本分页、跨用户隔离、OCR-only 与数学/历史/生物/噪声 fixtures、前端引用原样渲染。

实际验收结果见下方最终记录。Mock E2E 使用真实 MySQL/Redis/RocketMQ/MinIO/FFmpeg，AI 为确定性 Mock；不证明真实 ASR/OCR/VLM 识别质量或长视频效果。GitHub CI 工作流已补齐，远程运行状态须在提交推送后观察。

## 升级注意事项

新增 V22/V23，V1–V21 内容未改动。部署前停止旧 worker 并备份数据库，避免旧代码绕过新边界。V22 将升级前仍处于 CREATED/QUEUED/RUNNING/RETRYING 的任务标为 `TASK_UPGRADE_INTERRUPTED`，由用户创建新任务重试；已完成课程保留。MySQL DDL 不能按应用事务整体回滚，不能以删除迁移记录或自动 Flyway repair 代替恢复流程。

后续仍按蓝图进入 L1：Python 检索服务、embedding/hybrid retrieval、检索评测。旧 CourseVideoChunk 写入路径、LangChain4j 候选 Provider、旧检索兼容构造路径等按 C4 随功能替换下线，不在此次清理中做无验证的大规模删除。

## 最终验收记录（2026-09-11）

| 检查 | 结果 |
| --- | --- |
| 后端 `mvn -B package` | **1327 tests，0 failures，0 errors，0 skipped；BUILD SUCCESS** |
| 前端重新 `npm ci` + `npm run test:unit` | **13 个测试文件、37 项测试通过** |
| 前端 `npm run build` | 类型检查及构建通过；仍有现有大包和第三方 PURE 注释告警 |
| `npm audit`（含开发依赖） | **0 个已报告漏洞**；nanoid 3.3.19、Vitest/mocker 4.1.11、brace-expansion 2.1.4 |
| MySQL 8.4 + Flyway | 独立空库首次完整执行 V1–V23；后续启动 checksum 验证通过 |
| 最终 Mock E2E | 上传/合并/MinIO → outbox/RocketMQ → FFmpeg/Mock ASR → 翻译/学习资料/制品 → 章节 → 分页证据/QA 引用全部通过 |
| 权限与删除 | 跨用户读取返回 404；删除墓碑可消费；旧版本不可读取；重复删除返回 0；outbox 最终 SENT，证据/快照/关键帧记录清理为 0 |
| 差异检查 | `git diff --check` 通过；已发布 V1–V21 未修改 |

最终 E2E 命令：`python3 scripts/ci/mock-e2e.py --project lecturelens-demo-cleanup`。本轮测试实例在验收后关闭并保留数据卷；其他项目的容器未改动。上述结果为提交前的本地验收记录；远程 CI 状态以对应 PR 的 Checks 为准。本轮未调用付费模型，未重新验证历史长视频效果。


### 远程 CI 收口

远程冷启动验证暴露了 Demo 主题初始化的竞态：按集群创建主题时，Broker 尚未注册可能导致没有实际创建。Linux/PowerShell 启动脚本现改为直接向 Broker 创建主题，并要求明确的 RPC 成功响应，不能只依赖命令退出码。相关行为可对照 [RocketMQ 5.3.4 创建主题命令源码](https://github.com/apache/rocketmq/blob/rocketmq-all-5.3.4/tools/src/main/java/org/apache/rocketmq/tools/command/topic/UpdateTopicSubCommand.java)。

Mock E2E 另使用打包 SDK 探测 Proxy/主题路由（有界等待、不发送消息），测试进程 MQ 请求超时默认 10 秒，并等待 worker 关闭已完成租约。业务运行配置不变。最新远程结果见 [PR #25 Checks](https://github.com/a27497/lecturelens/pull/25/checks)。

主题初始化修复已在全新的 `cleanup-topic` 实例和空数据库上通过完整 Mock E2E；Linux 实例名称契约测试通过。PowerShell 使用相同的 Broker 命令，当前 Linux 环境未执行 PowerShell 脚本。
