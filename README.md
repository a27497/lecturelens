<div align="center">

  <h1>LectureLens</h1>
  <p><strong>基于课程证据的 Study Agent · 实验阶段</strong></p>
  <p>从学习目标出发，选择工具、读取课程证据，生成可追溯的解释与练习，并保存可恢复的执行状态</p>
  <p><em>A course-grounded Study Agent with bounded tools, persistent runs and measurable outcomes.</em></p>
  <p>
    <a href="https://github.com/a27497/lecturelens/stargazers"><img alt="GitHub Stars" src="https://img.shields.io/github/stars/a27497/lecturelens?style=flat-square"></a>
    <img alt="Python 3.12" src="https://img.shields.io/badge/Python-3.12-3776AB?style=flat-square&logo=python&logoColor=white">
    <img alt="LangGraph" src="https://img.shields.io/badge/Agent-LangGraph-1C3C3C?style=flat-square">
    <img alt="PostgreSQL and pgvector" src="https://img.shields.io/badge/PostgreSQL-pgvector-4169E1?style=flat-square">
    <img alt="Java 21" src="https://img.shields.io/badge/Java-21-E76F00?style=flat-square&logo=openjdk&logoColor=white">
    <img alt="Spring Boot 3.5.15" src="https://img.shields.io/badge/Spring%20Boot-3.5.15-6DB33F?style=flat-square&logo=springboot&logoColor=white">
    <img alt="Vue 3.5" src="https://img.shields.io/badge/Vue-3.5-42B883?style=flat-square&logo=vuedotjs&logoColor=white">
    <img alt="MySQL 8.4" src="https://img.shields.io/badge/MySQL-8.4-4479A1?style=flat-square&logo=mysql&logoColor=white">
    <img alt="Redis 8.8" src="https://img.shields.io/badge/Redis-8.8-DC382D?style=flat-square&logo=redis&logoColor=white">
    <img alt="RocketMQ 5.3.4" src="https://img.shields.io/badge/RocketMQ-5.3.4-D77310?style=flat-square">
    <a href="https://github.com/a27497/lecturelens/actions/workflows/ci.yml"><img alt="GitHub Actions CI" src="https://img.shields.io/github/actions/workflow/status/a27497/lecturelens/ci.yml?branch=main&style=flat-square&label=CI"></a>
    <a href="LICENSE"><img alt="MIT License" src="https://img.shields.io/badge/License-MIT-2F855A?style=flat-square"></a>
  </p>
</div>

当前开发状态（2026-09-20）：学习闭环 Phase 开发与有限范围验收已完成，未发布。冻结 AU：开发严格31/31、新保留严格8/8、独立PostgreSQL机制547项及真实闭环／恢复／权限验收通过，见 [Phase 完成报告](eval/phase-completion/FINAL_AU.md) 为准。下方各冻结候选的结果是历史记录；线上 C、默认反馈关闭和原账号路由保持不变。

<p align="center">
  <strong>Model-selected Tools</strong> ·
  <strong>Persistent Runs &amp; Checkpoints</strong> ·
  <strong>20 Real-course Eval Tasks</strong> ·
  <strong>Bounded AU Gate: Passed · Not Released</strong>
</p>

<p align="center">
  <a href="#项目预览">项目预览</a> ·
  <a href="#核心能力">核心能力</a> ·
  <a href="#真实长视频验证">真实验证</a> ·
  <a href="#系统流程">系统流程</a> ·
  <a href="#安装概览">安装使用</a>
</p>


L2.1 已实现可恢复的解释／出题执行与学习助手入口，见 [Study Agent 实施说明](docs/L2_STUDY_AGENT.md)。经过 BC、feedback-P、X、AN、AT 等历史候选迭代后，当前冻结 AU 已完成本轮有限范围学习闭环验收：开发31/31、全新保留8/8、547项机制测试及真实作答反馈/恢复/权限边界通过；候选仍未发布，自动评分、长期记忆和复习调度尚未实现，见 [AU 完成报告](eval/phase-completion/FINAL_AU.md)。

Evidence 后台增量更新、删除重试和索引状态已实现；部署及 L2 接入边界见 [Evidence 同步](docs/L1_EVIDENCE_SYNC.md)。

## 项目预览

> 以下截图使用合成测试数据生成，不包含真实账号、私人视频、API Key 或服务地址。

### 课程阅读与学习结果

![LectureLens 课程阅读与学习结果：视频、双语时间轴、学习资料、问答与下载入口](docs/images/lecturelens-course-reading.webp)

| 上传课程 | 我的课程 |
| :---: | :---: |
| ![LectureLens 分片上传与课程配置页面](docs/images/lecturelens-upload.webp) | ![LectureLens 课程任务列表与状态筛选页面](docs/images/lecturelens-course-list.webp) |

<details>
<summary>查看上传、任务处理和登录等辅助页面</summary>

| 异步任务处理 | 产品首页 |
| :---: | :---: |
| ![LectureLens 异步任务处理进度页面](docs/images/lecturelens-processing.webp) | ![LectureLens 产品首页与使用步骤](docs/images/lecturelens-home.webp) |

![LectureLens 注册与登录页面](docs/images/lecturelens-login.webp)

</details>

## 项目定位

LectureLens 以课程学习任务为主线：用户提出目标，Python Agent 根据证据和工具结果选择下一步，生成带引用的解释与练习；执行状态可追踪、取消和恢复。Java 提供课程摄取、权属与版本校验、Evidence 和鉴权入口，Vue 呈现学习任务与产物。

当前已实现受限工具循环与持久 Session/Run，仍处于实验阶段。真实课程评测暴露了错误答案、引用支持不足与拒答失败；作答评分、长期学习记忆和复习调度尚未实现。项目职责与后续验收标准见 [Agent 项目约束](docs/AGENT_PRODUCT_CONTRACT.md)。

## 核心能力

### 1. 基于目标的 Agent 执行

- **统一模型管理**：每个账号独立配置服务连接与密钥，分别指定决策和复核模型；新 Run 冻结所选版本。提供 25 个服务/地域预设、常用模型快捷添加、带用途说明和版本折叠的模型发现（默认筛选课程 Agent 候选）、主动工具调用测试；预设不代表兼容性或教学质量已通过验收，见 [模型管理](docs/MODEL_MANAGEMENT.md)。百炼最新六题开发回归完成 6/6、完整拒答 2/2，但课程内语义仅 1/4，质量仍未过关，见 [回归报告](eval/bailian-pilot/REGRESSION.md)。
- **模型选择工具**：使用标准 `tool_calls`，检索后可以补读证据、保存解释与两道练习，或报告证据不足；工具结果回填下一次模型决策。
- **草稿复核与修订（实验）**：模型提交答案要点，Python 同源生成答案与评分依据；代码输出题可由受限解释器计算答案。拒绝反馈保留课程证据并驱动预算内修订。线上仍为 C；此前冻结BC已完成本轮L2.2验收：20/20正确类型、16/16内容合格、4/4正确拒答，391项机制测试及恢复／浏览器／删除检查通过。该结果仅涵盖已见课程上的新目标，AI来源核查，不证明通用自动评分能力；候选未发布。见 [长任务进度](eval/l22-completion/README.md)、[验收条件](docs/L2_PHASE_COMPLETION.md)及 [历史复核试验](docs/L2_QUALITY_REVIEW.md)。
- **受限且可恢复**：LangGraph + PostgreSQL 保存 Session、Run、工具结果、事件与 checkpoint；约束调用次数、时间、引用和课程版本，支持取消及幂等恢复。
- **学习产物**：解释和练习带课程时间引用；参考答案按需读取，刷新后恢复服务端产物。
- **学习交互（未发布）**：学习助手作为课程默认入口；真实作答可保存、刷新恢复和查看修改记录。证据反馈单独保存，支持核对与纠正；默认关闭；冻结 feedback-P 开发6/6、全新保留作答8/8通过（AI来源核查、已见课程），历史失败保留，质量验收独立于 BC，见 [L3.1 进度](docs/L3_LEARNING_FLOW.md) 与 [反馈评测](eval/feedback-v1/README.md)。
- **效果可检查**：固定真实课程任务、逐题来源复核、失败记录及延迟报告。历史本地配置与 BC 等候选结果继续保留；当前冻结 AU 在已见课程的新目标上开发严格31/31、全新保留严格8/8，并完成547项机制测试与真实闭环/恢复/权限验收。该结果不代表未见课程泛化或自动评分能力，见 [AU 完成报告](eval/phase-completion/FINAL_AU.md)。

实现与复现入口：[Agent runtime](agent-service/src/lecturelens_agent/study/runtime.py)、[工具协议](agent-service/src/lecturelens_agent/study/contracts.py)、[L2 说明](docs/L2_STUDY_AGENT.md)、[真实评测](docs/L2_QUALITY_EVALUATION.md)。

### 2. 🎬 课程准备与视频任务链路

> 大文件上传与长耗时分析不占用请求主链路，任务状态可以恢复，也不会被重复消费。

- **上传与存储**：分片上传支持缺失分片查询和断点续传；合并前核验大小、MD5、实际分片和媒体头，原始媒体与制品写入 MinIO。
- **异步执行**：RocketMQ 投递分析任务，有界 Runner 控制并发；MySQL 保存业务事实、outbox 和执行租约，Redis claim 提供快速去重及短期进度缓存。
- **任务控制**：支持取消、失败重试、状态筛选和终态逻辑删除；SSE 断开后按有界退避重连，终态只触发一次详情刷新。

### 3. 🧩 时序多模态课程证据

> 字幕、画面文字、视觉描述和时间戳最终汇入同一条课程时间线。

- **字幕来源**：优先使用覆盖充分的内嵌字幕；字幕缺失或覆盖不足时调用 SiliconFlow ASR。
- **画面证据**：自适应关键帧规划过滤模糊、黑屏、空白和重复画面，再按预算执行可选 OCR 与有界 VLM。
- **时间线融合**：原文、译文、OCR、视觉描述和时间范围统一对齐；视觉分支不可用时，已有字幕主链仍可继续。

```text
[19:00–20:00]
Transcript   ...
Translation  ...
Visual       ...
Evidence     timestamp / keyframe
```

### 4. 📚 有时间证据的学习工作区

> 阅读、学习和问答都能回到原视频的具体时间范围。

- **边看边读**：视频、原文和译文在同一页面呈现，点击字幕、章节或证据即可跳转播放位置。
- **结构化资料**：生成覆盖课程首尾的章节，以及摘要、重点、术语和预生成问答。
- **问答与导出**：用户完成任务后按需发起课程范围问答；没有明确证据时拒答，并可下载 SRT、VTT、Markdown 和 JSON。

### 5. 🛡️ 可观测、可恢复与安全边界

> 外部 AI 可能超时、部分失败或返回无效结构，系统需要留下可诊断记录，同时守住凭据边界。

- **身份与资源**：JWT access/refresh rotation，Refresh Token 哈希存储；上传、播放、证据和制品下载统一执行 Owner Scope。
- **失败可追踪**：AI 调用记录保留阶段、Provider、模型、状态、次数与耗时；章节、视觉结果和学习资料通过校验后原子替换。
- **敏感信息控制**：Credential Leak Detector 区分课程术语与真实凭据；日志和 API 不暴露密钥、对象存储 key、本地路径、Prompt 或原始响应。

## 真实长视频验证

### 场景 A｜45:17 真实外部 ASR + VLM

| 指标 | 结果 |
| --- | --- |
| 视频与许可 | [Bare-Bones Basics of Full-Text Search](https://commons.wikimedia.org/wiki/File:BareBonesSearch.webm)，Wikimedia Commons，CC BY-SA 4.0 |
| 媒体 | 45:17，WebM，39.5 MB |
| 处理耗时 | `00:07:58` |
| 转写 | SiliconFlow ASR 成功；原文 / 译文 / 融合段为 46 / 46 / 46 |
| 视觉证据 | 关键帧 58；OCR 58/58；Qwen3-VL 44/44 |
| 章节 | 11 章，覆盖 `00:00:00–00:45:17`；时间轴空档 0 |
| 课程问答 | 返回 `19:00–20:00` 的课程证据 |
| 导出 | SRT、VTT、Markdown、JSON 全部成功 |

### 场景 B｜68:10 内嵌字幕长视频

| 指标 | 结果 |
| --- | --- |
| 媒体 | 68:10，H.264 1080p，381.7 MB |
| 字幕 | 1461 个内嵌字幕 cues |
| 融合与关键帧 | 最终融合段 69；关键帧 240 |
| 章节 | 时间轴覆盖 100%；最大空档 0 |
| 课程问答 | 课程内问题返回时间证据；课程外问题拒答 |
| 导出 | SRT、VTT、Markdown、JSON 全部成功 |

以上数据来自特定本地环境和模型配置，用于证明链路真实跑通，不代表性能、费用或时延 SLA。

验证基线：`main@81a300a`

上述长视频历史基线的自动化门禁：Backend `1308 tests`；Frontend `12 files / 36 tests`。当前 Agent/Python、Java 和前端验证见下方「测试与质量保障」；长视频摄取成功不代表 Agent 学习任务质量合格。

## 系统流程

### Agent 学习任务主流程

```mermaid
flowchart LR
    U[用户学习目标] --> W[Vue 学习助手]
    W --> J[Java 鉴权与课程就绪校验]
    J --> P[Python LangGraph Run]
    P --> M[模型决策]
    M --> T[工具参数、权限、版本与预算校验]
    T --> E[检索或补读 Java 权威 Evidence]
    E -->|工具结果与有界上下文| P
    T --> R[草稿与独立上下文模型复核]
    R -->|未通过：反馈修订，最多两份草稿| P
    R -->|通过| A[保存解释与练习或证据不足终态]
    P <--> D[(PostgreSQL Session / Run / checkpoint)]
    A --> D
    A -->|事件与产物经 Java 返回| W
```

模型在受限工具集中选择动作；代码负责工具授权、状态一致性及停止约束。当前范围是单课程解释与出题，复杂规划和学习记忆仍需后续验收。

### 课程准备流程

以下确定性流程提前准备 Evidence 和索引，供 Agent 使用。

<details>
<summary>查看媒体摄取、存储与普通课程 QA 链路</summary>

```mermaid
sequenceDiagram
    autonumber
    actor User as 用户
    participant Web as Vue 工作区
    participant API as Spring Boot API
    participant Store as MinIO
    participant MQ as RocketMQ
    participant Runner as Analysis Runner
    participant MediaAI as 媒体与 AI Provider
    participant State as MySQL + Redis

    User->>Web: 选择课程并分片上传
    Web->>API: 上传分片并完成媒体校验
    API->>Store: 保存原始视频
    API->>State: 同事务写任务与 outbox
    State->>MQ: 后台发布已提交事件
    API-->>Web: 返回任务状态
    MQ->>Runner: 异步消费
    Runner->>MediaAI: FFmpeg / FFprobe 解析媒体
    alt 内嵌字幕覆盖充分
        MediaAI-->>Runner: 返回内嵌字幕
    else 字幕缺失或覆盖不足
        Runner->>MediaAI: 调用 SiliconFlow ASR
        MediaAI-->>Runner: 返回转写结果
    end
    Runner->>MediaAI: 关键帧、可选 OCR / VLM
    MediaAI-->>Runner: 返回画面证据
    Runner->>MediaAI: 翻译、融合、章节与学习资料
    MediaAI-->>Runner: 返回结构化结果
    Runner->>State: 写入业务结果与进度
    Runner->>Store: 保存证据图与导出制品
    Runner-->>Web: SSE 推送进度和终态
    Web-->>User: 展示课程结果
    opt 任务完成后的按需课程问答
        User->>Web: 提交当前课程问题
        Web->>API: 请求课程问答
        API->>State: 读取已保存课程证据
        State-->>API: 返回证据时间段
        API->>MediaAI: 基于证据生成回答
        MediaAI-->>API: 返回回答
        API-->>Web: 返回答案与时间证据
    end
```

</details>

MySQL 保存课程业务事实，PostgreSQL 保存 Agent 执行状态与派生索引；Redis 负责摄取任务的短期协调，MinIO 保存媒体与制品。详细职责见 [Agent 项目约束](docs/AGENT_PRODUCT_CONTRACT.md) 和 [架构设计](docs/ARCHITECTURE.md)。

## 技术栈

| 层次 | 技术 | 用途 |
| --- | --- | --- |
| Agent 核心 | Python 3.12、FastAPI、LangGraph、PostgresSaver | 模型工具循环、Context、Run、checkpoint、学习产物与执行事件 |
| Agent 状态与检索 | PostgreSQL、pgvector、本地多语言 Embedding | 学习状态、Evidence 增量索引与课程内检索 |
| Web | Node.js 24 LTS、Vue 3.5.39、TypeScript 5.9.3、Vite 8.1.0、Pinia 3.0.4、Element Plus 2.14.2 | 上传、播放、双语时间轴、学习资料和状态恢复 |
| 业务与 Evidence API | Java 21、Spring Boot 3.5.15、MyBatis-Plus 3.5.16、Flyway | 鉴权、课程摄取、权威证据与版本、签名网关和业务迁移 |
| 异步与状态 | RocketMQ 5.3.4、Redis 8.8.0、SSE | 任务投递、防重复 claim、短期进度和前端事件流 |
| 数据与对象存储 | MySQL 8.4 LTS、MinIO `RELEASE.2025-04-22T22-12-26Z` | 业务事实、原始媒体、证据图和生成制品 |
| 媒体与 AI | FFmpeg/FFprobe 8.0.3、Tesseract OCR、SiliconFlow ASR、OpenAI-compatible LLM/VLM、LangChain4j 1.17.0 | 媒体解析、转写、翻译、视觉理解和结构化生成 |
| 测试与部署 | JUnit 5、Mockito、AssertJ、Vitest 4.1、vue-tsc、GitHub Actions、Docker Compose v2 | 自动化回归、类型检查、构建和本地中间件编排 |

## 安装概览

1. 克隆仓库。
2. 将 `.env.real-ai.example` 复制为未跟踪的 `.env`。
3. 填写自己的基础设施密码和 AI Provider 凭据。
4. 启动课程基础设施、Java 和前端；按下方步骤配置 Python Agent 与 PostgreSQL。
5. 注册本地账号，上传课程视频；处理成功且 Evidence 索引 READY 后，在「学习助手」中提交学习目标。

```bash
git clone https://github.com/a27497/lecturelens.git
cd lecturelens
cp .env.real-ai.example .env
docker compose --env-file .env up -d
npm --prefix frontend ci
npm --prefix frontend run dev
```

启动后端前需要将 `.env` 安全加载到当前进程。完整的 Windows、Linux/macOS、AI Provider、端口映射、停止和故障排查步骤见[本地部署指南](docs/DEPLOYMENT.md)。

### 启动实验阶段 Study Agent

需要 Python 3.12、uv，以及已配置的支持标准工具调用的模型服务。将 `.env.agent.example` 复制为 `.env.agent.local`，生成独立服务密钥，填写模型地址和模型名；在 Java/Python 两端启用 `STUDY_AGENT_ENABLED=true`，共享相同的 `AGENT_SERVICE_SECRET`。将其中 Java 配置项加载到 Java 进程后再启动 Java。模型配置可能产生外部服务费用，固定 mock 仅用于流程演示。

```bash
cp .env.agent.example .env.agent.local
# 先填写上述配置；示例默认保持 Agent 关闭。
docker compose -f compose.agent.yml up -d
cd agent-service
uv sync --locked
uv run --env-file ../.env.agent.local uvicorn lecturelens_agent.app:create_app --factory --host 127.0.0.1 --port 8090
```

完整的双服务配置和质量限制见 [Agent 服务](agent-service/README.md)、[Evidence 同步](docs/L1_EVIDENCE_SYNC.md) 和 [L2 运行说明](docs/L2_STUDY_AGENT.md)。

## 测试与质量保障

| 检查项 | 结果 |
| --- | --- |
| Agent / Python | 102 tests passed，含真实 PostgreSQL、模型隔离/快照与草稿修订恢复 |
| Java 业务与证据服务 | 1365 tests passed |
| Frontend | 16 files / 52 tests passed |
| TypeScript | passed |
| Production build | passed |
| 真实模型质量 | 隔离冻结BC通过本轮小样本门槛；线上C未变，未证明跨课程泛化，独立于机制测试 |

默认自动化测试使用 Mock、Fake 或禁用配置，不依赖真实 AI Key。CI 在 `push` 和 `pull_request` 上运行 Agent Python lint/测试（真实 PostgreSQL/pgvector）、Java 测试、前端单测/构建/依赖审计，以及摄取基础设施的 Mock E2E。真实模型任务评测单独执行，不能用测试夹具代替模型质量。历史清理验证见 [C0–C3 执行记录](docs/C0_C3_EXECUTION.md)，课程质量评测见 [L2.2 验证摘要](eval/study-v1/verification.json)，本轮模型管理测试与真实本地连接验收见 [模型管理验证摘要](eval/model-management/verification.json)。

<details>
<summary>查看本地测试命令</summary>

```bash
# Agent：使用独立测试数据库，避免与后台 worker 共用队列。
AGENT_TEST_DATABASE_URL=postgresql://.../lecturelens_agent_test uv run --directory agent-service pytest -q
```

```powershell
# 后端
cd backend
.\mvnw.cmd test

# 前端
cd ..\frontend
npm ci
npm run test:unit
npm run type-check
npm run build
npm audit --omit=dev --audit-level=high
```

</details>

## 项目结构

```text
LectureLens/
├── agent-service/        # Python Agent 核心、工具、Context、Run、索引与测试
├── eval/study-v1/        # 固定课程任务、来源与质量报告
├── backend/              # Java 鉴权、课程摄取、权威 Evidence 与签名网关
├── frontend/             # Vue 学习目标、执行状态、产物与课程阅读
├── infra/                # RocketMQ 本地配置
├── scripts/eval/         # 真实课程下载、Agent 评测、浏览器验收与清理
├── scripts/vision/       # 合成课程视频与离线视觉评测
├── docs/
│   ├── DEPLOYMENT.md     # Windows、Linux/macOS 与 AI Provider 配置
│   └── ARCHITECTURE.md   # 模块、状态机与事务边界
├── AGENTS.md             # 后续开发的 Agent 主线与职责约束
├── compose.agent.yml     # Agent PostgreSQL/pgvector
├── compose.yaml          # 课程业务基础设施
└── .env.real-ai.example  # 真实 Provider 配置模板
```

部分内部 package 和标识为兼容既有代码与数据库而保留 `courselingo` 前缀，clone 后无需重命名。

## 安全与能力边界

- 基础设施和第三方 AI 请求使用部署者自己的密码与 API Key；`.env`、媒体、日志和生成物不得提交到仓库。
- 普通课程 QA 保持单轮 RAG 路径；学习助手由 Python Agent 负责受限工具循环和持久执行。
- 已使用多语言 Embedding、pgvector 与 LangGraph；工具权限限定在当前用户、课程与证据版本。
- 隔离BC通过本轮有限范围L2.2门槛；线上C仍未达标，候选未发布。自动评分、长期学习记忆与复习安排尚未实现。
- 当前仓库面向可复现的本地部署，不承诺商业多租户隔离、在线 SaaS 可用性或性能 SLA。

漏洞报告和安全非目标见[安全策略](SECURITY.md)。启用 OCR 或视觉分析前，部署者应确认第三方服务条款、调用费用和数据合规要求。

## 相关文档

- [本地部署指南](docs/DEPLOYMENT.md)
- [架构设计](docs/ARCHITECTURE.md)
- [API 契约](docs/API.md)
- [数据库设计](docs/DB_SCHEMA.md)
- [自适应课程画面理解与离线评测](docs/ADAPTIVE_VIDEO_UNDERSTANDING_R1.md)
- [前端 UX](docs/FRONTEND_UX.md)
- [测试计划](TEST_PLAN.md)
- [Evidence RAG 评测素材与标注准备](eval/pilot-v1/README.md)
- [L1 Python 向量检索：启动、契约与验证](docs/L1_DENSE_RETRIEVAL.md)
- [L1 真实课程验收与已知限制](docs/L1_REAL_COURSE_ACCEPTANCE.md)
- [安全策略](SECURITY.md)
- [贡献指南](CONTRIBUTING.md)

<details>
<summary>本地离线视觉评测</summary>

仓库提供只依赖 Python 标准库和本机 FFmpeg/FFprobe 的合成视频与三策略评测脚本，命令和取舍见上方自适应课程画面理解文档。

</details>

## 参与贡献

欢迎提交范围清楚、可以复核的 Pull Request。提交前请运行与改动相关的检查，并确认没有凭据、大型媒体或生成目录；约定见[贡献指南](CONTRIBUTING.md)。

## License

许可协议详见 [MIT License](LICENSE)。


2026-09-20 真实闭环后续验收：实际浏览器上传→新执行出题→作答→反馈→修改→再次反馈，以及重启、调用中断恢复、取消、越权和删除检查已完成；补上取消后查看历史反馈的入口，前端79项及独立PostgreSQL作答/反馈46项通过。未见MIT线性代数课程严格质量仅4/6，提示调整候选Q未改善并已恢复P；四份新课程作答反馈正确不抵消出题/拒答问题。暂未开发同Session自适应后续练习，线上不变。见 [真实学习闭环结果](eval/learning-loop/RESULTS.md)。

2026-09-20 字段支持修复后续：候选 T 已增加逐字段来源隔离、候选不可见的课程覆盖观察、相邻教学步骤补读和答案匹配记录；独立 PostgreSQL 的完整 Python 测试459项通过。R/S/T对七个已消费目标严格通过4/7、5/7、6/7，最终仍误接受课程未讲授的解集分类。新保留题未消耗，当时工作区T保持实验状态，线上C与原模型路由不变；先修复应用任务与已演示方法的范围对应，再推进新保留验收。见 [字段支持修复结果](eval/field-support/RESULTS.md)。

2026-09-20 方法范围约束后续：实验候选X新增生成前的课程方法观察、模型选方法及独立范围判断，原交点越界开发问题已通过回归。完整Python测试467项、固定诊断4/4、已消费开发7/7；新保留八题严格质量5/8，仍有双点任务错误拒绝、明确条件遗漏和拒答夹带未教答案。当时的工作区X未发布，线上C和原路由不变；下一步先修复目标条件与拒答正文，再冻结新目标。见 [方法范围结果](eval/method-scope/RESULTS.md)。
