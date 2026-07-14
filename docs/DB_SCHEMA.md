# LectureLens Database Schema

## 数据原则

- MySQL 是事实来源。
- Redis 只做短状态，不作为最终事实来源。
- 分片上传的高频 chunk 状态优先放 Redis Set，不默认逐片落库。
- MinIO 保存原始视频、音频中间文件、字幕文件、学习包文件。
- 所有 owner 资源必须有 `user_id`。
- 所有数据库结构变更必须通过 Flyway 管理。

## Flyway 迁移规则

- A6 只建立 Flyway 迁移机制、MySQL 8.4 LTS JDBC 配置边界和迁移目录，不创建任何业务表。
- 迁移脚本统一放在 `backend/src/main/resources/db/migration/`。
- 迁移文件命名遵循 Flyway 版本化脚本规则，例如 `V版本号__说明.sql`。
- B1 创建 `user_account`、`refresh_token` 两张认证基础表，对应迁移文件 `V1__init_user_and_auth.sql`。
- B6 创建 `upload_session` 上传会话表，对应迁移文件 `V2__init_upload_session.sql`。
- C1 创建 `analysis_task`、`task_log` 两张任务基础表，对应迁移文件 `V3__init_analysis_task_and_task_log.sql`。
- D7 创建 `subtitle_segment` 字幕转写片段表，对应迁移文件 `V4__create_subtitle_segment_table.sql`。
- D8 创建 `subtitle_translation_segment` 字幕翻译片段表，对应迁移文件 `V5__create_subtitle_translation_segment_table.sql`。
- D9 创建 `learning_package` 学习包结构化输出表，对应迁移文件 `V6__create_learning_package_table.sql`。
- D10 创建 `artifact_file` 制品文件元数据表，对应迁移文件 `V7__create_artifact_file_table.sql`。
- Phase D 按 TODO 顺序创建字幕、学习包、制品和 AI 调用记录相关表。
- VIDEO-CONTEXT-R1 创建 `course_video_chunk` 后端上下文 chunk 索引表，对应迁移文件 `V17__create_course_video_chunk.sql`。
- 在 A7 建立 MySQL 容器前，默认 `FLYWAY_ENABLED=false`，避免本地没有 MySQL 时阻塞应用启动和测试；A7 之后再开启迁移验证。
- 服务器标准部署通过 `scripts/server/apply-db-migrations.sh` 在后端重启前执行 Flyway，并验证 `flyway_schema_history` 至少包含成功的 V11 记录。脚本不得清空数据库、删除上传文件、手工插入 history 记录或输出密码、token、object key、API key。

## user_account

用户账号表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT | 主键，自增 |
| email | VARCHAR(255) | 登录邮箱，唯一 |
| password_hash | VARCHAR(255) | BCrypt 哈希后的密码，不保存明文 |
| status | VARCHAR(32) | 用户状态，例如 ACTIVE / DISABLED / LOCKED；本阶段只建字段，不实现业务枚举 |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |
| updated_at | DATETIME(3) | 更新时间，默认 `CURRENT_TIMESTAMP(3)`，更新时自动刷新 |

索引与约束：

- 主键：`PRIMARY KEY (id)`。
- 唯一索引：`uk_user_account_email (email)`。
- 普通索引：`idx_user_account_status (status)`。

## refresh_token

刷新令牌表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT | 主键，自增 |
| user_id | BIGINT | 所属用户 ID |
| token_hash | VARCHAR(255) | Refresh Token 哈希值，不保存原始 token |
| expires_at | DATETIME(3) | 过期时间 |
| revoked_at | DATETIME(3) | 撤销时间，`NULL` 表示未撤销 |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |

索引、外键与删除策略：

- 主键：`PRIMARY KEY (id)`。
- 普通索引：`idx_refresh_token_user_expires (user_id, expires_at)`。
- 普通索引：`idx_refresh_token_hash (token_hash)`。
- 普通索引：`idx_refresh_token_revoked (revoked_at)`。
- 外键：`fk_refresh_token_user_id`，`refresh_token.user_id` 引用 `user_account.id`。
- 删除策略：`ON DELETE CASCADE`，用户删除时对应 refresh token 随用户删除。
- 更新策略：`ON UPDATE RESTRICT`。

## upload_session

上传会话表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | VARCHAR(64) | 主键，上传会话 ID，后续由后端生成，不使用用户传入值 |
| user_id | BIGINT | 上传所属用户 |
| filename | VARCHAR(255) | 原始展示文件名，仅用于展示，不作为真实存储路径 |
| ext | VARCHAR(32) | 文件扩展名，后续上传安全校验使用 |
| total_chunks | INT | 总分片数，必须大于 0 |
| chunk_size_bytes | BIGINT | 每个分片大小，必须大于 0 |
| size_bytes | BIGINT | 文件总大小，必须大于 0 |
| file_md5 | VARCHAR(64) | 完整文件 MD5，后续用于秒传和防重复分析 |
| status | VARCHAR(32) | 上传状态：新上传使用 CREATED / UPLOADING / STORED / MERGING / FAILED / CANCELLED；UPLOADED 仅为旧数据兼容状态 |
| storage_type | VARCHAR(32) | 存储类型，最终版为 MinIO |
| object_key | VARCHAR(255) | 对象存储 key，由后端生成，不能使用用户原始文件名 |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |
| updated_at | DATETIME(3) | 更新时间，默认 `CURRENT_TIMESTAMP(3)`，更新时自动刷新 |

索引、外键与删除策略：

- 主键：`PRIMARY KEY (id)`。
- 普通索引：`idx_upload_session_user_created (user_id, created_at)`。
- 普通索引：`idx_upload_session_md5 (file_md5)`。
- 普通索引：`idx_upload_session_user_status_created (user_id, status, created_at)`。
- 外键：`fk_upload_session_user_id`，`upload_session.user_id` 引用 `user_account.id`。
- 删除策略：`ON DELETE CASCADE`，用户删除时对应上传会话随用户删除。
- 更新策略：`ON UPDATE RESTRICT`。
- CHECK 约束：`total_chunks > 0`、`chunk_size_bytes > 0`、`size_bytes > 0`。

MySQL 保存上传会话事实数据；分片上传高频短状态使用 Redis Set `cl:u:chunks:{uploadId}`。Redis 不是最终事实来源，Redis 丢失、禁用或读取失败时回退本地 staging `.part` 文件扫描。complete 必须按本地 `.part` 完整性、size、MD5 和视频头校验，随后把 assembled 文件写入 MinIO，写入成功并更新为 `STORED` 后才清理 chunk state。写入失败保留 Redis 状态、分片和 assembled 文件。

MinIO 正式引用完整性统计只计入 `upload_session.status = STORED` 的原始上传对象，并继续计入全部 `artifact_file` 与 `video_keyframe` 对象。legacy `UPLOADED` 表示升级前的本地 assembled 遗留记录，不计入正式 S3/MinIO 引用统计，也不自动迁移、补写或修改。

## analysis_task

分析任务表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | VARCHAR(64) | 主键，分析任务 ID，由后端生成 |
| user_id | BIGINT | 所属用户 ID，owner 隔离字段 |
| upload_id | VARCHAR(64) | 关联上传会话 ID |
| target_language | VARCHAR(32) | 目标语言 |
| status | VARCHAR(32) | 任务状态，默认 `CREATED`；状态流转由 C2 实现 |
| progress_percent | INT | 任务进度百分比，默认 0，范围 0 到 100 |
| current_stage | VARCHAR(64) | 当前处理阶段，允许为空 |
| error_code | VARCHAR(64) | 失败错误码，允许为空 |
| error_message | VARCHAR(1024) | 失败错误摘要，允许为空，不记录密钥或本地路径 |
| retry_count | INT | 已重试次数，默认 0，必须大于等于 0 |
| max_retry_count | INT | 最大重试次数，默认 3，必须大于等于 0 |
| started_at | DATETIME(3) | 开始时间，允许为空 |
| finished_at | DATETIME(3) | 结束时间，允许为空 |
| deleted_at | DATETIME(3) | 用户逻辑删除时间；`NULL` 表示未删除 |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |
| updated_at | DATETIME(3) | 更新时间，默认 `CURRENT_TIMESTAMP(3)`，更新时自动刷新 |

索引、外键与删除策略：

- 主键：`PRIMARY KEY (id)`。
- 普通索引：`idx_analysis_task_user_created (user_id, created_at)`。
- 普通索引：`idx_analysis_task_user_status_created (user_id, status, created_at)`。
- 普通索引：`idx_analysis_task_upload (upload_id)`。
- 普通索引：`idx_analysis_task_status_created (status, created_at)`。
- 普通索引：`idx_analysis_task_user_deleted_created (user_id, deleted_at, created_at)`。
- 普通索引：`idx_analysis_task_user_deleted_status_created (user_id, deleted_at, status, created_at)`。
- 外键：`fk_analysis_task_user_id`，`analysis_task.user_id` 引用 `user_account.id`。
- 删除策略：`ON DELETE CASCADE`，删除用户时清理其任务。
- 外键：`fk_analysis_task_upload_id`，`analysis_task.upload_id` 引用 `upload_session.id`。
- 删除策略：`ON DELETE RESTRICT`，已有任务依赖的上传记录不允许被删除，避免任务悬空。
- 更新策略：以上外键均为 `ON UPDATE RESTRICT`。
- CHECK 约束：`progress_percent >= 0 AND progress_percent <= 100`、`retry_count >= 0`、`max_retry_count >= 0`。

C2 已实现任务状态机代码，`analysis_task.status` 当前使用以下状态：

| 状态 | 说明 |
| --- | --- |
| `CREATED` | 任务记录已创建，尚未进入队列 |
| `QUEUED` | 任务已准备进入异步队列，后续 RocketMQ Producer 发送成功后使用 |
| `RUNNING` | 任务被 Consumer / Runner 开始处理 |
| `SUCCEEDED` | 任务成功完成，`progress_percent` 必须为 100 |
| `FAILED` | 任务失败且不可继续执行，或达到最大重试次数 |
| `CANCELED` | 任务被用户或系统取消 |
| `RETRYING` | 任务失败后进入重试准备状态 |

合法状态流转为：`CREATED -> QUEUED`、`QUEUED -> RUNNING`、`RUNNING -> SUCCEEDED`、`RUNNING -> FAILED`、`RUNNING -> RETRYING`、`RUNNING -> CANCELED`、`RETRYING -> QUEUED`、`RETRYING -> FAILED`、`QUEUED -> CANCELED`、`CREATED -> CANCELED`。任务状态更新按 `task_id + user_id` owner scope 执行，并同步写入 `task_log`。C2 不创建任务 API，不发送 RocketMQ 消息，不接入 Redis、FFmpeg、ASR、LLM 或 LangChain4j 调用。MySQL 保存任务事实数据；Redis 后续只保存短状态、进度快照、claim 和限流，不是事实来源。

C8 已实现任务进度 Redis 短状态 `cl:t:progress:{taskId}`。该 key 保存任务当前 `taskId`、`status`、`progressPercent`、`currentStage`、脱敏截断后的 `errorCode` / `errorMessage` 和 `updatedAt` JSON 快照，并设置 TTL。快照不保存 `userId`、`objectKey`、本地路径、token、secret 或 API key。Redis 禁用时使用 no-op 实现；Redis 读写删除失败只降级为空结果或 warn 日志，不改变 `analysis_task` 作为最终事实来源的语义，不作为状态机合法性判断依据。

C9 已实现任务执行 Redis claim 短状态 `cl:t:claim:{taskId}`。该 key 使用原子 NX + TTL 领取语义，value 只保存 `taskId`、`requestId`、`claimedAt`、`expiresAt`，不保存 `userId`、`objectKey`、本地路径、token、secret 或 API key。释放 claim 时按 `requestId` 校验，避免误删其他执行器的 claim。Redis claim 只用于防重复执行，不替代 MySQL `analysis_task` 事实数据、owner scope、消息一致性校验或任务状态机校验。

C10 已实现任务创建限流 Redis 短状态 `cl:rate:analysis:{userId}`。该 key 使用固定窗口 counter + TTL 限制单个用户创建分析任务的频率，value 只保存计数值，不保存 token、secret、API key、objectKey 或本地路径。Redis rate limit 只是短状态限流组件，不是 MySQL 任务事实来源；Redis 禁用时使用 no-op 实现，Redis 异常时按 fail-open 策略记录 warn 并允许后续流程。

PRODUCT-POLISH-R1 通过 `V18__add_analysis_task_soft_delete.sql` 增加 `deleted_at`。这不是 MyBatis-Plus 全局 `TableLogic`：用户列表、详情、命令和 owner guard 显式追加 `deleted_at IS NULL`；批量删除服务使用单独的包含已删除记录查询以支持幂等。删除只更新 `analysis_task.deleted_at` 与 `updated_at`，不物理删除上传、字幕、翻译、学习包、章节、问答、关键帧、Video Segment、artifact、AI 调用记录或任务日志，也不改变任务创建限流和历史审计语义。

## task_log

任务日志表。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT | 主键，自增 |
| task_id | VARCHAR(64) | 所属分析任务 ID |
| user_id | BIGINT | 所属用户 ID，owner 隔离字段 |
| level | VARCHAR(16) | 日志级别：`INFO` / `WARN` / `ERROR` |
| stage | VARCHAR(64) | 任务阶段，允许为空 |
| message | VARCHAR(1024) | 日志摘要，不记录密钥或本地路径 |
| detail | TEXT | 内部错误详情，允许为空，不记录 access token、refresh token、API key、secret key、本地路径或 MinIO secret |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |

索引、外键与删除策略：

- 主键：`PRIMARY KEY (id)`。
- 普通索引：`idx_task_log_task_created (task_id, created_at)`。
- 普通索引：`idx_task_log_user_created (user_id, created_at)`。
- 普通索引：`idx_task_log_level_created (level, created_at)`。
- 外键：`fk_task_log_task_id`，`task_log.task_id` 引用 `analysis_task.id`。
- 删除策略：`ON DELETE CASCADE`，删除任务时清理任务日志。
- 外键：`fk_task_log_user_id`，`task_log.user_id` 引用 `user_account.id`。
- 删除策略：`ON DELETE CASCADE`，删除用户时清理其日志。
- 更新策略：以上外键均为 `ON UPDATE RESTRICT`。
- CHECK 约束：`level IN ('INFO', 'WARN', 'ERROR')`。

## subtitle_segment

字幕转写片段表，是 ASR 转写结果持久化后的字幕事实来源。D7 只保存原始转写文本，不保存翻译结果、制品对象路径、metadata 或 provider 原始响应。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT | 主键，自增 |
| task_id | VARCHAR(64) | 分析任务 ID |
| user_id | BIGINT | 所属用户 ID，owner 隔离字段 |
| segment_index | INT | ASR 片段序号，必须大于等于 0 |
| start_millis | BIGINT | 片段开始时间，毫秒，必须大于等于 0 |
| end_millis | BIGINT | 片段结束时间，毫秒，必须大于等于 `start_millis` |
| language | VARCHAR(32) | 原文语言 |
| text | TEXT | 原始转写文本，不是翻译结果 |
| provider | VARCHAR(64) | 安全 provider 名称，允许为空；不保存密钥、请求头或原始响应 |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |
| updated_at | DATETIME(3) | 更新时间，默认 `CURRENT_TIMESTAMP(3)`，更新时自动刷新 |

索引、外键与删除策略：

- 主键：`PRIMARY KEY (id)`。
- 唯一索引：`uk_subtitle_segment_task_user_index (task_id, user_id, segment_index)`，支持同一 `taskId + userId` 下幂等覆盖写入。
- 普通索引：`idx_subtitle_segment_task_user (task_id, user_id)`，支持 owner scope 查询。
- 普通索引：`idx_subtitle_segment_user_created (user_id, created_at)`。
- 外键：`fk_subtitle_segment_task_id`，`subtitle_segment.task_id` 引用 `analysis_task.id`。
- 删除策略：`ON DELETE CASCADE`，删除任务时清理其字幕片段。
- 外键：`fk_subtitle_segment_user_id`，`subtitle_segment.user_id` 引用 `user_account.id`。
- 删除策略：`ON DELETE CASCADE`，删除用户时清理其字幕片段。
- 更新策略：以上外键均为 `ON UPDATE RESTRICT`。
- CHECK 约束：`segment_index >= 0`、`start_millis >= 0`、`end_millis >= start_millis`。

D7 提供 `SubtitleSegmentPersistenceService` 将 `SpeechToTextResult` / `TranscribedSegment` 转换为 `subtitle_segment` 行。覆盖保存按 `taskId + userId` 先删除旧片段再插入新片段，并要求在同一事务内完成；查询和删除同样按 `taskId + userId` scope 执行。D7 不接入 Runner，不调用 FFmpeg、ASR Provider、LLM 或 LangChain4j，不生成翻译、摘要、Q&A、术语表、学习包或制品，不写入 `artifact_file` 或 `ai_call_record`。

## subtitle_translation_segment

TRANSLATION-DUAL-OUTPUT-R1 keeps the existing schema and strengthens the write contract: provider calls and result validation complete before a successful translation transaction replaces all owner/task/language segment rows and the matching `task_full_text_result` together. The translated full text is derived from the same ordered segment translations; partial segment coverage or a full-text-only state is not committed.

字幕翻译片段表，是基于 D7 已持久化转写字幕生成的目标语言字幕事实来源。D8 只保存翻译后的字幕片段，不保存 artifact 字段、metadata 大 JSON、objectKey、本地路径、Authorization header、API Key、token、secret、LLM 原始响应或 `ai_call_record`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT | 主键，自增 |
| task_id | VARCHAR(64) | 分析任务 ID，引用 `analysis_task.id` |
| user_id | BIGINT | owner 用户 ID，引用 `user_account.id` |
| segment_index | INT | 源字幕片段序号 |
| start_millis | BIGINT | 源字幕开始时间，毫秒 |
| end_millis | BIGINT | 源字幕结束时间，毫秒 |
| source_language | VARCHAR(32) | 源字幕语言 |
| target_language | VARCHAR(32) | 目标翻译语言 |
| translated_text | TEXT | 翻译后的字幕文本 |
| provider | VARCHAR(64) | 安全 LLM provider 名称，可为空 |
| created_at | DATETIME(3) | 创建时间 |
| updated_at | DATETIME(3) | 更新时间 |

索引、外键与约束：

- 主键：`PRIMARY KEY (id)`。
- 唯一索引：`uk_subtitle_translation_task_user_lang_index (task_id, user_id, target_language, segment_index)`，支持同一 `taskId + userId + targetLanguage` 下幂等覆盖写入。
- 普通索引：`idx_subtitle_translation_task_user_lang (task_id, user_id, target_language)`，支持 owner scope + 目标语言查询。
- 普通索引：`idx_subtitle_translation_user_created (user_id, created_at)`。
- 外键：`fk_subtitle_translation_task_id`，`subtitle_translation_segment.task_id` 引用 `analysis_task.id`。
- 外键：`fk_subtitle_translation_user_id`，`subtitle_translation_segment.user_id` 引用 `user_account.id`。
- Check：`segment_index >= 0`、`start_millis >= 0`、`end_millis >= start_millis`。

D8 提供 `SubtitleTranslationService` 读取当前 `taskId + userId` 的 D7 源字幕，构造 JSON-only `LlmRequest`，调用注入的 `LlmProvider` 抽象，解析 `{segments:[{index,text}]}` 后按 `taskId + userId + targetLanguage` 在事务内覆盖保存。`SubtitleTranslationQueryService` 查询翻译字幕时按 `segment_index ASC` 返回不包含 `userId` 的 view。D8 不接入 Runner，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 真实外部 LLM，不生成摘要、Q&A、术语表、学习包或制品，不写入 `artifact_file` 或 `ai_call_record`，不发送 MQ，不新增 API。

## learning_package

学习包结构化输出表，是基于 D7 源字幕和 D8 翻译字幕生成的学习包事实来源。D9 只保存结构化学习包字段，不保存 artifact 字段、metadata 大 JSON、LLM 原始响应大 JSON、objectKey、本地路径、Authorization header、API Key、token、secret 或 `ai_call_record`。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT | 主键，自增 |
| task_id | VARCHAR(64) | 分析任务 ID，引用 `analysis_task.id` |
| user_id | BIGINT | 所属用户，引用 `user_account.id` |
| source_language | VARCHAR(32) | 源字幕语言 |
| target_language | VARCHAR(32) | 目标学习语言 |
| title | VARCHAR(255) | 学习包标题 |
| summary | TEXT | 学习包摘要 |
| key_points_json | JSON | 重点内容数组，保存解析后的结构化 JSON |
| glossary_json | JSON | 术语数组，保存解析后的结构化 JSON，可为空数组 |
| qa_json | JSON | Q&A 数组，保存解析后的结构化 JSON，可为空数组 |
| provider | VARCHAR(64) | 安全 provider 名称，可为空 |
| schema_version | VARCHAR(32) | 学习包结构版本 |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |
| updated_at | DATETIME(3) | 更新时间，默认 `CURRENT_TIMESTAMP(3)` 并自动更新 |

- 主键：`id`。
- 唯一索引：`uk_learning_package_task_user_lang (task_id, user_id, target_language)`，支持同一 `taskId + userId + targetLanguage` 下幂等覆盖写入。
- 普通索引：`idx_learning_package_task_user (task_id, user_id)`，支持 owner scope 查询。
- 普通索引：`idx_learning_package_user_created (user_id, created_at)`。
- 外键：`fk_learning_package_task_id`，`learning_package.task_id` 引用 `analysis_task.id`。
- 外键：`fk_learning_package_user_id`，`learning_package.user_id` 引用 `user_account.id`。

D9 提供 `LearningPackageService` 读取当前 `taskId + userId` 的 D7 源字幕和 `taskId + userId + targetLanguage` 的 D8 翻译字幕，构造 JSON-only `LlmRequest`，调用注入的 `LlmProvider` 抽象，解析 `{title,summary,keyPoints,glossary,qa}` 后按 `taskId + userId + targetLanguage` 在事务内覆盖保存。`LearningPackageQueryService` 查询学习包时返回不包含 `userId` 的 view。D9 不接入 Runner，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 真实外部 LLM，不生成 SRT/VTT/Markdown/JSON 文件，不写入 `artifact_file` 或 `ai_call_record`，不发送 MQ，不新增 API。

## artifact_file

制品文件元数据表，是后续 D11-D14 生成 SRT/VTT/Markdown/JSON 内容后登记存储对象的事实来源。D10 只提供通用制品写入和元数据登记能力，不生成具体制品内容，不读取字幕表或学习包表，不保存 metadata 大 JSON、LLM/ASR 原始响应、token、secret、API Key、Authorization header 或本地完整路径。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT | 主键，自增 |
| task_id | VARCHAR(64) | 分析任务 ID，引用 `analysis_task.id` |
| user_id | BIGINT | 所属用户，引用 `user_account.id` |
| artifact_type | VARCHAR(32) | 制品类型：SRT / VTT / MARKDOWN / JSON |
| language | VARCHAR(32) | 制品语言 |
| file_name | VARCHAR(255) | 安全文件名，不包含路径穿越或绝对路径 |
| content_type | VARCHAR(128) | 制品 MIME 类型 |
| storage_backend | VARCHAR(32) | 存储后端名称 |
| object_key | VARCHAR(512) | 后端生成的对象存储 key，不返回给 view |
| size_bytes | BIGINT | 文件大小 |
| sha256 | VARCHAR(64) | 文件内容 SHA-256 |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |
| updated_at | DATETIME(3) | 更新时间，默认 `CURRENT_TIMESTAMP(3)` 并自动更新 |

- 主键：`id`。
- 唯一索引：`uk_artifact_file_task_user_type_lang (task_id, user_id, artifact_type, language)`，支持同一 `taskId + userId + artifactType + language` 下幂等覆盖写入。
- 唯一索引：`uk_artifact_file_object_key (object_key)`，防止对象 key 重复登记。
- 普通索引：`idx_artifact_file_task_user (task_id, user_id)`，支持 owner scope 查询。
- 普通索引：`idx_artifact_file_user_created (user_id, created_at)`。
- 外键：`fk_artifact_file_task_id`，`artifact_file.task_id` 引用 `analysis_task.id`。
- 外键：`fk_artifact_file_user_id`，`artifact_file.user_id` 引用 `user_account.id`。
- Check：`size_bytes >= 0`。

D10 提供 `ArtifactFileService` 使用现有 `StorageService` 写入对象，并按 `taskId + userId + artifactType + language` 在事务内覆盖保存 `artifact_file` 元数据。`ArtifactFileQueryService` 按 `taskId + userId` 或 `taskId + userId + artifactType + language` 查询，返回 view 不包含 `userId` 和 `objectKey`。D10 测试只使用 fake storage，不真实连接 MinIO；D10 不接入 Runner，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 或外部 LLM，不生成 SRT/VTT/Markdown/JSON 具体内容，不写入 `ai_call_record`，不发送 MQ，不新增 API。

## ai_call_record

AI 调用记录表，用于保存 ASR / LLM 调用的可审计安全元数据。D15 只提供记录能力，不接入 Runner、不调用 ASR / LLM / FFmpeg、不保存原始 prompt、原始 response、原始 ASR 文本、字幕全文、音频路径、对象 key、本地路径、Authorization header、API key、token 或 secret。

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| id | BIGINT | 主键，自增 |
| task_id | VARCHAR(64) | 分析任务 ID，引用 `analysis_task.id` |
| user_id | BIGINT | 所属用户 ID，owner 隔离字段，引用 `user_account.id` |
| call_type | VARCHAR(32) | 调用类型：`ASR` / `LLM` |
| stage | VARCHAR(64) | 调用阶段：`TRANSCRIPTION` / `TRANSLATION` / `LEARNING_PACKAGE` |
| provider | VARCHAR(64) | 安全 provider 名称 |
| model | VARCHAR(128) | 模型名称，允许为空 |
| status | VARCHAR(32) | 调用状态：`STARTED` / `SUCCEEDED` / `FAILED` |
| started_at | DATETIME(3) | 调用开始时间 |
| finished_at | DATETIME(3) | 调用结束时间，允许为空 |
| duration_millis | BIGINT | 调用耗时，毫秒，允许为空且必须大于等于 0 |
| prompt_tokens | INT | prompt token 数，允许为空且必须大于等于 0 |
| completion_tokens | INT | completion token 数，允许为空且必须大于等于 0 |
| total_tokens | INT | 总 token 数，允许为空且必须大于等于 0 |
| input_units | INT | 输入抽象计量，例如字符数或音频秒数，不保存原文，允许为空且必须大于等于 0 |
| output_units | INT | 输出抽象计量，例如字符数，不保存原文，允许为空且必须大于等于 0 |
| request_fingerprint | VARCHAR(128) | 请求 hash / fingerprint，允许为空，不保存原始请求 |
| response_fingerprint | VARCHAR(128) | 响应 hash / fingerprint，允许为空，不保存原始响应 |
| error_code | VARCHAR(64) | 错误码，允许为空 |
| error_message | VARCHAR(512) | 脱敏并截断后的错误摘要，允许为空 |
| retryable | TINYINT(1) | 是否可重试，允许为空 |
| created_at | DATETIME(3) | 创建时间，默认 `CURRENT_TIMESTAMP(3)` |
| updated_at | DATETIME(3) | 更新时间，默认 `CURRENT_TIMESTAMP(3)` 并自动更新 |

索引、外键与约束：

- 主键：`PRIMARY KEY (id)`。
- 普通索引：`idx_ai_call_record_task_user (task_id, user_id)`，支持 owner scope 查询。
- 普通索引：`idx_ai_call_record_user_created (user_id, created_at)`，支持用户维度审计列表。
- 普通索引：`idx_ai_call_record_task_stage (task_id, stage)`，支持任务阶段维度排查。
- 普通索引：`idx_ai_call_record_status (status)`，支持按调用状态排查。
- 外键：`fk_ai_call_record_task_id`，`ai_call_record.task_id` 引用 `analysis_task.id`。
- 外键：`fk_ai_call_record_user_id`，`ai_call_record.user_id` 引用 `user_account.id`。
- 删除策略：任务或用户删除时级联删除对应 AI 调用记录。
- 更新策略：以上外键均为 `ON UPDATE RESTRICT`。
- CHECK 约束：`duration_millis`、`prompt_tokens`、`completion_tokens`、`total_tokens`、`input_units`、`output_units` 为空或大于等于 0。

D15 提供 `AiCallRecordService` 记录调用开始、成功和失败结果。`startCall` 创建 `STARTED` 记录，`completeCall` 只按 `id + taskId + userId` 更新 owner 记录为 `SUCCEEDED`，`failCall` 只按 `id + taskId + userId` 更新 owner 记录为 `FAILED` 并保存脱敏截断后的错误摘要，`listByTask` 只按 `taskId + userId` 查询并按 `created_at ASC, id ASC` 稳定排序。返回 view 不包含 `userId`，命令和表结构都不接收或保存 raw prompt、raw response、音频路径、对象 key、本地路径、Authorization header、API key、token 或 secret。

## 索引原则

- owner 资源必须包含 `user_id` 索引。
- `analysis_task` 按 `user_id`、`status`、`created_at` 支持列表查询。
- `subtitle_segment` 按 `task_id`、`user_id`、`segment_index` 排序读取。
- `subtitle_translation_segment` 按 `task_id`、`user_id`、`target_language`、`segment_index` 排序读取。
- `learning_package` 按 `task_id`、`user_id`、`target_language` owner scope 查询和覆盖写入。
- `artifact_file` 按 `task_id`、`user_id` 查询，并按 `task_id`、`user_id`、`artifact_type`、`language` owner scope 覆盖写入。
- `ai_call_record` 按 `task_id`、`user_id` 查询当前用户当前任务调用记录，并按 `created_at`、`id` 稳定排序。

B1 已明确索引名称和 Flyway 文件名；B1 之外的表将在对应 TODO 任务中补充最终索引和迁移文件。

## task_full_text_result

LONG-6 adds `task_full_text_result` with migration `V10__create_task_full_text_result_table.sql`.

Columns:

- `id BIGINT AUTO_INCREMENT PRIMARY KEY`
- `task_id VARCHAR(64) NOT NULL`
- `user_id BIGINT NOT NULL`
- `source_language VARCHAR(32) NOT NULL`
- `target_language VARCHAR(32) NOT NULL`
- `source_full_text LONGTEXT NOT NULL`
- `translated_full_text LONGTEXT`
- `provider VARCHAR(64)`
- `created_at DATETIME NOT NULL`
- `updated_at DATETIME NOT NULL`

Indexes:

- Unique key `uk_task_full_text_task_user_lang (task_id, user_id, target_language)`.
- Index `idx_task_full_text_task_user (task_id, user_id)`.

The table stores sanitized source/translated full text for the current owner-scoped task result. It does not store raw prompts, raw responses, object keys, local paths, or secrets.
## video_keyframe

`video_keyframe` stores low-cost VISION-R1 keyframe candidates for an analysis task. It is an internal metadata table backed by `StorageService` / MinIO thumbnails. Public API responses never expose `object_key`.

Migration `V11__create_video_keyframe_table.sql` uses `CREATE TABLE IF NOT EXISTS video_keyframe`. This keeps the migration safe for a server where the table was created manually before Flyway history was updated; Flyway can still execute and record V11 without dropping or duplicating keyframe data.

| Field | Type | Description |
| --- | --- | --- |
| id | BIGINT | Primary key, auto increment. |
| task_id | VARCHAR(64) | Owner analysis task id. |
| user_id | BIGINT | Owner user id for owner-scope queries. |
| frame_index | INT | Extracted thumbnail frame index. |
| timestamp_millis | BIGINT | Video timestamp in milliseconds. |
| time_text | VARCHAR(32) | Display timestamp. |
| change_score | DECIMAL(10,6) | Normalized frame change score. |
| select_reason | VARCHAR(32) | `FIRST_FRAME`, `PERIODIC_ANCHOR`, `SCENE_CHANGE`, or `CONTENT_CHANGE`. |
| content_type | VARCHAR(128) | Thumbnail MIME type, currently `image/jpeg`. |
| storage_backend | VARCHAR(32) | Storage backend name, currently `MINIO`. |
| object_key | VARCHAR(512) | Internal storage object key. Never returned by API. |
| size_bytes | BIGINT | Thumbnail object size. |
| created_at | DATETIME(3) | Creation time. |
| updated_at | DATETIME(3) | Update time. |

Indexes and constraints:

- Primary key: `PRIMARY KEY (id)`.
- Idempotency guard: `uk_video_keyframe_task_frame (task_id, frame_index)`.
- Query indexes: `idx_video_keyframe_task_time (task_id, timestamp_millis)` and `idx_video_keyframe_user_task_time (user_id, task_id, timestamp_millis)`.

## video_keyframe_ocr

`video_keyframe_ocr` stores OCR-R1 text recognition metadata for keyframes. It is keyed by `keyframe_id`, scoped by `task_id + user_id`, and stores only safe OCR metadata. It does not store object keys, local filesystem paths, tokens, API keys, raw provider stderr, raw prompts, raw responses, VLM output, image summaries, embeddings, or course QA data.

Migration `V12__create_video_keyframe_ocr_table.sql` uses `CREATE TABLE IF NOT EXISTS video_keyframe_ocr`. The server migration script verifies successful V12 in `flyway_schema_history` and verifies that `video_keyframe_ocr` exists before backend restart.

| Column | Type | Notes |
| --- | --- | --- |
| id | BIGINT | Auto-increment primary key. |
| task_id | VARCHAR(64) | Analysis task id. |
| user_id | BIGINT | Owner user id for scoped queries. |
| keyframe_id | BIGINT | Referenced `video_keyframe.id`. |
| timestamp_millis | BIGINT | Copied keyframe timestamp for ordered reads. |
| provider | VARCHAR(64) | Safe provider label, default `tesseract`. |
| language_hint | VARCHAR(64) | OCR language hint, for example `chi_sim+eng`. |
| ocr_text | TEXT | Recognized text, truncated by `COURSELINGO_VISION_OCR_MAX_TEXT_LENGTH`. |
| text_length | INT | Original recognized text length before truncation. |
| text_truncated | TINYINT(1) | Whether `ocr_text` was truncated. |
| confidence | DECIMAL(5,4) | Optional normalized OCR confidence. |
| status | VARCHAR(32) | `SUCCEEDED`, `EMPTY`, `FAILED`, or `SKIPPED`. |
| error_code | VARCHAR(64) | Safe internal error code. |
| error_message | VARCHAR(255) | Sanitized message safe for logs; API returns friendly text instead. |
| duration_millis | BIGINT | OCR call duration. |
| created_at | DATETIME | Creation time. |
| updated_at | DATETIME | Update time. |

- Idempotency guard: `uk_video_keyframe_ocr_keyframe (keyframe_id)`.
- Query index: `idx_video_keyframe_ocr_task_user_time (task_id, user_id, timestamp_millis)`.
- Foreign keys cascade from `video_keyframe`, `analysis_task`, and `user_account`.
- Foreign keys: `task_id -> analysis_task(id)`, `user_id -> user_account(id)`, both cascade on delete and restrict on update.
- Checks: non-negative `timestamp_millis` / `size_bytes`, and known `select_reason`.

## video_keyframe_analysis

`video_keyframe_analysis` stores VLM-R1 visual analysis metadata for selected high-value keyframes. It is keyed by `keyframe_id`, scoped by `task_id + user_id`, and stores only safe structured summaries. It does not store object keys, local filesystem paths, tokens, API keys, provider stderr, raw requests, raw responses, audio-visual fusion records, embeddings, or course QA data.

Migration `V13__create_video_keyframe_analysis.sql` uses `CREATE TABLE IF NOT EXISTS video_keyframe_analysis`. The server migration script verifies successful V13 in `flyway_schema_history` and verifies that `video_keyframe_analysis` exists before backend restart.

| Column | Type | Notes |
| --- | --- | --- |
| id | BIGINT | Auto-increment primary key. |
| task_id | VARCHAR(64) | Analysis task id. |
| user_id | BIGINT | Owner user id for scoped queries. |
| keyframe_id | BIGINT | Referenced `video_keyframe.id`. |
| timestamp_millis | BIGINT | Copied keyframe timestamp for ordered reads. |
| provider | VARCHAR(64) | Safe provider label, for example `openai-compatible-vision`. |
| model | VARCHAR(128) | Safe model label returned from routing configuration. |
| screen_type | VARCHAR(32) | `PPT`, `CODE`, `TERMINAL`, `WHITEBOARD`, `BROWSER`, or `OTHER`. |
| visual_summary | TEXT | Concise visual description. |
| detected_elements_json | JSON | Bounded list of visible UI/text/object elements. |
| status | VARCHAR(32) | `SUCCEEDED`, `EMPTY`, `FAILED`, or `SKIPPED`. |
| error_code | VARCHAR(64) | Safe internal error code. |
| error_message | VARCHAR(255) | Sanitized message safe for logs; API returns friendly text instead. |
| duration_millis | BIGINT | Provider call duration. |
| created_at | DATETIME | Creation time. |
| updated_at | DATETIME | Update time. |

- Idempotency guard: `uk_video_keyframe_analysis_keyframe (keyframe_id)`.
- Query index: `idx_video_keyframe_analysis_task_user_time (task_id, user_id, timestamp_millis)`.
- Foreign keys cascade from `video_keyframe`, `analysis_task`, and `user_account`.
- Public APIs expose a nested safe `visualAnalysis` view, not this table directly.

## video_segment

`video_segment` stores FUSION-R1 rule-based segment evidence generated from ASR subtitles, keyframe OCR rows, and existing visual-analysis summaries. It does not store object keys, local filesystem paths, tokens, API keys, raw prompts, raw responses, provider stderr, embeddings, or course QA data.

Migration `V14__create_video_segment.sql` uses `CREATE TABLE IF NOT EXISTS video_segment`. The server migration script verifies successful V14 in `flyway_schema_history` and verifies that `video_segment` exists before deployment continues.

| Column | Type | Notes |
| --- | --- | --- |
| id | BIGINT | Auto-increment primary key. |
| task_id | VARCHAR(64) | Analysis task id. |
| user_id | BIGINT | Owner user id for scoped queries. |
| segment_index | INT | Zero-based fused window index. |
| start_millis | BIGINT | Segment start timestamp. |
| end_millis | BIGINT | Segment end timestamp. |
| time_text | VARCHAR(64) | Display range such as `00:00:00 - 00:01:00`. |
| asr_text | TEXT | Bounded ASR evidence for the window. |
| ocr_text | TEXT | Bounded OCR evidence for matching keyframes. |
| visual_summary | TEXT | Bounded visual-analysis evidence when historical VLM rows exist. |
| fused_summary | TEXT | Rule-generated segment summary. |
| keywords_json | JSON | Rule-extracted keywords. |
| evidence_json | JSON | Safe evidence id lists and source counts. |
| confidence | DECIMAL(5,4) | Lightweight confidence score derived from evidence source count. |
| status | VARCHAR(32) | `SUCCEEDED`, `EMPTY`, `FAILED`, `SKIPPED`, or `DISABLED`. |
| created_at | DATETIME | Creation time. |
| updated_at | DATETIME | Update time. |

- Idempotency guard: the fusion service deletes old `task_id + user_id` rows before inserting regenerated segments, and `uk_video_segment_task_user_index (task_id, user_id, segment_index)` prevents duplicate windows.
- Query index: `idx_video_segment_task_user_time (task_id, user_id, start_millis)`.
- Foreign keys cascade from `analysis_task` and `user_account`.
- Public APIs expose safe `VideoSegmentResponse` rows only.

## course_qa_record

`course_qa_record` stores QA-R1 single-task, single-turn course QA results. It stores the user's trimmed question, the final Chinese answer, sanitized cited evidence JSON, safe provider/model metadata, token usage, duration, status, and sanitized error summaries. It does not store raw prompts, raw provider responses, object keys, local filesystem paths, API keys, tokens, JWT secrets, database passwords, embeddings, or vector-search payloads.

Migration `V15__create_course_qa_record.sql` uses `CREATE TABLE IF NOT EXISTS course_qa_record`.

| Column | Type | Notes |
| --- | --- | --- |
| id | BIGINT | Auto-increment primary key. |
| task_id | VARCHAR(64) | Analysis task id. |
| user_id | BIGINT | Owner user id for scoped queries. |
| question | VARCHAR(1000) | Trimmed user question. |
| answer | TEXT | Final answer or insufficient-evidence message. |
| evidence_json | JSON | Sanitized time-bounded evidence items. |
| status | VARCHAR(32) | `SUCCEEDED` or `FAILED`. |
| provider | VARCHAR(64) | Safe LLM provider label. |
| model | VARCHAR(128) | Safe model label. |
| prompt_tokens / completion_tokens / total_tokens | INT | Optional usage counters. |
| duration_millis | BIGINT | Optional provider-call duration. |
| error_code | VARCHAR(64) | Sanitized failure code. |
| error_message_summary | VARCHAR(512) | Sanitized failure summary. |
| created_at / updated_at | DATETIME(3) | Audit timestamps. |

Indexes:

- `idx_course_qa_task_user_created (task_id, user_id, created_at)`.
- `idx_course_qa_user_created (user_id, created_at)`.

Foreign keys cascade from `analysis_task` and `user_account`. Public APIs expose only `recordId`, answer, cited evidence, and safe usage metadata.

## course_chapter

`course_chapter` stores CHAPTER-R1 on-demand course chapter timeline rows. It stores only owner-scoped chapter metadata, sanitized evidence windows, safe provider/model metadata, token usage, duration, status, and sanitized error summaries. It does not store raw prompts, raw provider responses, object keys, local filesystem paths, API keys, tokens, JWT secrets, database passwords, OCR payloads, keyframe image data, embeddings, vector-search payloads, or Agent state.

Migration `V16__create_course_chapter.sql` uses `CREATE TABLE IF NOT EXISTS course_chapter`.

| Column | Type | Notes |
| --- | --- | --- |
| id | BIGINT | Auto-increment primary key. |
| task_id | VARCHAR(64) | Analysis task id. |
| user_id | BIGINT | Owner user id for scoped queries. |
| chapter_index | INT | Zero-based chapter order. |
| title | VARCHAR(255) | Chinese chapter title. |
| summary | TEXT | One-sentence Chinese chapter summary. |
| keywords_json | JSON | Bounded keyword list. |
| start_millis | BIGINT | Chapter start timestamp. |
| end_millis | BIGINT | Chapter end timestamp. |
| evidence_json | JSON | Sanitized ASR/subtitle time-window evidence items. |
| status | VARCHAR(32) | `SUCCEEDED` or `FAILED`. |
| provider | VARCHAR(64) | Safe LLM provider label. |
| model | VARCHAR(128) | Safe model label. |
| prompt_tokens / completion_tokens / total_tokens | INT | Optional usage counters. |
| duration_millis | BIGINT | Optional provider-call duration. |
| error_code | VARCHAR(64) | Sanitized failure code. |
| error_message_summary | VARCHAR(512) | Sanitized failure summary. |
| created_at / updated_at | DATETIME(3) | Audit timestamps. |

Indexes:

- `uk_course_chapter_task_user_index (task_id, user_id, chapter_index)` prevents duplicate chapter order for the same owner task.
- `idx_course_chapter_user_task (user_id, task_id)` supports owner-scoped task reads.
- `idx_course_chapter_user_created (user_id, created_at)` supports user history diagnostics.

Foreign keys cascade from `analysis_task` and `user_account`. Successful regeneration deletes and reinserts only rows for the same `task_id + user_id`; failed generation preserves existing successful chapters.

## course_video_chunk

`course_video_chunk` stores VIDEO-CONTEXT-R1 fixed-window backend context chunks for an analysis task. It is a rule-built index over stable text facts. It does not store raw prompts, raw provider responses, object keys, local filesystem paths, API keys, tokens, JWT secrets, database passwords, OCR payloads, keyframe image data, VLM output, embeddings, vector-search payloads, Agent state, or QA history.

Migration `V17__create_course_video_chunk.sql` uses `CREATE TABLE IF NOT EXISTS course_video_chunk`.

| Column | Type | Notes |
| --- | --- | --- |
| id | BIGINT | Auto-increment primary key. |
| task_id | VARCHAR(64) | Analysis task id. |
| user_id | BIGINT | Owner user id for scoped queries. |
| target_language | VARCHAR(32) | Task target language. |
| chunk_index | INT | Zero-based fixed-window chunk index. |
| start_millis | BIGINT | Chunk start timestamp. |
| end_millis | BIGINT | Chunk end timestamp. |
| time_text | VARCHAR(64) | Display range such as `00:00:00 - 00:04:00`. |
| summary | TEXT | Rule-generated summary. No LLM call is used in R1. |
| keywords_json | JSON | Bounded rule-extracted keyword array. |
| evidence_json | JSON | Sanitized subtitle evidence references. |
| source_text_preview | TEXT | Bounded source subtitle preview plus `video_segment.asr_text` supplement. |
| translated_text_preview | TEXT | Bounded translated subtitle preview. |
| build_version | VARCHAR(32) | `VIDEO_CONTEXT_R1`. |
| created_at / updated_at | DATETIME(3) | Audit timestamps. |

Indexes:

- `uk_course_video_chunk_task_user_lang_index (task_id, user_id, target_language, chunk_index)` prevents duplicate chunks for the same owner task/language.
- `idx_course_video_chunk_task_user_time (task_id, user_id, start_millis)` supports owner-scoped time reads.
- `idx_course_video_chunk_user_created (user_id, created_at)` supports owner diagnostics.

Foreign keys cascade from `analysis_task` and `user_account`. Successful rebuild deletes and reinserts only rows for the same `task_id + user_id + target_language`; build failure preserves existing chunks.
