# LectureLens 仓库导览

从[产品介绍](../README.md)进入，用本页定位代码，再用[架构](ARCHITECTURE.md)理解权限、数据与恢复边界。本页源码路径按 `bd142130e79ee60012d89d515b5bc4577d277b60` 核对；描述 main 的实现，不代表维护环境已经部署这些功能。

## 目录与数据归属

| 入口 | 职责 |
| --- | --- |
| [frontend/](../frontend/) | Vue/TypeScript：上传、课程阅读、学习目标、引用跳转、作答和 Trace；经 Java 网关访问服务 |
| [backend/](../backend/) | Java：认证、课程和媒体处理、Evidence 权属/版本/删除检查；MySQL 是课程业务事实权威 |
| [agent-service/](../agent-service/) | Python/FastAPI/LangGraph：学习决策、上下文、工具编排、Session/Run、产物与反馈；PostgreSQL 保存执行状态和派生检索索引 |
| [docs/](./) | 架构、契约、API、部署及历史设计；按[阅读导航](ARCHITECTURE.md#文档阅读导航)区分用途 |
| [eval/](../eval/) | 冻结候选、历史报告、复算记录与失败证据；从[评测索引](../eval/README.md)进入，不把旧成绩作为当前提交的测试结果 |
| [scripts/](../scripts/) | CI、Demo 和评测入口；部分评测会调用真实模型，阅读脚本不等于授权执行 |
| [infra/](../infra/)、[Compose](../compose.yaml)、[Agent Compose](../compose.agent.yml) | 基础服务配置，包括 MySQL、Redis、MinIO、RocketMQ 与独立 Agent PostgreSQL |
| [.github/](../.github/) | CI 与依赖维护；[工作流](../.github/workflows/ci.yml)规定检查入口 |
| 根目录文档与模板 | [AGENTS.md](../AGENTS.md) 是 Coding Agent 工作规则；[测试计划](../TEST_PLAN.md)、[验收报告](../HUMAN_ACCEPTANCE_REPORT.md)、[贡献指南](../CONTRIBUTING.md)和[安全范围](../SECURITY.md)分别说明验证、历史结果、协作与边界。[配置模板](../.env.real-ai.example)不含可直接用于部署的凭据 |

Python 不直接读写 MySQL，Java 不直接写 Agent 表。MinIO 保存媒体和制品，Redis 提供进度及短期协调；这些设施承担的事务、投递和取消边界见[完整架构](ARCHITECTURE.md)。

## 三条核心调用链

以下是核对源码后的主要阅读路径，省略 DTO、Mapper 和 Provider 适配层；箭头跨异步队列或 HTTP 时，并非同一个同步调用栈。

### 1. 视频上传与学习资料准备

1. [Vue 上传状态](../frontend/src/stores/upload.ts)经[上传 API](../frontend/src/api/upload.ts)调用 [UploadSessionController](../backend/src/main/java/com/example/courselingo/upload/controller/UploadSessionController.java) 的分片与 `complete` 接口；合并并存储成功后，另由 [TaskController.create](../backend/src/main/java/com/example/courselingo/task/controller/TaskController.java)创建分析任务。
2. [TaskCreationServiceImpl.create](../backend/src/main/java/com/example/courselingo/task/service/TaskCreationServiceImpl.java)保存任务，通过 [DurableTaskOutbox](../backend/src/main/java/com/example/courselingo/task/service/DurableTaskOutbox.java)异步投递 RocketMQ；[消息处理器](../backend/src/main/java/com/example/courselingo/mq/AnalysisTaskRunnerMessageHandler.java)交给 [AnalysisTaskRunnerImpl](../backend/src/main/java/com/example/courselingo/task/runner/AnalysisTaskRunnerImpl.java)，取得执行资格后进入 [Pipeline.execute](../backend/src/main/java/com/example/courselingo/task/runner/PipelineAnalysisTaskWorkExecutor.java)。
3. [ExtractAudioStep](../backend/src/main/java/com/example/courselingo/task/runner/ExtractAudioStep.java)处理音频；[TranscribeAudioStep](../backend/src/main/java/com/example/courselingo/task/runner/TranscribeAudioStep.java)优先使用覆盖充分的内嵌字幕，否则调用 ASR；[PersistSubtitleSegmentsStep](../backend/src/main/java/com/example/courselingo/task/runner/PersistSubtitleSegmentsStep.java)保存片段，再经[翻译步骤](../backend/src/main/java/com/example/courselingo/task/runner/TranslateSubtitleSegmentsStep.java)和[学习资料步骤](../backend/src/main/java/com/example/courselingo/task/runner/GenerateLearningPackageStep.java)生成结果，课程元数据与制品分别存入 MySQL、MinIO。

FFmpeg 负责媒体处理，ASR 负责语音转写；翻译消费字幕文本。关键帧、OCR/VLM、融合是可配置分支，完整顺序见[步骤定义](../backend/src/main/java/com/example/courselingo/task/runner/PipelineAnalysisTaskStepName.java)。取消、租约失效不能转为降级成功，两路证据均不可用时失败。这是固定准备流程。

回归入口：[Pipeline 单测](../backend/src/test/java/com/example/courselingo/task/runner/PipelineAnalysisTaskWorkExecutorTest.java)、[失败路径](../backend/src/test/java/com/example/courselingo/task/runner/PipelineAnalysisTaskRunnerFailureTest.java)；跨上传、MQ 和制品的[Mock E2E](../scripts/ci/mock-e2e.py)使用确定性 AI。

### 2. Java Evidence 到 Python 检索索引

1. [CourseEvidenceService](../backend/src/main/java/com/example/courselingo/evidence/CourseEvidenceService.java)按 owner/course/revision 物化权威快照；源变更和删除产生同步意图。
2. [EvidenceIndexSynchronizer.synchronize / synchronizeDeletes](../backend/src/main/java/com/example/courselingo/evidence/EvidenceIndexSynchronizer.java)领取持久工作，通过 [DenseEvidenceClient.sync](../backend/src/main/java/com/example/courselingo/qa/service/DenseEvidenceClient.java)签名发送 `PLAN` 清单、`APPLY` 缺失正文或 `DELETE`。
3. [FastAPI sync](../agent-service/src/lecturelens_agent/app.py)验证签名与协议，调用 [Retriever.sync](../agent-service/src/lecturelens_agent/retrieval.py)分块、嵌入，由 [VectorStore.plan / apply / delete](../agent-service/src/lecturelens_agent/store.py)更新 PostgreSQL/pgvector；完整版本发布并确认后才为 READY。

查询走 `Retriever.search`，不会临时建索引；索引未就绪返回冲突，故障明确报告不可用。命中仅是候选 ID，[StudyEvidenceAuthority](../backend/src/main/java/com/example/courselingo/study/StudyEvidenceAuthority.java)仍检查当前所有权、删除状态与 revision，并解析权威正文。协议、重试和版本围栏见[Evidence 同步](L1_EVIDENCE_SYNC.md)。

回归入口：[DenseEvidenceClientTest](../backend/src/test/java/com/example/courselingo/qa/DenseEvidenceClientTest.java)、[test_retrieval.py](../agent-service/tests/test_retrieval.py)；数据库用例需要独立 PostgreSQL/pgvector，skip 不能记作完整通过。

### 3. 学习目标到 Study Agent 产物

1. [CourseAgentPanel](../frontend/src/components/task-detail/CourseAgentPanel.vue)经 [study API](../frontend/src/api/study.ts)提交目标；[StudyController.command / invoke](../backend/src/main/java/com/example/courselingo/study/StudyController.java)解析认证用户，检查课程、revision 和索引状态，再由 [StudyTransport](../backend/src/main/java/com/example/courselingo/study/StudyTransport.java)签名转发。
2. [FastAPI study_command](../agent-service/src/lecturelens_agent/app.py)验证签名并回查 Java 授权；[StudyStore.command](../agent-service/src/lecturelens_agent/study/store.py)幂等创建 Session/Run。[StudyRuntime](../agent-service/src/lecturelens_agent/study/runtime.py)的 worker 领取 Run，运行 LangGraph `decide → tool → decide/结束`。
3. 模型选择检索、补读、受限核算或提交候选；[AuthorityClient](../agent-service/src/lecturelens_agent/study/authority.py)调用 Java Evidence Authority，观察结果回填下一轮决策。证据不足、复核意见或依赖失败影响后续动作；权限、工具和预算由程序约束。
4. 候选复核通过后，由 [StudyStore.save_tool](../agent-service/src/lecturelens_agent/study/store.py)原子保存工具结果和学习产物；可选的[发布审批](STUDY_APPROVAL_RECOVERY.md)先暂存并等待课程所有者决定。事件经 Java SSE 返回 Vue；作答与独立反馈也保存在 Python/PostgreSQL。

模型/工具/token/deadline 预算持久化；取消、权限或版本变化、预算耗尽及不可恢复错误停止执行。checkpoint、调用日志和幂等结果支持恢复，结果不明的外部模型调用可能保守失败；这不保证 Provider 恰好调用一次。细节见[执行说明](L2_STUDY_AGENT.md)与[审批恢复协议](STUDY_APPROVAL_RECOVERY.md)。

回归入口：[StudyControllerTest](../backend/src/test/java/com/example/courselingo/qa/StudyControllerTest.java)、[test_study.py](../agent-service/tests/test_study.py)、[test_study_approval.py](../agent-service/tests/test_study_approval.py)、[Vue 面板测试](../frontend/src/components/task-detail/CourseAgentPanel.test.ts)。确定性 Provider 验证执行协议；真实任务质量另见[冻结 AU](../eval/phase-completion/FINAL_AU.md)，不由这些测试推导。

## 实现、实验与历史证据

| 范围 | 如何理解 |
| --- | --- |
| main 中的实现 | 媒体准备、Evidence 同步、普通课程 QA、Study Agent、作答/反馈及可选审批均有代码；启用条件和具体部署版本须单独核对 |
| 实验能力 | Study Agent 整体仍属实验；审批默认关闭，反馈也受开关控制。冻结 AU 的开发 31/31、新保留 8/8 及 547 项机制测试仅对应原候选、已知公开课程和当时条件 |
| 历史记录 | [评测索引](../eval/README.md)保留失败候选、独立检索对照和机制验收；不能把历史通过数作为本 PR 的成绩，或追认为当前部署质量 |
| 尚未交付 | 自动评分、长期记忆、自动复习调度；未见课程泛化没有系统性验收结论 |

## 版本与部署快照

2026-10-20 的只读核对；这是维护环境的审计快照，后续可能变化。依据为远端 refs、Git 元数据、运行进程与 systemd 入口、release 身份文件和内容哈希；未读取凭据内容、调用模型或改动部署。

| 对象 | 已确认事实与限制 |
| --- | --- |
| P1 的远端 main 基线 | fetch 后为 `bd142130e79ee60012d89d515b5bc4577d277b60`；本次只在独立 worktree 增加文档 |
| 原开发工作树 | `codex/p14-system-model-management`，HEAD `37605e62fbb2da8e54c88d1699feb05c32ebea5c`；与 main 分叉，原工作树 / main 分别有 57 / 2 个独有提交；另有 `provider.py` 修改及 5 个未跟踪文件，保持原样 |
| 运行中 Python | 独立 release，以 `bc2e6cc79f1a3311b90cc4d407f75d2e20048275` 为基础，另有 DeepSeek provider 修改；55 个受跟踪 Python 源文件中，仅 `study/provider.py` 与基础提交不同，其哈希及 `uv.lock` 哈希与 release 声明吻合。不是原样部署该提交 |
| 运行中 Java | 运行独立 JAR，使用独立环境文件和另一工作树的附加配置；未发现可确认提交的 `git.properties`，精确 Git 身份暂未知。JAR SHA-256：`76ae2273273aa5979fe1397efbfa8995e5d722f4c39b6b7ea25728e8019fdd18` |

因此 main 已实现、冻结候选通过验收和维护环境已部署是不同结论。旧文档中按日期记录的“线上 C 未变”“未发布”等只描述当时状态；具体部署行为不能从 main 或历史测试成绩推断。本轮未重新验证服务健康或真实模型质量，也未修改服务、数据库、模型配置或原工作树。

## 公开历史

首次公开提交 [`d3db87b`](https://github.com/a27497/lecturelens/commit/d3db87b679d52aefd231560475fd8eca625b22b1) 是 2026-07-14 的无父提交项目快照：863 个跟踪文件、80,456 行新增、0 行删除，主要为 Java 后端、Vue 前端、测试与文档，当时没有 `agent-service/`。

Python 服务首次出现在公开历史的 [`2f746d2`](https://github.com/a27497/lecturelens/commit/2f746d24cb4046cb68981a9cfa8534081a413ad0)（2026-09-15），先加入检索；后续 [`5fc093f`](https://github.com/a27497/lecturelens/commit/5fc093f0dc6b079a2352299272b11e88d9d0513d)（2026-09-21）收录有界 Study Agent 学习闭环。首次大提交不代表完整开发过程；没有记录支持更早的逐日开发来源，不补造提交历史。

可用 Git 原始元数据复核，不需运行服务：

```bash
git show --format=fuller --shortstat d3db87b679d52aefd231560475fd8eca625b22b1
git ls-tree -r --name-only d3db87b679d52aefd231560475fd8eca625b22b1
git log --reverse --diff-filter=A --format='%H %as %s' -- agent-service
```
