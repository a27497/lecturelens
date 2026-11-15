# 字幕就绪即可学习（Step 3）

开关：`PIPELINE_EARLY_LEARNING_ENABLED`（`courselingo.pipeline.early-learning.enabled`），**默认 `false`**。迁移：`V33__subtitles_ready_learning.sql`。

## 行为

开关关闭时行为与此前完全一致：只有 `SUCCEEDED` 的课程可学习；翻译、学习资料或下载文件任一步失败都会让整门课程 `FAILED`。

开关开启后：

1. `PERSIST_SUBTITLES` 成功（或从检查点恢复）后，若本次运行仍持有执行租约、任务仍为 `RUNNING` 且至少有一条字幕，写入 `analysis_task.learning_ready_at`。从此课程即为“可学习”：证据索引立即排队构建，课程问答、学习助手（Agent）、闪卡、Tutor 均按同一规则开放。
2. 翻译（`TRANSLATE_SUBTITLES`）、学习资料（`GENERATE_LEARNING_PACKAGE`）、下载文件（`GENERATE_ARTIFACTS`）在后台继续，并在 `task_stage_outcome` 中各自记录 `SUCCEEDED`/`FAILED`。其中任一步失败只让对应功能不可用，课程最终仍为 `SUCCEEDED`（`error_code=PIPELINE_DEGRADED_BACKGROUND`，与既有 `PIPELINE_DEGRADED_ASR_ONLY`/`VISUAL_ONLY` 降级约定一致）。视觉分支（OCR/视觉分析/融合）本来就是独立降级，不变。
3. 以下失败仍终止整个运行：取消、执行租约丢失/任务状态改变、截止时间超时、源内容变化、策略快照无效、成本记账不完整（含 `WRITE_AI_CALL_RECORD` 失败）、以及字幕就绪之前的任何失败。
4. 学习开放只在本次运行内有效：每次 `QUEUED→RUNNING` 清空 `learning_ready_at`；任务转为 `FAILED`/`CANCELED` 后不再可学习。

可学习判定（后端 `LearningAvailability.learnable`，前端 `courseLearnable`）：`status='SUCCEEDED' OR (status='RUNNING' AND learning_ready_at IS NOT NULL)`。

## 迟到的译文不会使已有学习会话失效

学习会话、Tutor 会话与证据 ID 都绑定 `content_revision`；以往任何来源变化都会 `content_revision+1`，旧会话随即 `STUDY_CONFLICT`/stale。课程在运行中提前开放后，译文等派生来源仍会陆续写入，若沿用旧规则会让刚开始的学习全部失效。

处理方式（`LearnableEvidencePublisher`，由 `GenerationFence.sourceChanging` 在“运行中且已可学习”时委托）：在写入事务提交前重新收集证据并与当前修订已发布的快照比较：

- 仅新增：新增证据追加到**同一修订**的快照（已有证据 ID、内容与修订号不变），记录同修订 `UPSERT`，索引对同一修订增量重建；
- 已有证据被修改或删除：照旧推进修订（`INVALIDATE`），保证引用正确性优先；
- 写入事务回滚时不发布任何内容。

索引对同一修订“追赶”期间（`PENDING`/`INDEXING`/`FAILED` 且 `indexedRevision == revision`），旧索引仍覆盖会话可能引用的全部证据，因此学习与问答继续可用（`IndexStatus.servable()`、前端 `evidenceIndexServable`）。不同修订的索引永远不会被使用。

Agent 服务（agent-service）无改动：同修订、更高序号的增量清单本就被其索引存储接受。

## API

- `GET /api/tasks/{id}`、任务 SSE 进度事件：新增 `learningReady`（布尔）。
- `GET /api/tasks/{id}/results`：新增 `learningPackageStatus`、`artifactsStatus`（`NOT_STARTED|RUNNING|SUCCEEDED|FAILED|SKIPPED|CANCELED`）；`translationStatus` 在后台翻译失败时为 `FAILED`。

## 已知限制

- 已 `SUCCEEDED` 的课程不允许重新分析，因此后台阶段失败后目前没有“只重跑该阶段”的入口。
- 开关在运行时读取（不像 Translation V2 那样冻结进任务策略快照）；切换只影响之后开始的运行。
