# LectureLens Architecture Design

## Public local Demo profile

The public local Demo keeps the same upload, RocketMQ dispatch, bounded Analysis Runner, FFmpeg, persistence, result, and artifact boundaries as the normal asynchronous pipeline. It changes only the explicitly configured AI provider implementations: `MockAsrProvider` returns a deterministic local transcript and `DemoMockLlmProvider` returns deterministic aligned translations and a structured learning package. Both are disabled by default, perform no external network call, and do not replace a configured real `LlmProvider`.

`.env.demo.example` enables the Demo providers and disables SiliconFlow, OpenAI-compatible, LangChain4j, OCR, and visual-analysis providers. `.env.real-ai.example` disables the Demo providers and requires the user to supply local credentials. A startup guard rejects any mixed Demo/real ASR or LLM configuration. The task-detail UI reads only the safe backend field from `/api/public/runtime-configuration`; it never derives the Demo notice from a browser-controlled value.

The Demo Compose runtime validates `LECTURELENS_DEMO_INSTANCE` against `^[a-z0-9-]{1,32}$`, derives the project name as `lecturelens-demo-<instance>`, and uses Compose-scoped volumes, so Demo instances cannot share MySQL, Redis, MinIO, or RocketMQ state. The Demo environment maps nonstandard host ports while containers retain their normal internal ports, except RocketMQ proxy whose internal gRPC listener is deliberately set to the selected host port: RocketMQ 5.x clients receive that port in proxy route metadata. The standard default remains `8081`. Stopping a Demo runs `down` without `-v`; data deletion is an explicit manual action.

## 最终技术栈

- 后端：Java 21 + Spring Boot 3.5.15 + Maven Wrapper 3.9.x
- ORM：MyBatis-Plus 3.5.16
- 数据库：MySQL 8.4 LTS
- 数据库迁移：Flyway，由 Spring Boot BOM 管理版本
- 缓存/短状态/限流：Redis 8.8.0
- 对象存储：MinIO 固定 RELEASE tag
- 媒体处理：FFmpeg 8.0.3
- 消息队列：RocketMQ 5.3.4
- AI 编排：LangChain4j，使用 langchain4j-bom 固定版本
- ASR：SiliconFlow-compatible ASR Provider
- LLM：OpenAI-compatible LLM Provider
- 实时进度：SSE
- 前端：Node.js 24 LTS + Vue 3.5.x + Vite 8.x + TypeScript 5.9.x + Pinia 3.x + Element Plus 2.14.x + Axios 固定安全版本
- 部署：Docker Compose
- CI：GitHub Actions + Dependabot
- 架构：单体应用 + RocketMQ 异步任务队列 + package-by-domain

## 单体架构原则

- 使用单体后端应用承载认证、上传、任务、AI Pipeline、制品和设置接口。
- 使用 package-by-domain 组织后端代码，避免按 Controller / Service / Mapper 横向堆叠。
- HTTP 请求线程只处理短事务，不执行 FFmpeg / ASR / LLM 长任务。
- RocketMQ 作为分析任务异步边界。
- MySQL 是事实来源，Redis 是短状态组件。

## package-by-domain 后端目录

```text
backend/src/main/java/com/example/courselingo/
├── auth
├── upload
├── storage
├── task
├── mq
├── dispatch
├── pipeline
├── media
├── ai
├── subtitle
├── learning
├── artifact
├── common
└── infrastructure
```

## Vue 前端目录

```text
frontend/src/
├── api
├── assets
├── components
├── layouts
├── router
├── stores
├── views
│   ├── auth
│   ├── dashboard
│   ├── upload
│   ├── task
│   ├── result
│   └── settings
├── types
└── utils
```

前端用户体验约束：

- 注册和登录页先做字段级校验，再调用后端认证接口，避免普通用户只看到泛化认证失败。
- API 错误通过统一前端映射转换为中文提示；普通页面不展示原始英文异常、堆栈、access token、`objectKey`、本地路径或密钥类字段。
- 上传页保留分片上传、进度、暂停/继续、原视频预览和原视频自带字幕能力，同时用三步说明帮助用户理解“上传、确认、创建 AI 分析任务”的流程。
- 任务列表页基于现有任务查询接口展示中文状态、进度、阶段、目标语言、创建时间、最近更新和脱敏失败原因，并在前端本地提供全部、进行中、已完成、失败和已取消筛选；失败或取消任务的重新分析入口复用既有 retry API。
- 任务详情页保留专业结果和调试信息，但对课程原视频、全文阅读、时间轴分段、学习笔记和调试信息增加普通用户可理解的说明。

## 上传生命周期状态机

- `CREATED`：上传会话已创建。
- `UPLOADING`：分片上传中。
- `MERGING`：服务端合并分片中。
- `STORED`：新上传的正式完成状态，原始文件已经持久化到 MinIO；本地 assembled 文件仅作为受控缓存。
- `UPLOADED`：仅表示升级前遗留的本地 assembled 上传，用于兼容历史任务，不计入正式 MinIO 引用。
- `FAILED`：上传或合并失败。
- `CANCELLED`：上传被取消。

## 分析任务生命周期状态机

- `CREATED`：任务记录已创建。
- `QUEUED`：任务已准备进入异步队列。
- `CLAIMED`：Consumer 已领取任务。
- `EXTRACTING_AUDIO`：FFmpeg 提取音频中。
- `TRANSCRIBING`：ASR 转写中。
- `TRANSLATING`：LLM 字幕翻译中。
- `GENERATING_LEARNING_PACKAGE`：生成摘要、重点、Q&A、术语表中。
- `GENERATING_ARTIFACTS`：生成 SRT/VTT/Markdown/JSON 中。
- `SUCCEEDED`：任务成功。
- `FAILED`：任务失败。
- `RETRYING`：任务等待重试。
- `CANCELLED`：任务取消。

C13 任务控制接口补充重新分析入口和取消入口。HTTP `POST /api/tasks/{taskId}/retry` 不重置原任务，而是只允许 `FAILED` / `CANCELED` 任务基于原 `uploadId` 和 `targetLanguage` 创建一个新的分析任务；原失败或取消任务保留历史状态、错误信息、日志和 AI 调用记录。`SUCCEEDED` 不允许重新分析，`CREATED` / `QUEUED` / `RUNNING` / `RETRYING` 等处理中状态不允许重复分析。取消入口允许 `CREATED` / `QUEUED` / `RUNNING` / `RETRYING` 进入 `CANCELED`，`SUCCEEDED`、`FAILED`、`CANCELED` 等终态不允许取消。

## RocketMQ 异步任务链路

1. HTTP 创建任务接口校验上传归属和状态。
2. 后端调用 C10 任务创建限流组件。
3. 后端写入 `analysis_task`，初始状态为 `CREATED`。
4. 后端通过 C2 状态服务推进到 `QUEUED`，写入 `task_log` 并刷新 C8 进度快照。
5. 后端发送 Topic `courselingo-analysis-task` 消息，Tag 为 `ANALYSIS_CREATED`。
6. Consumer 使用 `taskId` 做幂等领取。
7. Consumer 执行 FFmpeg、ASR、LLM、LangChain4j 和制品生成。
8. Consumer 写入 MySQL 事实数据，并更新 Redis 进度快照。
9. SSE 接口读取任务状态和进度快照向前端推送。

本地 E2E 或人工重跑可能留下旧 RocketMQ 消息。Consumer 对已不存在的任务或当前 MySQL 状态不再允许执行的任务消息视为 stale / dirty message，记录 warn 后 ack/drop，避免 RocketMQ 对非重试业务错误无限重投；执行器繁忙、外部 provider timeout、数据库短暂失败等可恢复异常仍返回消费失败并交给 RocketMQ 重试。

C14 创建任务 HTTP 接口只做任务创建：鉴权、`uploadId + userId` owner scope 校验、`STORED` 正式上传或 legacy `UPLOADED` 状态校验、C10 限流、MySQL 任务插入、C2 状态推进和 `ANALYSIS_CREATED` RocketMQ 消息发送。它不直接调用 Runner，不在 HTTP 请求线程内执行 FFmpeg / ASR / LLM / LangChain4j，不生成字幕、学习包或制品。当前策略不是生产级分布式事务消息：MySQL 任务插入和状态推进先于 MQ 发送，MQ 发送失败时返回项目异常并写入 WARN 任务日志，不假装成功。

C13 retry / cancel HTTP 接口只做任务控制。retry 鉴权并按 `taskId + user_id` 校验原任务归属后，复用创建任务服务创建新任务并投递 `ANALYSIS_CREATED`，不修改原任务；cancel 鉴权、校验状态后通过状态服务推进到 `CANCELED` 并发送 `ANALYSIS_CANCEL`。它们不直接调用 Runner，不在 HTTP 请求线程内执行 FFmpeg / ASR / LLM / LangChain4j，不生成字幕、学习包或制品。retry 选择新建任务而不是重置原任务，是为了保留失败历史、日志和 `ai_call_record`，并避免状态机回滚带来的脏状态。

C15 任务列表 / 详情 HTTP 接口只做查询：鉴权后按当前 `user_id` 过滤 MySQL `analysis_task`，列表固定按 `created_at DESC` 排序，详情按 `taskId + user_id` 查询。查询接口不读取客户端 owner 字段，不接受任意排序字段，不发送 RocketMQ 消息，不调用 Runner，不执行 FFmpeg / ASR / LLM / LangChain4j，不生成字幕、学习包或制品。

PRODUCT-POLISH-R1 增加 owner-scoped 批量逻辑删除。`POST /api/tasks/batch-delete` 先规范化并去重最多 100 个任务 ID，再一次查询当前用户任务（该专用查询显式允许读取已删除记录以保证幂等）。只要存在缺失/非本人任务就整体返回 `TASK_NOT_FOUND`；只要任一未删除任务不是 `SUCCEEDED`、`FAILED`、`CANCELED` 就整体返回 `TASK_DELETE_NOT_ALLOWED`。通过 `@Transactional` 和一次带 `user_id + id IN (...) + deleted_at IS NULL + status IN (...)` 条件的 UPDATE 同时设置 `deleted_at`、`updated_at`；更新计数异常会抛错并回滚，禁止部分成功。

普通 `selectByIdAndUserId`、列表、总数和用户命令更新均显式追加 `deleted_at IS NULL`，因此结果、播放令牌、内嵌字幕、artifact、关键帧、章节、QA、Video Segment、视频上下文和 SSE 复用同一 owner guard 后都将已删除任务视为不存在。运行中状态不可删除，所以 Runner/Pipeline 不会因用户删除而中断；历史关联表、MinIO 对象、Redis 限流和审计记录都不删除、不重置、不绕过。

TASK-LIST-UX-R1 只增强前端任务列表体验，不改变 C15 查询接口语义。列表页拉取当前用户任务后在前端按状态分组筛选，使用统一状态工具把 `CREATED` / `QUEUED` / `RUNNING` / `RETRYING` 归为进行中，把 `SUCCEEDED`、`FAILED`、`CANCELED` / `CANCELLED` 分别归为已完成、失败、已取消；列表页的重新分析按钮仍调用 C13 retry API，后端继续创建新任务而不是重置原任务。

RESULT-UX-R1 只增强前端任务详情结果页体验，不改变 D16 结果查询接口、artifact 下载接口、任务状态机、视频播放或原视频自带字幕逻辑。任务详情页复用 `GET /api/tasks/{taskId}`、`GET /api/tasks/{taskId}/results` 和 artifact 下载接口，在前端展示“本次分析结果”总览、全文阅读复制、时间轴关键词搜索、学习笔记空态、导出文件说明和失败任务重新分析引导；下载 artifact 时继续使用鉴权 API，不在 URL、日志或页面中暴露 `objectKey`、本地路径、token 或密钥。

## Redis 用途

- `cl:u:chunks:{uploadId}`：上传分片状态 Set。
- `cl:t:progress:{taskId}`：任务进度快照。
- `cl:t:claim:{taskId}`：防重复分析领取锁。
- `cl:rate:analysis:{userId}`：任务创建限流。
- Redis 数据必须设置 TTL。
- Redis 不是最终事实来源。

## MinIO 存储设计

- 保存原始视频文件。
- 保存 FFmpeg 生成的音频中间文件。
- 保存字幕文件。
- 保存学习包文件。
- bucket 禁止公开读写。
- 对象路径由服务端生成，不使用用户原始文件名作为真实路径。

## FFmpeg 调用边界

- D1 提供独立 `FfmpegAudioExtractor` media 组件；F2 在显式启用 pipeline executor 时由 `ExtractAudioStep` 调用该组件。
- D1 不调用 ASR / LLM / LangChain4j，不生成字幕、学习包或制品。
- F2 接入后，FFmpeg 只在异步任务执行器中调用；HTTP 请求线程不得直接执行 FFmpeg。
- HTTP 请求线程不得直接执行 FFmpeg。
- 输入文件必须来自服务端确认的 MinIO 对象或受控临时文件。
- `FfmpegAudioExtractor` 通过配置读取 ffmpeg 可执行文件、音频格式、采样率、声道数和超时时间。
- `FfmpegAudioExtractor` 使用 `ProcessBuilder` 参数数组调用 ffmpeg，不拼接 shell 字符串；调用过程读取 stdout/stderr，超时销毁进程。
- `FfmpegAudioExtractor` 校验输入文件存在且为普通文件，输出目录可创建，输出文件路径必须位于指定输出目录下。
- F2 复用 `FfmpegAudioExtractor` 的超时、退出码和 stderr 脱敏边界；Runner 失败路径会将任务推进到 `FAILED` 并保存脱敏错误摘要。

## ASR Provider 抽象

- `SpeechToTextProvider` 负责屏蔽 SiliconFlow-compatible ASR 细节。
- D2 仅定义 ASR Provider 抽象、请求 / 结果 / 转写片段模型和基础校验，不实现真实外部 ASR Provider。
- Provider 输入为服务端生成的音频文件路径、语言、请求 ID、任务 ID 和超时时间。
- Provider 输出为转写全文、带时间戳的转写片段、耗时、音频时长和脱敏后的元数据。
- D2 不接入 Runner，不调用 SiliconFlow、LLM 或 LangChain4j，不写入数据库、RocketMQ、字幕表、学习包或制品。
- D3 提供 `SiliconFlowAsrProvider` 和 JDK `HttpClient` 客户端实现，固定调用 `POST /v1/audio/transcriptions`，使用 `multipart/form-data` 上传 `file` 和 `model` 字段，并通过 `Authorization: Bearer <API_KEY>` 鉴权。
- SiliconFlow ASR Provider 默认通过 `courselingo.ai.asr.silicon-flow.enabled=false` 禁用；启用前必须通过环境变量配置 API key、base URL、模型、超时和最大音频大小。
- D3 不接入 Runner，不调用 LLM 或 LangChain4j，不写入数据库、RocketMQ、字幕表、学习包或制品；测试使用 fake client，不真实请求 SiliconFlow。
- D4 提供 `MockAsrProvider`，通过 `courselingo.ai.asr.mock.enabled=false` 默认禁用，仅在显式启用后注册本地 mock provider bean。它复用 D2 请求校验，返回确定性的 `mock` provider 结果、单段转写和脱敏 metadata，不读取 API key，不发起网络请求，不依赖 SiliconFlow 配置。
- D4 不接入 Runner，不调用真实外部 ASR、LLM 或 LangChain4j，不写入数据库、RocketMQ、字幕表、学习包或制品。
- F3 在显式启用 pipeline executor 时由 `TranscribeAudioStep` 调用注入的 `SpeechToTextProvider`，输入来自 F2 的内部音频文件引用，ASR 结果只保存在 pipeline context 中供字幕持久化步骤使用。
- F3 测试使用 fake / mock provider，不真实请求 SiliconFlow 或任何外部 ASR；异常和 context `toString` 不暴露音频路径、`objectKey`、token、secret 或 API key，也不记录字幕全文。
- F4 在显式启用 pipeline executor 时由 `TranslateSubtitleSegmentsStep` 和 `GenerateLearningPackageStep` 复用 D8 / D9 服务，服务内部通过注入的 `LlmProvider` 抽象生成字幕翻译和学习包，并按 owner scope 覆盖保存。
- F4 测试使用 fake / mock LLM，不真实请求 OpenAI-compatible API、LangChain4j 外部模型或任何外部 LLM；异常和 context `toString` 不暴露 `objectKey`、本地路径、token、secret 或 API key，也不记录字幕全文、翻译全文或学习包全文。
- F5 在显式启用 pipeline executor 时由 `GenerateArtifactsStep` 复用 D11-D14 的 SRT/VTT/Markdown/JSON 制品服务，并通过 D10 `ArtifactFileService` 与 `StorageService` 覆盖写入 `artifact_file` 元数据和制品内容。
- F6 在显式启用 pipeline executor 时由 `WriteAiCallRecordStep` 复用 D15 `AiCallRecordService`，把 ASR、字幕翻译和学习包生成步骤产生的成功 / 失败调用摘要写入 `ai_call_record`。该步骤只保存 provider、model、callType、stage、status、耗时、token usage、输入/输出抽象计量、fingerprint 和脱敏错误摘要等安全元数据；不保存 raw prompt、raw response、secret、token、`objectKey`、本地路径、字幕全文或学习包全文。

## LLM Provider 抽象

- OpenAI-compatible LLM Provider 负责字幕翻译和结构化内容生成请求。
- Provider 不直接处理 HTTP Controller。
- Provider 的调用结果必须经过领域服务校验后再持久化。
- D5 提供 `LlmProvider` 抽象、请求 / 结果 / 消息 / usage 模型、请求校验、脱敏异常，以及默认禁用的 `OpenAiCompatibleLlmProvider`。
- D5 的 OpenAI-compatible provider 通过 `courselingo.ai.llm.openai-compatible.*` 配置读取 base URL、API key、模型、超时、temperature 和 max tokens，固定调用 `POST /v1/chat/completions`，使用 JSON 请求体和 `Authorization: Bearer <API_KEY>` 鉴权。
- MODEL-R1 新增 `courselingo.ai.model-routing.*` Profile / Stage Router 底座。当前活跃阶段只有 `TRANSLATION_FULL_TEXT`、`SUBTITLE_TRANSLATION` 和 `LEARNING_PACKAGE`，默认路由到 `deepseek-text` profile，复用服务器侧 `OPENAI_COMPATIBLE_*` 环境变量。Router 在启动时校验 active route、profile、enabled 状态和 `TEXT_CHAT` / `JSON_OUTPUT` 能力，缺失时 fail fast；`model-routing.enabled=false` 时保持旧 OpenAI-compatible 配置路径兼容。
- MODEL-R1 开启时，D8 字幕分段翻译、D8 全文翻译和 D9 学习包生成会在调用 `LlmProvider` 前把 stage route 应用到 `LlmRequest`：覆盖 timeout、temperature、max tokens、max attempts，并把 profile code、provider type、model name 和 base URL 写入安全 metadata。OpenAI-compatible provider 只从该安全 metadata 读取 model/base URL 覆盖值，API key 仍只来自服务器环境变量，不进入 request metadata、日志、前端响应或 artifact。
- MODEL-R1 本身不新增数据库表、MQ topic、业务 API 或前端 UI；它只提供 stage/profile 路由底座。VLM-R1 后续接入了 `VISION_FRAME_ANALYSIS`，但该阶段仍由 `COURSELINGO_VISION_ANALYSIS_ENABLED=false` 默认关闭。`VISION_OCR`、`FUSION_SUMMARY`、`COURSE_QA`、`EMBEDDING` 仍作为后续阶段枚举和文档边界保留。
- D5 不接入 LangChain4j，不直接读取或写入字幕表，不写入数据库、RocketMQ、学习包或制品；F4 仅通过 D8 / D9 服务注入的 `LlmProvider` 抽象间接使用已显式启用的 provider。测试使用 fake client / stub transport，不真实请求 OpenAI 或中转站。
- D6 提供默认禁用的 `LangChain4jLlmProvider`，实现同一个 `LlmProvider` 抽象，并通过 `courselingo.ai.llm.langchain4j.*` 配置读取 base URL、API key、模型、连接超时、请求超时、temperature 和 max tokens。
- D6 的 LangChain4j provider 使用 LangChain4j 1.17.0 的 `ChatModel` / `ChatRequest` / `ChatResponse` API，真实 OpenAI-compatible 调用隔离在 `LangChain4jChatModelClient` 内；单元测试只使用 fake client，不真实请求 OpenAI、中转站或任何外部 LLM。
- D6 只接入 LangChain4j provider 边界，不替换 D5 provider，不直接读取或写入字幕表，不写入数据库、RocketMQ、学习包或制品，不生成摘要、翻译、Q&A、术语表、学习包或 artifact；F4 仅通过 D8 / D9 服务注入的 `LlmProvider` 抽象间接使用已显式启用的 provider。

## 字幕转写持久化边界

- D7 创建 `subtitle_segment` 表，保存 ASR 转写片段的 `task_id`、`user_id`、`segment_index`、`start_millis`、`end_millis`、`language`、`text`、安全 provider 名称和时间戳。
- `SubtitleSegmentPersistenceService` 复用 D2 的 `SpeechToTextResult` / `TranscribedSegment` 模型，将 ASR 结果转换为数据库字幕片段。
- 覆盖保存以 `taskId + userId` 为 owner scope，在事务内先删除当前用户当前任务的旧片段，再插入新片段；失败时由事务回滚避免半成品。
- `SubtitleSegmentQueryService` 只按 `taskId + userId` 查询当前用户片段，并按 `segment_index ASC` 返回不包含 `userId` 的 view。
- D7 不调用 FFmpeg，不调用 ASR Provider / SiliconFlow / mock ASR，不调用 LLM / LangChain4j，不接入 Runner，不发送 RocketMQ，不生成字幕翻译、摘要、Q&A、术语表、学习包或制品，不写入 `artifact_file` 或 `ai_call_record`。
- F3 在显式 pipeline 中由 `PersistSubtitleSegmentsStep` 先通过 `AnalysisTaskMapper.selectByIdAndUserId` 校验任务 owner scope，再调用 `SubtitleSegmentPersistenceService.saveTranscriptionResult` 覆盖保存 ASR 片段，重复执行不会追加重复字幕。
- F3 持久化失败会让 pipeline step 抛错，由 Runner 将任务推进到 `FAILED` 并保存脱敏错误摘要。

## 字幕翻译持久化边界

- D8 创建 `subtitle_translation_segment` 表，保存目标语言字幕片段的 `task_id`、`user_id`、`segment_index`、`start_millis`、`end_millis`、`source_language`、`target_language`、`translated_text`、安全 provider 名称和时间戳。
- `SubtitleTranslationService` 只从 D7 `subtitle_segment` 读取当前 `taskId + userId` 的源字幕，构造严格 JSON 输出要求的 `LlmRequest`，调用注入的 `LlmProvider` 抽象，解析并校验 `{segments:[{index,text}]}`。
- 覆盖保存按 `taskId + userId + targetLanguage` 执行，删除旧翻译和插入新翻译在同一事务内完成；不会删除其他 `userId` 或其他 `targetLanguage` 的数据。
- `SubtitleTranslationQueryService` 按 `taskId + userId + targetLanguage` 查询翻译结果，固定按 `segment_index ASC` 返回不包含 `userId` 的 view。
- D8 测试只使用 fake `LlmProvider`。D8 服务已在 F4 显式 pipeline 中由 `TranslateSubtitleSegmentsStep` 调用；该步骤不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 真实外部 LLM，不发送 RocketMQ，不生成摘要、Q&A、术语表、学习包或制品，不写入 `artifact_file` 或 `ai_call_record`，不新增 API。

## 学习包结构化输出边界

- D9 创建 `learning_package` 表，保存结构化学习包的 `task_id`、`user_id`、`source_language`、`target_language`、`title`、`summary`、`key_points_json`、`glossary_json`、`qa_json`、安全 provider 名称、schema version 和时间戳。
- `LearningPackageService` 只读取当前 `taskId + userId` 的 D7 源字幕，以及当前 `taskId + userId + targetLanguage` 的 D8 翻译字幕，构造严格 JSON 输出要求的 `LlmRequest`，调用注入的 `LlmProvider` 抽象，解析并校验 `{title,summary,keyPoints,glossary,qa}`。
- 覆盖保存按 `taskId + userId + targetLanguage` 执行，删除旧学习包和插入新学习包在同一事务内完成；不会删除其他 `userId` 或其他 `targetLanguage` 的数据。
- `LearningPackageQueryService` 按 `taskId + userId + targetLanguage` 查询学习包，返回不包含 `userId` 的 view。
- D9 测试只使用 fake `LlmProvider`。D9 服务已在 F4 显式 pipeline 中由 `GenerateLearningPackageStep` 调用；该步骤不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 真实外部 LLM，不发送 RocketMQ，不生成 SRT/VTT/Markdown/JSON 文件或制品，不写入 `artifact_file` 或 `ai_call_record`，不新增 API。

## 制品文件写入边界

- D10 创建 `artifact_file` 表，保存制品元数据的 `task_id`、`user_id`、`artifact_type`、`language`、`file_name`、`content_type`、`storage_backend`、后端内部 `object_key`、`size_bytes`、`sha256` 和时间戳。
- `ArtifactFileService` 接收后续 D11-D14 生成好的内容字节，生成后端内部 object key，使用现有 `StorageService` 写入对象，再按 `taskId + userId + artifactType + language` 覆盖保存元数据。
- 覆盖保存和元数据写入在事务内完成；如果 storage 写入失败，不写 DB；如果 DB 写入失败，会尽量删除刚写入的新对象；旧对象删除失败不阻断新元数据指向新对象。
- `ArtifactFileQueryService` 按 `taskId + userId` 或 `taskId + userId + artifactType + language` 查询，返回不包含 `userId` 和 `objectKey` 的 view。
- D10 测试只使用 fake `StorageService`，不真实连接 MinIO。D10 不生成 SRT/VTT/Markdown/JSON 具体内容，不读取字幕表或学习包表，不接入 Runner，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 或外部 LLM，不发送 RocketMQ，不新增 API，不写入 `ai_call_record`。

## SRT 制品生成边界

- D11 提供 `SrtArtifactService` 和 `SrtFormatter`，从 D8 已保存的翻译字幕中按 `taskId + userId + targetLanguage` 查询当前 owner scope 数据，并生成 UTF-8 SRT 内容。
- SRT cue 固定使用 1-based 连续序号、`HH:mm:ss,SSS` 时间格式、`-->` 分隔符和空行分隔；生成前校验时间范围和非空文本，清理控制字符并拒绝包含 token、secret、API key、Authorization header 或本地路径的文本。
- D11 只通过 D10 `ArtifactFileService.saveArtifactFile` 保存制品，`artifactType` 固定为 `SRT`，`contentType` 固定为 `application/x-subrip`，文件名由后端生成且不包含路径片段。
- D11 不直接调用 `StorageService` 或 `ArtifactFileMapper`，不新增数据库表或字段，不修改 `artifact_file`、`subtitle_segment`、`subtitle_translation_segment` 或 `learning_package` 表结构。
- D11 不生成 VTT/Markdown/JSON，不接入 Runner，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 或外部 LLM，不真实连接 MinIO，不发送 RocketMQ，不新增 API，不写入 `ai_call_record`。

## VTT 制品生成边界

- D12 提供 `VttArtifactService` 和 `VttFormatter`，从 D8 已保存的翻译字幕中按 `taskId + userId + targetLanguage` 查询当前 owner scope 数据，并生成 UTF-8 WebVTT 内容。
- WebVTT 内容固定以 `WEBVTT` header 开头，cue 使用 `HH:mm:ss.SSS` 时间格式、`-->` 分隔符和空行分隔，不生成 SRT 序号；生成前校验时间范围和非空文本，清理控制字符，避免字幕文本中的 `-->` 破坏 cue 结构，并拒绝包含 token、secret、API key、Authorization header 或本地路径的文本。
- D12 只通过 D10 `ArtifactFileService.saveArtifactFile` 保存制品，`artifactType` 固定为 `VTT`，`contentType` 固定为 `text/vtt; charset=utf-8`，文件名由后端生成且不包含路径片段。
- D12 不直接调用 `StorageService` 或 `ArtifactFileMapper`，不新增数据库表或字段，不修改 `artifact_file`、`subtitle_segment`、`subtitle_translation_segment` 或 `learning_package` 表结构。
- D12 不生成 Markdown/JSON，不接入 Runner，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 或外部 LLM，不真实连接 MinIO，不发送 RocketMQ，不新增 API，不写入 `ai_call_record`。

## Markdown 制品生成边界

- D13 提供 `MarkdownArtifactService` 和 `MarkdownLearningPackageFormatter`，从 D9 已保存的学习包中按 `taskId + userId + targetLanguage` 查询当前 owner scope 数据，并生成 UTF-8 Markdown 学习包内容。
- Markdown 内容固定包含一级标题、`## 摘要`、`## 重点`、`## 术语表` 和 `## 问答`；重点使用有序列表，术语表使用 Markdown table，问答使用稳定的 `Qn` 小标题；空 glossary / qa 输出稳定空状态文本。
- D13 生成前会清理控制字符，校验标题、摘要、重点、术语和问答文本，转义表格中的 `|`，并拒绝包含 token、secret、API key、Authorization header 或本地路径的内容。
- D13 只通过 D10 `ArtifactFileService.saveArtifactFile` 保存制品，`artifactType` 固定为 `MARKDOWN`，`contentType` 固定为 `text/markdown; charset=utf-8`，文件名由后端生成且不包含路径片段。
- D13 不直接调用 `StorageService` 或 `ArtifactFileMapper`，不新增数据库表或字段，不修改 `artifact_file`、`subtitle_segment`、`subtitle_translation_segment` 或 `learning_package` 表结构。
- D13 不生成 JSON，不接入 Runner，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 或外部 LLM，不真实连接 MinIO，不发送 RocketMQ，不新增 API，不写入 `ai_call_record`。

## JSON 制品生成边界

- D14 提供 `JsonArtifactService` 和 `JsonLearningPackageExporter`，从 D7 已保存的源字幕、D8 已保存的目标语言字幕和 D9 已保存的学习包中按 `taskId + userId + targetLanguage` 查询当前 owner scope 数据，并生成 UTF-8 JSON 学习包导出内容。
- JSON 内容固定包含 `schemaVersion`、`taskId`、`targetLanguage`、`subtitles` 和 `learningPackage`；字幕项按 `segment_index ASC` 输出，并包含 `index`、`startMillis`、`endMillis`、`sourceText` 和 `translatedText`。
- D14 生成前会校验源字幕、翻译字幕和学习包均存在，校验源字幕与翻译字幕 index 及时间范围一致，清理控制字符，并拒绝包含 token、secret、API key、Authorization header 或本地路径的内容。
- D14 只通过 D10 `ArtifactFileService.saveArtifactFile` 保存制品，`artifactType` 固定为 `JSON`，`contentType` 固定为 `application/json; charset=utf-8`，文件名由后端生成且不包含路径片段。
- D14 不直接调用 `StorageService` 或 `ArtifactFileMapper`，不新增数据库表或字段，不修改 `artifact_file`、`subtitle_segment`、`subtitle_translation_segment` 或 `learning_package` 表结构。
- D14 不生成 SRT/VTT/Markdown，不接入 Runner，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、OpenAI/中转站/LangChain4j 或外部 LLM，不真实连接 MinIO，不发送 RocketMQ，不新增 API，不写入 `ai_call_record`。

## AI 调用记录边界

- D15 创建 `ai_call_record` 表，并提供 `AiCallRecordService`、domain、mapper、dto 和脱敏组件，用于记录 ASR / LLM 调用的可审计安全元数据。
- `AiCallRecordService.startCall` 只创建 `STARTED` 记录，记录 `taskId`、`userId`、`callType`、`stage`、`provider`、可选 `model`、开始时间、输入抽象计量和请求 fingerprint，不保存原始请求内容。
- `completeCall` 只按 `id + taskId + userId` 更新当前 owner 的记录为 `SUCCEEDED`，写入结束时间、耗时、token usage、输入/输出抽象计量和 request/response fingerprint，不保存原始响应内容。
- `failCall` 只按 `id + taskId + userId` 更新当前 owner 的记录为 `FAILED`，写入结束时间、耗时、错误码、脱敏并截断到 512 字以内的错误摘要和 retryable 标记。
- `listByTask` 只按 `taskId + userId` 查询当前用户当前任务的调用记录，并按 `created_at ASC, id ASC` 稳定排序；返回 view 不包含 `userId`。
- F6 已在显式 pipeline executor 中接入 `WriteAiCallRecordStep`，复用 D15 service 写入 ASR、字幕翻译和学习包生成的安全调用摘要；该步骤不包装 provider，不新增真实外部调用，不发送 RocketMQ，不新增 API，不改前端，不生成 SRT/VTT/Markdown/JSON，不修改 D7-D14 已完成业务表或制品链路。
- D15 表结构和 DTO 不保存 raw prompt、raw response、原始 ASR 文本、字幕全文、音频路径、objectKey、本地路径、Authorization header、API key、token 或 secret。

## 结果页查询边界

- D16 提供 `GET /api/tasks/{taskId}/results` 结果概览 API 和前端任务详情页结果展示。
- `TaskResultService` 先按 Bearer access token 获取当前用户，再用 `taskId + userId` 查询 `analysis_task` 做 owner scope 校验；任务不存在或不属于当前用户时返回 `TASK_NOT_FOUND`。
- 结果 API 只聚合 D7 `SubtitleSegmentQueryService`、D8 `SubtitleTranslationQueryService`、D9 `LearningPackageQueryService`、D10 `ArtifactFileQueryService` 和 D15 `AiCallRecordService.listByTask` 的已持久化只读结果。
- 响应不包含 `userId`、`objectKey`、本地路径、access token、refresh token、API key、Authorization header、secret、raw prompt、raw response、request fingerprint 或 response fingerprint。
- 没有字幕、翻译、制品或 AI 调用记录时返回空数组；没有学习包时返回 `null`。
- D16 不生成新的字幕、翻译、学习包或 SRT/VTT/Markdown/JSON 制品，不创建数据库表，不修改 Flyway migration，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、LLM、OpenAI、中转站或 LangChain4j，不发送 RocketMQ，不接入真实 Runner。

## 结构化日志边界

- E1 使用 Logback pattern + SLF4J MDC 输出结构化 key=value 日志，不新增第三方日志依赖，不引入 JSON encoder。
- `StructuredRequestLoggingFilter` 为每个 HTTP 请求生成或复用 `traceId` / `requestId`，写入 MDC，并在响应头返回 `X-Trace-Id` 和 `X-Request-Id`。
- HTTP completion log 固定记录 `event=http_request_completed`、`method`、不含 query string 的 `path`、`status`、`durationMs`、`clientIp`、`userAgentHash` 和 `outcome`，不记录 request body、response body、Authorization header、Cookie 或 query string 敏感值。
- `SafeLogSanitizer` 用于日志错误摘要脱敏和长度限制，覆盖 Authorization、Cookie、Set-Cookie、token、secret、API key、password、refresh token、objectKey、本地路径、raw prompt 和 raw response 等字段。
- `GlobalExceptionHandler` 记录结构化异常日志，包含 `event=exception_handled`、`errorCode`、`exceptionType` 和脱敏截断后的 `errorMessage`，不改变现有 API 响应语义。
- 任务状态变更、MQ producer/consumer 和 Runner 边界只增加结构化日志字段，不改变状态机、MQ 发送语义；截至 F6，显式启用的 pipeline executor 已能解析上传源、调用 FFmpeg 提取音频、调用 ASR provider 抽象并持久化字幕转写片段，再通过 LLM provider 抽象覆盖生成字幕翻译和学习包，复用 artifact 服务生成 SRT/VTT/Markdown/JSON 制品，并复用 `AiCallRecordService` 写入 AI 调用记录安全元数据。
- E1 不接入 E3 tracing，不新增业务 API，不修改数据库表或 Flyway migration，不改前端。

## 业务 metrics 边界

- E2 使用 Spring Boot Actuator / Micrometer 记录业务 metrics，不新增第三方 Prometheus 依赖，不修改 `backend/pom.xml`。
- Actuator 仅暴露 `health`、`info` 和 `metrics`，`health.show-details` 保持 `never`，`info.env.enabled` 保持 `false`，公共 meter tag 固定为 `application=courselingo-pro`。
- E2 指标包括任务创建、任务状态流转、Runner run/retry/cancel 边界、Runner run 耗时、RocketMQ produce/consume、上传会话创建、chunk 接收、上传完成、制品保存次数和制品字节数。
- Metrics tag 只使用低基数字段：`outcome`、`from`、`to`、`stage`、`topic`、`tag` 和 `type`。tag 值会归一化，空值为 `unknown`，过长、路径样式或敏感样式值归为 `other`。
- Metrics 不把 `userId`、`taskId`、`uploadId`、`objectKey`、文件名、本地路径、音频路径、token、secret、API key、Authorization header、Cookie、raw prompt、raw response、字幕全文或学习包全文写入 tag。
- E2 对 task / mq / runner / upload / artifact 的修改只增加 metrics 观测，不改变状态机、MQ topic/tag/group、发送时机、Runner 执行逻辑、上传校验或制品保存语义。
- E2 不接入 E3 tracing，不新增业务 API，不新增数据库表，不修改 Flyway migration，不改前端，不接入真实 Runner Pipeline，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、LLM、OpenAI、中转站或 LangChain4j，不发送新的 MQ。

## Tracing 上下文边界

- E3 提供项目内部 tracing 上下文能力，不接入 OpenTelemetry、Jaeger、Zipkin、SkyWalking 或外部 tracing 平台，不新增第三方 tracing 依赖。
- `common.tracing` 提供 `TracingContext`、`TracingContextFactory`、`TracingContextHolder` 和 `TracingScope`。上下文只包含安全的 `traceId` 和 `requestId`，写入 ThreadLocal 与 SLF4J MDC，并在 scope 关闭时恢复或清理，避免线程复用污染。
- HTTP 请求继续复用 E1 的 `X-Trace-Id` / `X-Request-Id`。请求头缺失、过长、字符不安全、包含 Authorization / Cookie / token / secret / API key / password 等敏感词或路径样式时，会替换为服务端生成的 UUID。
- `StructuredRequestLoggingFilter` 在请求开始时建立 tracing scope，在 completion log 写出后清理上下文；HTTP completion log 仍不记录 request body、response body、query string 或敏感 header。
- RocketMQ `AnalysisTaskMessage` 增加 `traceId`，并继续保留 `requestId`。Producer 只把 `taskId`、`uploadId`、`userId`、`targetLanguage`、`requestId`、`traceId` 和 `createdAt` 写入消息体，不写入 token、secret、API key、Authorization、Cookie、objectKey、本地路径、raw prompt、raw response、字幕全文或学习包全文。
- Consumer 在调用 handler 前用消息中的 `traceId` / `requestId` 建立 tracing scope，Runner 边界继续复用同一上下文；`BoundedTaskExecutor` 会捕获当前 tracing context 并在线程池 worker 中恢复，执行结束后清理。
- E3 对 MQ producer/consumer、Runner 和 bounded executor 的修改只传递 tracing 上下文，不改变状态机、MQ topic/tag/group、发送时机、Runner 执行逻辑、上传校验、制品保存语义或 metrics tag 设计。
- E3 不新增业务 API，不新增数据库表，不修改 Flyway migration，不改前端，不进入 E4 owner 保护，不接入真实 Runner Pipeline，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、LLM、OpenAI、中转站或 LangChain4j，不发送新的 MQ。

## 安全配置与 owner 保护边界

- E4 使用 `SecurityHeadersFilter` 补充基础安全响应头：`X-Content-Type-Options=nosniff`、`X-Frame-Options=DENY`、`Referrer-Policy=no-referrer`、`Cache-Control=no-store` 和 `Pragma=no-cache`。
- E4 不引入 Spring Security Web、复杂 RBAC 或多租户 SaaS 权限系统，不改变 JWT 登录、refresh token 或现有鉴权服务语义。
- Actuator 仍只暴露 `health`、`info` 和 `metrics`，不暴露 `env`、`configprops`、`heapdump`、`threaddump`、`loggers` 或 `prometheus`。
- owner scope 继续以服务端从 Bearer access token 解析出的 `userId` 为准；上传、任务、结果、制品和 AI 调用记录不得信任客户端传入的 `userId`、`ownerId` 或伪造 owner header。
- `UploadSessionOwnerGuard` 在访问 mapper 前校验 `uploadId`、`currentUserId` 和状态更新值，跨用户或非法 scope 不泄露资源是否存在。
- E4 不新增业务 API，不新增数据库表，不修改 Flyway migration，不改前端，不接入真实 Runner Pipeline，不调用 FFmpeg、ASR Provider、SiliconFlow、mock ASR、LLM、OpenAI、中转站或 LangChain4j，不发送新的 MQ。

## GitHub Actions CI 边界

- E5 新增 `.github/workflows/ci.yml`，workflow 名称为 `CI`，触发范围为 `push` 和 `pull_request`。
- `backend-test` job 使用 `ubuntu-latest`、`actions/checkout@v6`、`actions/setup-java@v5`、Temurin Java 21 和 Maven cache，在 `backend/` 下运行 `./mvnw test`。
- `frontend-build` job 使用 `ubuntu-latest`、`actions/checkout@v6`、`actions/setup-node@v6`、Node.js 24 LTS 和 npm cache，在 `frontend/` 下运行 `npm ci` 与 `npm run build`。
- CI 只验证后端测试和前端构建，不部署、不发布 Docker 镜像、不推送制品、不配置 secrets，不连接真实 MySQL、Redis、RocketMQ、MinIO 或外部 AI 服务。
- E5 不新增业务 API，不改业务代码，不新增数据库表，不修改 Flyway migration，不改前端功能，不接入真实 Runner Pipeline，不进入 E6 或后续任务。

## Dependabot 依赖更新边界

- E6 新增 `.github/dependabot.yml`，用于按周检查后端 Maven、前端 npm 和 GitHub Actions 依赖更新。
- Maven 更新范围固定为 `/backend`，npm 更新范围固定为 `/frontend`，GitHub Actions 更新范围固定为 `/`。
- Maven 和 npm 配置 minor/patch 更新分组；不强制 major 更新分组，major 更新由 Dependabot 单独提出。
- Dependabot 只创建依赖更新 PR，不配置私有 registry、secrets、真实账号、reviewer、assignee 或自动 merge。
- E6 不修改 `pom.xml`、`package.json`、`package-lock.json` 或 CI workflow，不升级任何依赖版本，不改业务代码，不新增数据库表，不修改 Flyway migration，不改前端功能，不进入 E7 或后续任务。

## Docker 本地运行边界

- E7 新增根目录 `DOCKER.md`，说明本地 Docker / Docker Compose 使用方式、环境变量、服务端口、验证方式、常见问题和安全提醒。
- 当前 `compose.yaml` 只承载 MySQL、Redis、MinIO、RocketMQ 等基础设施依赖；后端和前端当前没有 Dockerfile，不通过项目镜像启动。
- 后端仍建议使用 Java 21 和 Maven Wrapper 在本机运行；前端仍建议使用 Node.js 24 LTS 和 npm 在本机运行。
- Docker Compose 启动成功不等于完整业务链路可用；F6 已在显式 pipeline 中接入上传源解析、FFmpeg 音频提取、ASR provider 转写、字幕转写持久化、LLM provider 字幕翻译、学习包持久化、SRT/VTT/Markdown/JSON 制品生成和 `ai_call_record` 安全元数据写入。F7 已提供真实 HTTP 端到端验收脚本，但脚本存在不等于当前环境已经配置真实外部 provider 并跑通完整 AI 验收，也不因此宣称项目生产可用。
- E7 不修改 `compose.yaml`、`.env.example`、`application.yml`、业务代码、前端功能、数据库表、Flyway migration 或 CI workflow，不运行真实 Docker / Docker Compose 作为通过条件，不进入 E8 或后续任务。

## Security Policy 文档边界

- E8 新增根目录 `SECURITY.md`，说明项目安全定位、支持版本、漏洞反馈方式、密钥处理、认证与授权、owner scope、防泄漏原则、上传安全、可观测安全、依赖安全、Docker 本地安全、非目标和提交前安全检查。
- `SECURITY.md` 明确 LectureLens 是学习和简历项目，不宣称生产级 SaaS 安全能力。
- E8 只补充文档，不修改认证、JWT、refresh token、owner scope、Spring 配置、`.env.example`、`application.yml`、`compose.yaml`、数据库表、Flyway migration、前端功能或远端 GitHub 安全设置。

## Test Plan 文档边界

- E9 新增根目录 `TEST_PLAN.md`，说明测试目标、测试分层、后端测试命令、前端构建命令、CI 测试边界、外部依赖测试原则、重点回归范围、安全测试 checklist、手工验证清单、已知 warning 和提交前 checklist。
- 自动化测试边界保持 mock/fake/disabled-mode 优先，不把真实 Docker、MySQL、Redis、RocketMQ、MinIO、FFmpeg、ASR、LLM 或外部 API 作为默认通过条件。
- E9 只补充文档，不新增测试代码，不修改业务代码、Maven / npm 配置、CI workflow、Docker / Dependabot / Security 配置、数据库表、Flyway migration 或前端功能。

## Interview Notes 文档边界

- E10 新增根目录 `INTERVIEW_NOTES.md`，用于整理 LectureLens 的面试讲解主线、项目定位、技术栈、已实现核心功能、架构亮点、难点、常见问答、简历写法建议、当前边界和后续计划。
- `INTERVIEW_NOTES.md` 只引用当前 README、docs、API、DB、MQ、SECURITY、TEST_PLAN 和 DOCKER 文档中已经明确的能力，不宣称项目已上线、已商用、生产级高并发 SaaS、完整 RBAC、Kubernetes、微服务或当前环境已通过真实外部 provider 端到端验收。
- E10 只补充文档，不修改业务代码、测试代码、Maven / npm 配置、CI / Docker / Dependabot 配置、数据库表、Flyway migration 或前端功能。

## Demo Script 文档边界

- E11 新增根目录 `DEMO_SCRIPT.md`，用于面试、答辩或本地自测时按步骤展示启动基础设施、启动后端、启动前端、注册登录、上传视频、创建任务、查看任务详情、查看结果页、可观测性和安全边界。
- `DEMO_SCRIPT.md` 只引用当前 README、DOCKER、TEST_PLAN、SECURITY、INTERVIEW_NOTES、API、DB、MQ、Compose 和环境变量样例中已经明确的能力；不宣称当前环境已通过真实外部 provider 端到端验收，不宣称生产级 SaaS、线上部署或高并发压测结果。
- E11 只补充文档，不修改业务代码、测试代码、Maven / npm 配置、CI / Docker / Dependabot 配置、`compose.yaml`、`.env.example`、`application.yml`、数据库表、Flyway migration 或前端功能，不运行真实外部服务作为通过条件。

## Resume Project 文档边界

- E12 新增根目录 `RESUME_PROJECT.md`，用于把 LectureLens 写进 Java 后端 / AI 应用实习简历，提供项目名、技术栈、bullet、一段式描述、60 秒口述稿、最终推荐版本和禁用表述。
- `RESUME_PROJECT.md` 只引用当前 README、INTERVIEW_NOTES、DEMO_SCRIPT、TEST_PLAN、SECURITY、DOCKER、API、DB、MQ 和架构文档中已经明确的能力；不宣称当前环境已通过真实外部 provider 端到端验收，不宣称生产上线、商用用户、生产级 SaaS 或高并发压测结果。
- E12 只补充文档，不修改业务代码、测试代码、Maven / npm 配置、CI / Docker / Dependabot 配置、`compose.yaml`、`.env.example`、`application.yml`、数据库表、Flyway migration 或前端功能，不运行真实外部服务作为通过条件。

## Pipeline Executor 边界

- F1 新增 `PipelineAnalysisTaskWorkExecutor`，作为后续真实 Runner Pipeline 的可切换执行器骨架。
- 默认仍使用 `NoopAnalysisTaskWorkExecutor`，只验证 Runner 状态流转；只有显式设置 `courselingo.task.runner.pipeline.enabled=true` 时才启用 pipeline executor。
- Pipeline executor 固定包含 `VALIDATE_TASK`、`RESOLVE_UPLOADED_SOURCE`、`EXTRACT_AUDIO`、`TRANSCRIBE`、`PERSIST_SUBTITLES`、`TRANSLATE_SUBTITLES`、`GENERATE_LEARNING_PACKAGE`、`GENERATE_ARTIFACTS`、`WRITE_AI_CALL_RECORD` 和 `UPDATE_TASK_PROGRESS_STATUS` 步骤边界。
- F2 将 `RESOLVE_UPLOADED_SOURCE` 实现为 `ResolveUploadedSourceStep`：按 `uploadId + userId` 校验上传会话归属。`STORED` 必须使用 `MINIO` 存储类型并确认远端对象存在；有效的本地 assembled 文件可作为缓存，缺失或大小不符时从 MinIO 下载到同目录临时文件，校验字节数后安全替换。legacy `UPLOADED` 仍只读取本地 assembled 文件。该步骤不向 API、日志、异常或 context `toString` 暴露 `objectKey` 或本地路径。
- F2 将 `EXTRACT_AUDIO` 实现为 `ExtractAudioStep`：从 context 读取内部 source path，输出到 `courselingo.task.runner.workspace-dir` 下的 runner workspace，并调用 D1 `FfmpegAudioExtractor`。音频路径只保存在 pipeline 内部 context 中，供 F3 使用。
- F3 将 `TRANSCRIBE` 实现为 `TranscribeAudioStep`：读取 F2 `AudioExtractionResult`，通过注入的 `SpeechToTextProvider` 抽象执行转写，并把 `SpeechToTextResult` 放入 pipeline context。长音频分片 ASR 使用受控并发，默认 `ASR_CHUNK_CONCURRENCY=2`，最大 `ASR_CHUNK_MAX_CONCURRENCY=4`；所有 chunk 结果按 chunk index 排序后复用现有 offset / reindex 逻辑合并。测试只使用 fake provider，不调用真实 SiliconFlow 或外部 ASR。
- F3 将 `PERSIST_SUBTITLES` 实现为 `PersistSubtitleSegmentsStep`：按 `taskId + userId` 校验任务归属后复用 D7 字幕持久化服务覆盖保存转写片段，重复执行不会产生重复字幕。
- F4 将 `TRANSLATE_SUBTITLES` 实现为 `TranslateSubtitleSegmentsStep`：按 `taskId + userId` 校验任务归属后复用 D8 `SubtitleTranslationService`，通过注入的 `LlmProvider` 抽象读取已持久化源字幕并覆盖保存目标语言翻译，重复执行不会产生重复翻译。
- F4 将 `GENERATE_LEARNING_PACKAGE` 实现为 `GenerateLearningPackageStep`：按 `taskId + userId` 校验任务归属后复用 D9 `LearningPackageService`，通过注入的 `LlmProvider` 抽象读取源字幕和翻译字幕并覆盖保存学习包，重复执行不会产生重复学习包。
- F5 将 `GENERATE_ARTIFACTS` 实现为 `GenerateArtifactsStep`：按 `taskId + userId` 校验任务归属后复用 D11-D14 artifact 服务生成 SRT/VTT/Markdown/JSON，并通过 D10 `ArtifactFileService.saveArtifactFile` 按 `taskId + userId + artifactType + language` 覆盖保存制品元数据；重复执行不会追加重复 `artifact_file`。
- F6 将 `WRITE_AI_CALL_RECORD` 实现为 `WriteAiCallRecordStep`：按 `taskId + userId` 校验任务归属后，依次把 context 中暂存的 ASR / LLM 调用摘要写入 `ai_call_record`。写入过程复用 D15 service 的 start / complete / fail owner 更新语义，不直接绕过 service 写 mapper；同一次 pipeline 重试会按本次执行重新记录调用事实，不尝试跨重试复用旧记录。
- Pipeline step 抛出的异常会被包装为脱敏后的 step exception，并继续由现有 Runner 失败路径推进任务到 `FAILED`，不新增 MQ topic、tag、consumer group 或业务 API。
- F6 不新增数据库表，不修改 Flyway migration，不新增业务 API，不新增 MQ 行为，不改前端，不改 provider 真实调用配置。

## 真实端到端验收脚本边界

- F7 新增 `scripts/e2e/run-pipeline-e2e.ps1` 和 `docs/E2E_ACCEPTANCE.md`，用于对已经启动的后端执行真实 HTTP API 验收。
- 脚本只调用公开 API：`GET /actuator/health`、`POST /api/auth/register`、`POST /api/auth/login`、上传会话创建、chunk 上传、缺失分片查询、complete、`POST /api/tasks`、`GET /api/tasks/{taskId}` 和 `GET /api/tasks/{taskId}/results`。
- 脚本不调用 service、mapper、数据库、MQ 客户端或本地 runner 内部类，不绕过 owner scope，也不新增任何测试专用业务 API。
- 脚本不启动 Docker、后端、前端、MySQL、Redis、MinIO、RocketMQ、FFmpeg、ASR provider 或 LLM provider；真实成功验收依赖用户已在本地完成这些运行态和 provider 配置。
- TRANSLATION-DUAL-OUTPUT-R1 后，脚本只接受 `translations` 数量与 `subtitles` 严格相等，且 `sourceFullText`、`translatedFullText` 同时非空；只有全文或只有分段译文均视为失败。
- 公开 API 可校验 health、认证链路、上传链路、任务终态、结果概览中的 subtitles、translations、learningPackage、SRT/VTT/Markdown/JSON artifact 安全元数据和 `ai_call_record` 安全元数据。
- 公开 API 暂不能校验 artifact 文件真实下载内容、内部 `objectKey`、本地 runner workspace 路径、provider 原始 prompt / response、内部 MQ 投递细节、数据库行级中间态或 MinIO 对象内部路径；这些内容应保持服务端内部实现细节。
- 脚本输出只打印脱敏摘要，不打印 access token、refresh token、Authorization、Cookie、API key、secret、`objectKey`、本地视频路径、音频路径、runner workspace 路径、字幕全文、翻译全文、学习包全文、raw prompt 或 raw response。
- F7 不新增数据库表，不修改 Flyway migration，不新增业务 API，不新增 MQ topic / tag / consumer group，不修改 `backend/pom.xml`、`application.yml`、`.env.example`、Compose 或前端。

## LangChain4j 使用边界

- LangChain4j 用于编排摘要、重点、Q&A、术语表生成。
- LangChain4j 不作为业务事实来源。
- 结构化输出必须落到 `learning_package` 和相关制品记录。
- 截至 F7，项目已完成 SRT/VTT/Markdown/JSON 制品内容生成、AI 调用记录表和记录服务、基于已持久化结果的任务结果查看能力、后端结构化日志基础、业务 metrics 基础、项目内部 tracing 上下文能力、基础安全响应头和 owner 保护加固、GitHub Actions CI、Dependabot 依赖更新配置、Docker 使用说明、Security Policy、Test Plan、Interview Notes、端到端演示脚本、简历项目描述、可选 pipeline executor 骨架、显式 pipeline 中的上传源解析、FFmpeg 音频提取、ASR provider 转写、字幕转写持久化、LLM provider 字幕翻译、学习包持久化、SRT/VTT/Markdown/JSON 制品生成、`ai_call_record` 安全元数据写入，以及面向公开 HTTP API 的真实端到端验收脚本。

## SSE 事件协议

- SSE 用于任务进度推送。
- 事件包含 `taskId`、`status`、`progressPercent`、`currentStage`、`errorCode`、`errorMessage`、`updatedAt`。ASR 分片阶段还可包含向后兼容的 `completedChunks`、`totalChunks`、`currentChunkIndex`、`stepDetail`，用于展示“语音转文字中：已完成 x / total 段”。
- 终态事件为 `SUCCEEDED`、`FAILED`、`CANCELLED`。
- SSE 断开后前端允许重连，并通过任务详情接口补齐状态。

## 安全边界

- 所有上传、任务、结果、制品接口必须鉴权。
- 所有 owner 资源必须按 `user_id` 过滤。
- retry / cancel 只能从 Bearer access token 得到当前用户，并按 `taskId + user_id` 校验 owner scope；不得从请求体、Query、Header 或 Body 接收 `userId` / `ownerId` 作为归属依据。
- 不信任客户端传入的 owner、Content-Type、文件名和排序字段。
- MinIO bucket 禁止公开读写。
- 密钥只能来自环境变量或安全配置，不得硬编码。

## 未指定项

- 生产并发指标：未指定。
- 上线域名：未指定。
- 商业付费能力：未指定。
- 邮件、短信、第三方登录：未指定。
- 管理后台：未指定。

## LONG-6 long video pipeline notes

- After FFmpeg extracts audio, the ASR step checks the extracted audio size against the configured provider limit.
- `AudioDurationProbe` treats the extracted WAV header as the authoritative timeline: the JavaSound implementation calculates milliseconds from `frameLength / frameRate` and fails with the sanitized `MEDIA_INPUT_INVALID` error when the duration cannot be read. The probe runs once before any ASR request and does not expose the local audio path.
- If the audio exceeds the limit, the runner creates temporary FFmpeg chunks under the task workspace `asr-chunks`, transcribes chunks through the existing `SpeechToTextProvider` with controlled concurrency, offsets segment timestamps by chunk start time, reindexes segments from 0, then deletes the temporary chunk directory.
- Single-file and chunked ASR results are bounded to that authoritative duration. Provider segments are intersected with the real chunk range, segments wholly beyond it are discarded, partially overlapping segments are clipped, and invalid provider timestamps are distributed only inside the real range. A chunk whose start is at or beyond the authoritative duration is rejected; the last valid chunk ends exactly at that duration. The final `SpeechToTextResult.audioDurationMillis` and aggregate ASR `inputUnits` use the probed duration, so persisted subtitles, SRT/VTT, fusion windows, Chapter, and Video Context inherit the same bounded timeline without downstream patches.
- The bounded task executor default timeout is 14400 seconds. ASR chunk processing refreshes the Redis claim around chunk start, completion, retry, and a periodic keepalive while chunk futures are running. Refresh validates the stored request id before extending `cl:t:claim:{taskId}`.
- ASR chunk progress is written to the Redis progress snapshot with `completedChunks`, `totalChunks`, `currentChunkIndex`, and `stepDetail`, so SSE can show granular long-video progress without making Redis the business source of truth.
- Full source text is assembled from ordered ASR segments. With full-text mode enabled, translation uses aligned JSON batches carrying batch-local and original source indexes, validates complete one-to-one coverage, persists every `subtitle_translation_segment`, and derives `translatedFullText` from those same ordered translations.
- Provider network calls, JSON parsing, and complete coverage validation finish before database persistence begins. Segment rows and `task_full_text_result` are then deleted and inserted in one final transaction. Output truncation, incomplete JSON, missing segments, duplicate indexes, blank text, and non-string text trigger deterministic batch bisection; a single oversized segment may be split at natural punctuation and merged back to its original index. Authentication, configuration, network-wide, timeout, mixed-index, unknown-index, and business-validation failures do not trigger blind splitting.
- After each aligned batch passes structural parsing, translation validates target-language semantics before accepting the batch. For a non-Chinese source translated to Chinese, the ordered batch output must contain enough CJK text; highly source-similar output is classified as `UNTRANSLATED_TEXT`. Non-technical segments also reject punctuation-only source copies and complete English prose, so one translated segment cannot hide another untranslated sentence inside an otherwise Chinese batch. Bounded technical terms, explicit code identifiers, and a centralized finite list of multi-word product names such as `Spring Cloud Config Server`, `Spring Cloud Netflix Eureka`, `Visual Studio Code`, and `OpenAI Chat Completions API` may remain in English; those phrases are removed before the remaining English sequence is checked for prose markers and ordinary natural-language words.
- The first semantic failure sends the complete source batch through one corrective target-language request without embedding the previous provider response. If the configured semantic attempts are exhausted, a multi-segment batch is bisected and each child restarts from a normal request; a single oversized segment reuses punctuation-based piece splitting and validates each piece independently. Structural and semantic splitting share `single-segment-max-depth`, and a final unsplittable failure reaches persistence with zero translation writes.
- Translation continues to use `AiModelStage.TRANSLATION_FULL_TEXT`, the `deepseek-text` route, JSON structured output, the configured timeout, max tokens, and max attempts. Pipeline persistence still creates one aggregate `ai_call_record`; its row count is not the number of underlying provider batches.
- `semantic-max-attempts` accepts only `1` or `2` and defaults invalid values to `2`: `1` performs only the initial request, while `2` allows at most one corrective semantic request. It is not an unbounded provider retry setting and remains separate from provider `max-attempts`, which covers transport/provider-call failures. Every returned provider result, including rejected semantic attempts and split or piece results, contributes duration and token usage to the single aggregate Pipeline translation record; `inputUnits` and `outputUnits` remain the original source segment count.
- When both the declared source and target language tags are Chinese and the source text passes the bounded Chinese-content check, translation skips the provider, persists one aligned segment translation per source segment, and derives the full text from those rows. Chinese-looking text declared as a non-Chinese source language, or any non-Chinese target, still uses the provider.
- Learning package generation prefers `translatedFullText`, falling back to source subtitles only when no full-text translation exists.
- Successful translation guarantees aligned segment rows before SRT/VTT/JSON/Markdown generation; artifact fallback behavior remains defensive for pre-existing or failed historical data.

## 原视频播放预览边界

- 原视频预览用于上传完成后的上传页回看，以及任务详情页的原视频回看。
- 前端不直接拼接本地文件路径或对象存储 key，而是先通过受保护 API 申请短期播放令牌，再把服务端返回的 `playbackUrl` 交给 `<video>` 标签。
- 上传播放令牌接口按 `uploadId + currentUserId` 校验 owner scope；任务播放令牌接口按 `taskId + currentUserId` 校验任务归属后，再解析任务绑定的上传源。
- 播放令牌使用服务端签名，默认有效期由 `courselingo.media.playback.token-ttl-minutes` / `MEDIA_PLAYBACK_TOKEN_TTL_MINUTES` 控制，默认 15 分钟。
- 播放流接口通过 query token 访问，因为浏览器原生 `<video>` 标签不能稳定附带 Bearer header；服务端仍必须校验令牌签名、过期时间、`uploadId` 绑定关系和 owner scope。
- 播放流支持 HTTP Range，按请求范围流式读取，不把完整视频读入内存。
- 新上传源文件以 MinIO 为持久化事实来源，complete 仅在对象写入成功后返回 `STORED`；本地 assembled 文件是受控缓存。legacy `UPLOADED` 继续只读取历史本地 assembled 文件。接口响应、异常、日志和前端状态不得暴露本地路径、`objectKey`、access token、refresh token、API key、secret、raw prompt 或 raw response。
- 原视频自带字幕能力只通过 `ffprobe` 探测原视频容器内 subtitle stream，并通过 `ffmpeg -map 0:<streamIndex> -c:s webvtt` 将支持的文本软字幕轨道提取为 WebVTT 缓存文件；不提取外挂字幕，不读取 AI VTT artifact，不做视频转码，不做硬字幕烧录。
- 支持提取的字幕 codec 限定为 `subrip`、`srt`、`ass`、`ssa`、`mov_text`、`webvtt`。PGS、DVD、DVB、xsub 等图片字幕当前不做 OCR 或文字提取。
- 前端上传页“原视频预览”和任务详情页“课程原视频”均用受保护 API 下载 WebVTT 文本，创建 Blob URL 供 `<track>` 使用，并使用自定义 overlay 按 video `currentTime` 显示当前字幕，避免只依赖浏览器原生字幕轨道渲染。
- 原视频自带字幕缓存位于后端本地 `storage/embedded-subtitles/{uploadId}/track-{streamIndex}.vtt`，API 和日志不得暴露缓存路径、本地视频路径、`objectKey`、`userId`、token、secret 或字幕全文。
- 该能力不新增数据库表，不新增 RocketMQ topic/tag/consumer group，不改变任务状态机，不做视频转码、多清晰度、自适应码率、下载按钮、分享链接或管理员绕过。
## VISION-R1 keyframe scanning

VISION-R1 adds a low-cost visual channel before OCR/VLM. When the explicit pipeline executor is enabled, `EXTRACT_KEYFRAMES` runs after `RESOLVE_UPLOADED_SOURCE` and before `EXTRACT_AUDIO`.

- The step uses FFmpeg to extract bounded low-resolution JPEG thumbnails, then computes frame changes in Java with `ImageIO`; it does not call OCR, VLM, fusion, course QA, embedding, or any visual model.
- `courselingo.vision.keyframe.enabled=false` skips the step without changing the ASR/LLM path.
- Keyframe scan failures are isolated: the step writes a sanitized `WARN` task log and continues to audio extraction, ASR, translation, learning package generation, artifacts, and AI call record writing.
- `VideoKeyframeScanService` deletes old keyframes for the same `taskId + userId` before inserting new rows, and `video_keyframe.uk_video_keyframe_task_frame` prevents duplicate frame records.
- Server deployment runs `scripts/server/apply-db-migrations.sh` before backend restart. The script executes Flyway with `FLYWAY_ENABLED=true`, verifies successful V11 in `flyway_schema_history`, and verifies that `video_keyframe` exists without clearing data or printing secrets.

## OCR-R1 keyframe OCR

OCR-R1 adds local OCR for already-selected VISION-R1 keyframes. It does not call VLMs, does not summarize images, does not fuse audio and visual evidence, does not implement course QA, and does not create embeddings.

When the explicit pipeline executor is enabled, `OCR_KEYFRAMES` runs after `GENERATE_ARTIFACTS` and before `WRITE_AI_CALL_RECORD`. It reads keyframe thumbnails through `StorageService`, writes temporary image files only for the local OCR process, cleans the temporary directory after each frame, and persists sanitized OCR metadata in `video_keyframe_ocr`.

Failure semantics:

- If `courselingo.vision.ocr.enabled=false`, the step is skipped and existing ASR/LLM behavior is unchanged.
- If OCR fails, the step writes a sanitized warning and the main ASR/translation/learning-package pipeline continues by default.
- Per-frame provider failures are stored as `FAILED` OCR rows; they do not fail the task.
- OCR rows are idempotent for the same `taskId + userId`: the service deletes old OCR rows for the task before inserting the new scan result.

Public APIs return a nested safe `ocr` view on keyframe metadata. They never return `objectKey`, local temporary paths, provider stderr, tokens, API keys, raw prompts, raw responses, or OCR process command lines.
- Thumbnail files are stored through the existing `StorageService` abstraction. The database stores internal `object_key`, but keyframe list APIs and task results return only safe metadata and an authenticated image API path.
- Temporary frame extraction directories live under the runner workspace and are deleted in a `finally` block. Source frame extraction is capped by `maxSourceFramesTotal`, derived from `maxKeyframesTotal`, to avoid unbounded disk growth.
- Frontend task detail fetches keyframe images as authenticated blobs and revokes object URLs when the task changes or the page unloads.

## VLM-R1 keyframe visual analysis

VLM-R1 adds a disabled-by-default visual analysis foundation for already-selected keyframes. It does not change ASR, translation, learning-package generation, OCR semantics, RocketMQ topics, audio-visual fusion, course QA, or embeddings.

When the explicit pipeline executor is enabled and `courselingo.vision.analysis.enabled=true`, `ANALYZE_KEYFRAMES` runs after `OCR_KEYFRAMES` and before `WRITE_AI_CALL_RECORD`. This position lets the selector use both keyframe metadata and OCR text, while keeping all existing ASR/LLM artifacts available even when visual analysis fails. The step is fail-soft by default: provider errors create sanitized `FAILED` rows and a warning, but the task continues unless `COURSELINGO_VISION_ANALYSIS_FAIL_TASK_ON_ERROR=true`.

VLM-R1 only processes bounded high-value frames:

- preferred reasons: `SCENE_CHANGE` and `CONTENT_CHANGE`;
- OCR text present or materially changed;
- defaults: at most 80 frames per task, at most 2 frames per minute, and at least 10 seconds between selected frames.

The service reads thumbnails through `StorageService`, creates only temporary resized JPEG inputs for provider calls, and deletes the temporary directory after use. It never logs object keys, temporary paths, API keys, raw requests, or raw responses.

`video_keyframe_analysis` stores one row per analyzed keyframe. Re-running analysis for the same `taskId + userId` deletes old rows before inserting new results, and `uk_video_keyframe_analysis_keyframe` prevents duplicate rows. Public APIs return a nested safe `visualAnalysis` view on keyframe metadata. The response includes status, screen type, summary, detected elements, provider, model, and a friendly message; it excludes object keys, local paths, provider stderr, raw provider payloads, credentials, and user ids.

## FUSION-R1 video segment fusion

FUSION-R1 adds disabled-by-default, rule-based segment fusion for ASR subtitles, keyframe OCR text, and existing VLM visual summaries. It does not call an LLM by default, does not enable real VLM, does not implement audio-visual QA, and does not create embeddings.

When the explicit pipeline executor is enabled and `courselingo.fusion.video-segment.enabled=true`, `FUSE_VIDEO_SEGMENTS` runs after `ANALYZE_KEYFRAMES` and before `WRITE_AI_CALL_RECORD`. This position lets the step use all persisted ASR/OCR/VLM evidence while keeping AI call audit flushing last. Fusion failures are fail-soft by default: the step writes a sanitized warning and the main ASR/translation/learning-package result remains valid unless `COURSELINGO_FUSION_VIDEO_SEGMENT_FAIL_TASK_ON_ERROR=true`.

The service creates bounded time windows, defaults to 60 seconds per segment, caps generated rows with `COURSELINGO_FUSION_VIDEO_SEGMENT_MAX_SEGMENTS`, deletes previous rows for the same `taskId + userId` before inserting regenerated segments, and stores safe evidence ids/counts in `video_segment.evidence_json`. Every final window uses `end = min(start + windowMillis, durationMillis)`; invalid `end <= start` windows are dropped, and the clamped end is shared by evidence selection, persisted segment boundaries, and `timeText`. Public APIs return `VideoSegmentResponse` only and exclude object keys, local paths, provider stderr, raw prompts, raw responses, credentials, and user ids.

`POST /api/tasks/{taskId}/video-segments/rebuild` is an owner-scoped derived-data repair entrypoint for an existing `SUCCEEDED` task. It resolves the authenticated user, hides missing and non-owner tasks behind `TASK_NOT_FOUND`, rejects other statuses with `TASK_INVALID_STATUS`, and transactionally reuses the same rule-based fusion core. Explicit repair bypasses only the automatic-pipeline enabled flag so a disabled default cannot produce a false-success no-op; the normal pipeline `fuse` entry remains disabled-by-default. Rebuild returns only window/saved/empty/skipped counters and does not invoke ASR, translation, an LLM, RocketMQ, or a new analysis task; it also does not change subtitles, translations, uploads, or task state.

## QA-R1 course content QA

QA-R1 adds a user-triggered course QA endpoint and a task-detail "课程问答" tab. It is scoped to the current `taskId` and current authenticated user, is single-turn, non-streaming, and does not add embeddings, a vector database, cross-video search, agent orchestration, chat memory, voice input, or a new default pipeline step.

The backend HTTP request path stays short:

1. validate authentication and `taskId + userId` ownership;
2. validate and trim the question;
3. apply Redis fixed-window rate limiting with `cl:rate:qa:{userId}`;
4. retrieve bounded evidence from existing MySQL facts;
5. call the routed LLM only when evidence exists;
6. persist the sanitized result in `course_qa_record`;
7. return a safe `ApiResponse<CourseQaResponse>`.

Evidence retrieval is rule-based. It parses simple time windows such as `00:03:00`, `3:00`, and `3分到5分`. `CourseQaQueryTermExtractor` splits Chinese/Latin transitions, retains bounded technical identifier characters, normalizes Latin terms to lowercase, and treats generic Chinese and English question phrases as separators so mixed and Chinese-only technical questions retain their actual subject. It deduplicates terms in first-occurrence order. Retrieval scores up to 100 candidates and returns at most 8 evidence items. A candidate must first have positive `keywordScore + timeBoost`; only then may source priority and confidence affect ranking. Source priority is `video_segment` speech text, translated subtitles, and source subtitles. Learning-package content may inform context internally but is not exposed as primary time-bounded evidence. OCR and keyframes remain experimental visual assistance, but QA-R1 does not use OCR as default prompt, response, or `course_qa_record.evidence_json` evidence.

The prompt requires JSON output with `answer` and `citedEvidenceIndexes`. `CourseQaServiceImpl` and `CourseQaPromptFactory` share `CourseQaMessages.INSUFFICIENT_EVIDENCE`, exactly `当前课程内容中没有找到明确依据`. If retrieval has no positively relevant evidence, the service refuses before the LLM call, writes no QA `ai_call_record`, persists an empty evidence list, and returns null usage. If a completed model response cites no valid retrieved index, the service no longer falls back to all retrieved evidence; it returns the same controlled refusal and an empty evidence list while retaining the completed call audit. LLM calls use `AiModelStage.COURSE_QA` and `AiCallStage.COURSE_QA`; `ai_call_record` stores only safe provider/model/status/duration/token metadata and sanitized errors.

Frontend evidence cards show source type, time range, snippet, translated/fused snippet, confidence, and can seek the existing original-video player to `startTimeMillis`. The tab does not alter upload, ASR, subtitle translation, learning-package generation, artifacts, keyframe selection, SSE, or the main analysis task state machine.

## CHAPTER-R1 course chapter timeline

CHAPTER-R1 adds an on-demand "课程章节" tab and `GET /api/tasks/{taskId}/chapters` / `POST /api/tasks/{taskId}/chapters/generate` APIs. It is deliberately outside the main Runner Pipeline in this round: no pipeline step, MQ message, async chapter queue, VLM, Agent, embeddings, vector database, keyframe dependency, or OCR dependency is introduced.

The backend path is:

1. validate authentication and `taskId + userId` ownership;
2. read persisted subtitles, subtitle translations, and `video_segment.asr_text`;
3. create bounded time windows using `COURSELINGO_CHAPTER_WINDOW_SECONDS`, `COURSELINGO_CHAPTER_MAX_EVIDENCE_ITEMS`, and `COURSELINGO_CHAPTER_MAX_CHARS_PER_WINDOW`;
4. optionally include learning-package summary/glossary as global context only, not as time-boundary evidence;
5. call the existing OpenAI-compatible provider through `AiModelStage.COURSE_CHAPTER`;
6. parse JSON chapters, filter invalid evidence indexes, clamp times, sort, and drop invalid duplicate/overlapping chapters;
7. overwrite `course_chapter` rows only after successful parsing;
8. write safe `ai_call_record` metadata with `AiCallStage.COURSE_CHAPTER`;
9. return safe chapter rows to the frontend.

Chapter generation failures do not change `analysis_task.status`, do not delete existing successful chapters, and do not affect QA, ASR, subtitle translation, learning-package generation, artifacts, keyframes, SSE, or task retry/cancel behavior. The chapter module never reads object storage, object keys, local media paths, OCR rows, keyframe images, raw prompts, raw provider responses, tokens, API keys, or secrets.

## VIDEO-CONTEXT-R1 course video context index

VIDEO-CONTEXT-R1 adds a backend context organization layer for long course videos. It creates `course_video_chunk` rows and exposes `GET /api/tasks/{taskId}/video-context` plus `POST /api/tasks/{taskId}/video-context/rebuild`.

The module stays outside the main Runner Pipeline in R1. No pipeline step, MQ topic/tag, async queue, QA behavior change, Chapter behavior change, OCR/keyframe dependency, VLM, Agent loop, embedding, vector database, LLM call, or `ai_call_record` write is introduced.

The backend path is:

1. validate authentication and `taskId + userId` ownership;
2. read persisted subtitles, subtitle translations, existing chapters, learning package, `video_segment.asr_text`, and full-text metadata only as fallback context;
3. create fixed time-window chunks using `COURSELINGO_VIDEO_CONTEXT_CHUNK_WINDOW_SECONDS`;
4. dynamically enlarge the effective window when a long video would exceed `COURSELINGO_VIDEO_CONTEXT_MAX_CHUNKS`;
5. build rule-based summaries, keywords, evidence references, and previews without a model call;
6. on rebuild, delete old `course_video_chunk` rows only after the in-memory build succeeds;
7. return safe DTOs that omit `userId`, object keys, local paths, raw prompts, raw responses, credentials, and full provider payloads.

`course_video_chunk` and `course_chapter` serve different purposes. Chunks are fixed time-window indexes for backend context retrieval and long-video organization. Chapters are semantic chapter timeline records generated on demand by CHAPTER-R1. VIDEO-CONTEXT-R1 does not feed QA or Chapter generation in R1; that integration is intentionally deferred until the index behavior is stable.
