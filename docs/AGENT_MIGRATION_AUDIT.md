# LectureLens：Agent 升级前技术债评估与清理方案

评估日期：2026-09-11。代码基线：`f71641e`（`main`）。

目标：面向国内 **Agent 应用研发 / AI 后端工程** 岗位，优先提高工程研发岗位的竞争力。模型训练、微调、强化学习、推理内核优化不在本次主线。

本文保留清理前审计结论与源码位置，C0–C3 已进入实施；实际改动与验收结果以 [C0_C3_EXECUTION.md](C0_C3_EXECUTION.md) 为准。后续产品与技术蓝图见 [STUDY_AGENT_BLUEPRINT.md](STUDY_AGENT_BLUEPRINT.md)。代码位置均相对仓库根目录，行号对应上述提交。

## 1. 结论

项目已经具有较完整的视频处理、证据呈现、鉴权和工程测试基础，适合作为 Study Agent 的数据与业务底座。当前最需要解决的是证据质量、事务边界、任务交付可靠性、配置与测试的真实性，以及已有抽象对新 Agent 的限制。

建议保留 Java 视频与业务服务，新增 Python Agent 服务；冻结非必要的媒体算法扩展。清理不以文件数量、测试数量或 Java 代码占比为目标，也不进行全量 Python 重写。

当前问答属于“词法检索 + 证据约束生成”的检索增强问答，可以作为 baseline；尚没有 embedding/vector/hybrid/rerank，也没有模型驱动的工具循环。不能把 LangChain4j 依赖本身视为 Agent 实现。

## 2. 检查范围与验证边界

已检查：构建与依赖、CI、配置与启动脚本、数据库迁移、上传与任务调度关键路径、字幕与视觉证据、融合与学习资料、课程问答、课程上下文、调用记录、前端问答与路由。对关键服务进行了源码路径分析，没有声称逐行审计全部代码。

规模统计采用文件物理行数，包含空行和注释：

| 范围 | 文件数 | 行数 | 解释 |
| --- | ---: | ---: | --- |
| 后端主 Java 源文件 | 621 | 44,481 | 含 DTO、Entity、配置等，数量本身不说明质量 |
| 后端测试 Java 文件 | 203 | 37,962 | 需要保留有业务价值的回归保护 |
| frontend/src | 88 | 9,056 | 包含组件测试 |
| scripts | 14 | 1,751 | 包含已有视觉评估脚本 |

检查环境：Java 21、Node 24。前端 `npm ci`、`npm run test:unit`、`npm run build` 均已执行；36 tests / 12 files 通过，类型检查包含在 build 中。构建存在大 chunk 和第三方 PURE 注释警告，不阻断构建。

后端首轮 `mvn -B test`：1,308 tests，0 failures，1 error，2 skipped；原因均涉及缺少 FFmpeg。已安装 FFmpeg 后进行完整复核，最终结果见本文末尾“最终复核”。首轮环境缺失不归因于业务代码缺陷。

`npm audit --omit=dev` 返回 1 项 high advisory：`nanoid@3.3.16`，路径为 `vite → postcss → nanoid`。Vite 当前被放在 dependencies，所以被生产依赖审计计入；这并不自动证明线上浏览器应用存在可利用漏洞。应更新传递依赖并纠正构建工具分类，重新检查锁文件、构建和实际交付路径。审计原始信息：[GHSA-2v37-7h3g-55p8](https://github.com/advisories/GHSA-2v37-7h3g-55p8)。

README 中的 45:17、68:10 长视频结果属于项目记录的历史验证，标注基线为 `81a300a`。本轮未运行真实外部 ASR/VLM，也未重跑 MySQL、Redis、RocketMQ、MinIO 联合 E2E；不能将单测通过等同于当前提交的真实长视频复验。

## 3. 按优先级处理的债务

优先级为项目清理优先级，不是安全漏洞评级。P0 阻碍可靠基线或会被 Agent 放大；P1 在对应能力接入前处理；P2 随迁移收口。

### D01 · P0 · 长事务包住外部模型请求，QA 失败记录可能被回滚

**源码证据：** `backend/src/main/java/com/example/courselingo/qa/service/CourseQaServiceImpl.java:160` 在 `ask` 上开启事务，方法内查库、调用模型、写成功或失败记录；失败分支在 `:272` 写入后于 `:291` 抛出运行时异常。`LearningPackageServiceImpl.java:174`、`CourseChapterServiceImpl.java:135` 也在事务方法内进行模型生成与修复调用。

**影响：** 外部模型耗时期间占用事务和数据库连接，Agent 多轮调用会进一步放大问题。QA 的 `course_qa_record` 写入在默认 Spring 事务语义下随异常回滚，现有 Mockito 测试验证 insert 调用不能证明失败记录落库。`AiCallRecordServiceImpl` 使用 `REQUIRES_NEW`，因此不能概括成“所有 AI 失败日志都丢失”。这是源码推断，尚未通过真实数据库故障场景复现。

**清理：** 将流程拆为“短事务读取版本快照 → 无事务模型调用 → 短事务校验版本并提交结果”。失败记录由独立持久化服务提交；不要仅给原方法添加 `noRollbackFor`，也不要通过同类自调用期待事务传播生效。写入前重新校验任务未删除、版本未失效、用户仍有权限。

**验收：** 慢模型期间不持有业务事务；模型超时后失败记录仍可查询；旧版本生成结果不能覆盖新版本；并发删除后不能复活结果。用真实事务集成测试覆盖，参考已有 `VisionAnalysisAiCallTransactionIntegrationTest` 的隔离思路。

### D02 · P0 · 课程证据被样本专用规则清洗，OCR 被整体排除

**源码证据：** `qa/service/CourseQaEvidenceSanitizer.java:18` 包含 `{emcee`、`ie ot` 等特定短语正则；`:62` 对 `sourceType=OCR` 直接返回空串，`:75` 跳过“画面文字包括”段。`frontend/src/components/task-detail/CourseQaPanel.vue:62` 起再次按中文前缀、字符比例和类似短语改写或删除证据。

**影响：** 局部坏例子的修复变成全局丢弃规则；即使某张幻灯片 OCR 正确，内容仍可能无法进入 QA。后端和前端分别改变证据，展示内容和模型所见内容也可能不一致。`confidence` 参数被传入清洗函数，但目前没有用于筛选。

**清理：** 保留原始内容，将规范化、OCR 质量、来源与丢弃原因变成结构化字段；读取时根据可解释质量策略过滤。前端只渲染服务端给出的引用文本。特定样本移入 bad-case fixtures，加入不同课程的正确 OCR 与相似术语反例，再替换这些黑名单。

**验收：** 纯幻灯片文字问题能引用正确 OCR；低质 OCR 被降权或排除且保留原因；合法术语不会被样本正则截断；引用文本与最终模型上下文一致。未验证替代策略前不直接取消所有清洗。

### D03 · P0 · 数据库状态与 MQ 投递之间存在故障窗口

**源码证据：** `task/service/TaskCreationServiceImpl.java:121` 的 `create` 先写任务、转为 QUEUED，再调用 MQ；`sendCreatedMessage` 失败仅写 WARN 后抛出。任务与 MQ 路径未发现 outbox 或定时补投机制。Runner 先进入 RUNNING，重启后不能仅凭 Redis claim 自动恢复整个执行。

**影响：** 进程崩溃或 MQ 发送失败可能留下无可消费消息的 QUEUED 任务；消费者去重与 claim 不等于任务可恢复。这是已识别的源码故障窗口，未注入故障复现，不应描述为已观测生产事故。

**清理：** 优先增加事务 outbox：任务状态与待发送事件同事务落库，发布器有界重试并记录投递结果。消费端按事件 ID 和任务执行版本幂等。对陈旧 RUNNING 增加租约/心跳及可解释的恢复策略；先支持安全标记中断并重试，不承诺任意步骤精确续跑。

**验收：** 在入库后、发送前、发送后但确认前分别中断，恢复后最终完成或明确失败；重复消息不重复提交结果；旧 worker 无法覆盖新执行版本。不要用更换 MQ 产品代替修复一致性。

### D04 · P0 · Noop 成功路径应与运行配置隔离

**源码证据：** `task/runner/AnalysisTaskWorkExecutorConfiguration.java` 在 pipeline 关闭或缺省时注入 `NoopAnalysisTaskWorkExecutor`；该类 `execute` 直接返回成功。主配置默认 pipeline 关闭。Demo 和 real-ai 示例显式开启 pipeline，因此不是示例配置必然出错。

**影响：** 组合配置不完整时，启用消费但未开启 pipeline 可能出现“没有执行分析却成功”的状态。

**清理：** 测试桩进入明确 test/demo 范围；生产可接收任务的模式要求真实 executor 和完整依赖，否则启动失败或明确不可用。保留可复现的 mock Demo 与真实模式标签。`DemoAiModeGuard` 也要覆盖两个真实 LLM provider 同时开启的冲突。

**验收：** 对 demo、real、test 和非法组合做配置测试；不存在 real 模式无实际分析但任务成功的路径。不要删除用于指标或可选缓存降级的全部 Noop 类。

### D05 · P1 · 检索、证据、课程上下文尚未形成统一契约

**源码证据：** `qa/service/CourseQaEvidenceRetriever.java:95` 每次读取课程融合段、字幕和译文，在内存进行词法打分；限制候选数在读取和排序之后。`video/context/service/CourseVideoContextBuilder` 独立构建课程 chunks，但 QA 不消费 `course_video_chunk`。`CourseQaEvidenceItem` 用 sourceType + 数据库 sourceId 标识来源。

**影响：** 加 embedding 前如果不统一来源，会积累多套 chunk、质量规则和引文。字幕与融合服务存在 delete-then-insert，数据库自增 ID 不能单独承担长期引用与索引版本标识。现有历史问答存储了证据 JSON，不能因此断言历史展示已全部失效。

**清理：** 建立不可变版本的 `CourseEvidence` 投影；包含 owner、course/task、revision、source_refs、时间范围、模态、原文/规范文本、派生关系、质量信息和内容 hash。Java 保留源数据与访问授权，Python 构建检索投影。`CourseVideoChunk` 转为兼容读取或展示视图，迁移验证后再停写。

**验收：** 同版本重复索引不产生重复；重处理形成新版本；旧引用可标记过期并按既定保留策略解析；课程删除立即禁止查询，索引异步删除有重试与可观测状态。

### D06 · P1 · 双 LLM 实现与抽象能力不匹配

**源码证据：** `ai/llm` 下同时存在手写 HTTP provider 与 LangChain4j provider。`.env.real-ai.example:61` 启用前者；后者由独立开关启用。`LlmMessage` 只有 role/content，`LlmRole` 无 TOOL，`LlmRequest` 无 tool schemas，`LlmResult` 无 tool calls。`docs/ARCHITECTURE.md:21` 写“LangChain4j 编排 / BOM”，实际 POM 直接固定两个依赖版本。

**清理：** Java 媒体 pipeline 暂保留已验证的 HTTP provider；在搜索所有配置入口、确认没有依赖 LangChain4j 的真实运行方式后，删除未采用的适配器、配置和专属测试，并删除相关 Maven 依赖。新增 Python Agent 使用所选框架的标准 tool/message 协议。保留 Java ASR/VLM/批量生成所需的 provider 能力，不为消灭重复而引入跨语言通用 LLM 网关。

**验收：** 真实模式只有一种默认文本 provider；结构化输出、超时、取消、重试仍通过原有契约验证；文档准确描述“现有 pipeline”和“新 Agent runtime”。若决定采用纯 Java 路线，则反过来保留一个成熟框架适配，淘汰重复实现。

### D07 · P1 · 大服务、过多 fallback 与重试预算难以解释

**源码证据：** `SubtitleTranslationServiceImpl` 1,562 行；`TranscribeAudioStep` 1,145 行；`LearningPackageServiceImpl` 916 行；`VideoSegmentFusionServiceImpl` 902 行。学习资料存在生成、修复、fallback；翻译存在拆批、并发、递归拆分与语义重试；模型路由又可设置 attempts/timeout。

**清理：** 按真实职责拆分批次规划、provider 调用、输出校验和持久化，不统一机械拆到每类 200 行。统一一次业务操作的 deadline、最大调用次数和 token/cost 预算；每次尝试可追踪。章节和资料要记录 `generated/repaired/fallback`，避免结构覆盖被误当成内容质量。

**验收：** 限定预算内能结束；重试次数、耗时与费用可从记录复算；fallback 有明确来源；原失败场景仍受测试保护。大文件行数只是拆分线索，不是单独删除理由。

### D08 · P1 · 测试门禁与 README 的验证口径不一致

**源码证据：** `.github/workflows/ci.yml` 后端执行测试，前端只执行 `npm ci` 和 `npm run build`，不执行 `test:unit`。现有视觉脚本有评估价值，但未发现 Agent/RAG 基准数据和基于它们的回归门禁。大量 Java 测试使用 mock/H2，不能证明 MySQL 迁移或 MQ 交付可靠性。

**清理：** 前端补 CI 单测；补从空 MySQL 启动的 Flyway 集成验证、一个固定样例的无外部付费 E2E；真实模型 eval 独立按预算运行。将历史人工验证与当前自动门禁分开，保留数据、模型、配置、提交 hash 和运行结果。

**验收：** CI 能发现前端行为回归、迁移失败、Demo 无结果、引用不可跳转；任务成功与正确回答分别评估。不要为让数字好看而移除失败场景或跳过真实依赖验证。

### D09 · P1 · 删除的外部副作用缺少持久重试边界

**源码证据：** `task/service/TaskBatchDeleteServiceImpl.java:92` 软删除后仍在事务内调用 `cleanupEvidence`；异常只记录 WARN。重复删除会尝试再次清理，但未见保证最终清理的持久任务。

**清理：** 用事务内 tombstone/outbox，提交后清理对象、检索索引及派生数据；各步骤幂等并有失败重试。授权查询先查有效状态，不等待物理清理完成。Agent 引用和 memory 不应继续恢复被删除课程的原文。

**验收：** 存储或索引离线时逻辑删除立即阻断访问；恢复后自动完成清理；数据库回滚不会提前破坏仍有效的数据。

### D10 · P2 · 文档、命名和前端体积债务

**源码证据：** `db/migration/README.md` 仍称未来才添加业务表，实际已有 V1–V21；架构文档保留早期阶段叙述和失实的“请求线程不执行 LLM”承诺。`courselingo`/`CourseLingo Pro` 与 LectureLens 混用。前端所有页面同步导入并全量注册 Element Plus，构建触发大 chunk 警告。

**清理：** 首先修正文档事实和产品展示名称；内部包名、库名、对象前缀可以暂留兼容，不进行全库替换。旧 V21 恢复说明移至历史运维文档并保留入口；已发布迁移不改写。拆分 TaskListView（906 行）的查询、批量操作、展示职责，按路由懒加载；UI 功能迁移时再优化组件引入。

**验收：** 新人可按单一路径运行项目；当前架构文档与代码相符；旧数据库可正常升级；页面行为不回归。

## 4. 保留、重构与删除决策

| 部分 | 决策 | 原因与删除前提 |
| --- | --- | --- |
| auth、资源 Owner Scope、播放/下载授权 | 保留并扩展至 Agent、Evidence、Memory | 这是企业应用工程价值；Python 不能信任模型传入的 userId |
| upload、storage、断点续传、MinIO | 保留并冻结扩展 | 已服务真实视频，不重写成 Python 上传系统 |
| media、ASR、内嵌字幕 | 保留 | 原始时序证据的来源；作为独立 ingestion 能力 |
| OCR、VLM、关键帧 | 保留必要路径，停止继续扩展启发式算法 | 多模态证据是差异化；只处理质量与性能阻塞，不转向 CV 算法项目 |
| adaptive 预算与质量过滤、视觉评估脚本 | 保留经验证能力，减少对外配置面 | 冻结不等于马上删除；删除策略前要有对照结果 |
| subtitle translation | 保留，逐步改为可选后台增强 | 单语课程搜索不必等待全课程翻译；保留双语展示和导出 |
| fusion / VideoSegment | 保留并规范来源 | 不让 LLM 摘要覆盖原始证据；是时序多模态投影的重要基础 |
| chapter、learning package | 重构为可调用/可缓存的学习能力 | 提前生成降为可选，不让所有用户为所有资料等待或付费 |
| CourseVideoChunk/context builder | 收敛到 Evidence 派生视图 | 先确认前端和 API 使用者，再停写并迁移 |
| CourseQaEvidenceRetriever / QueryTermExtractor | 保留为 benchmark，随后替换在线入口 | 时间范围规则可复用；不继续无限添加关键词例外 |
| QA 样本短语黑名单、前端证据改写 | 替代后删除 | 先有质量字段与跨课程回归数据，避免噪声直接进入 prompt |
| CourseQaService / 单轮 QA 页面 | 迁移至 Agent API 与 Workspace 后退役 | 保留旧记录可读和短期接口兼容，避免两套产品长期并行 |
| LangChain4j 适配器与依赖 | Python 主线下的删除候选 | 并非框架不好；当前默认真实路径未使用它，必须核对部署配置 |
| ai_call_record、tracing、metrics | 保留并接入统一 run/trace 关联 |已有 token/耗时记录可扩展；不重复造一套观测平台 |
| RocketMQ、Redis | 先保留 | 修复交付语义比换栈收益更高；不将每个 Agent tool 调用放进 MQ |
| MySQL 与 V1–V21 | 保留 | 新 Agent 可以用独立存储；不为 pgvector 强迁整个 Java 系统 |
| SRT/VTT/Markdown/JSON 导出 | 保留，低优先级维护 | 边际维护成本可控；Markdown/JSON 还可承载学习产物 |
| Demo mock 和重要回归测试 | 保留 | 可复现性资产；与真实运行明确分开 |
| 生产路径中未隔离的 Noop 成功逻辑 | 隔离或删除 | 条件见 D04，不按类名批量删除 |
| 历史阶段文字、失实能力说明 | 更新/归档 | Git 保存历史，不需要长期留在主 README 中 |

## 5. 建议拆成五个可评审变更

| 顺序 | 范围 | 完成标准 |
| --- | --- | --- |
| C0 基线与文档 | 保存复核结果；补前端 CI；依赖分类及传递版本修复；纠正文档 | 真实与 mock 标注清楚；无静默跳过；迁移说明准确 |
| C1 运行与事务边界 | 配置校验、Noop 隔离、QA/章节/资料长事务与失败落库 | 配置错误明确失败；故障记录可查询；旧结果不覆盖新版本 |
| C2 任务与删除可靠性 | outbox、幂等投递、陈旧执行恢复、删除清理任务 | 故障窗口与恢复演示可重复 |
| C3 证据契约 | 来源与版本、质量字段、规范化出口、替代样本黑名单 | API/展示/索引消费同一份可追溯证据 |
| C4 随迁移退役旧入口 | 重复 provider、旧 QA/context 写入、陈旧页面和无用配置 | 新路径覆盖业务用例后才能移除；不是 Agent 开发前的无限大重构 |

迁移顺序是 C0–C3 建立稳定边界后进入 L1/L2；C4 与功能切换同时进行。每个变更同时检查源码引用、反射/Bean、配置、SQL、前端、文档与运行脚本。旧 MQ 消息、持久化 JSON 和已发布数据库迁移的兼容性需要单独验证。

## 6. 最终复核

补齐 FFmpeg 后，重新执行完整 `mvn -B test`：**1,308 tests，0 failures，0 errors，0 skipped，BUILD SUCCESS**，耗时 43.161 秒。前端 36 tests 及 production build 通过。

本次仅新增两份评估/蓝图文档，业务源码、数据库迁移和依赖锁文件未改动。真实模型质量、基础设施联合 E2E、事务故障及 MQ 崩溃恢复仍是后续清理的验证任务。
