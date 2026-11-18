# 文档索引

`docs/` 下的文档分三类。**当前说明**描述 main 上的代码行为；**实验记录**描述一次具体实验或实验性功能的设计与结果；**历史**是已经被替代的方案、清理记录或某一次环境的操作说明，保留用于追溯，不代表当前状态。

本索引只做分类，没有移动或删除任何文件，所以外部链接不会断。评测证据在 [`eval/`](../eval/README.md)。

## 先看这几篇

| 文档 | 用途 |
| --- | --- |
| [项目主页](../README.md) | 定位、演示、质量结果、怎么跑起来 |
| [设计取舍](DESIGN_TRADEOFFS.md) | 主要架构选择、放弃了什么、证据在哪 |
| [仓库导览](PROJECT_MAP.md) | 目录职责、三条调用链的源码与回归测试入口 |
| [架构](ARCHITECTURE.md) | 组件、数据所有权、Evidence 与 Agent 生命周期、故障边界 |

## 当前说明

| 文档 | 内容 |
| --- | --- |
| [AGENT_PRODUCT_CONTRACT.md](AGENT_PRODUCT_CONTRACT.md) | Study Agent 的产品与架构契约（Java / Python 分工、验收口径） |
| [ARCHITECTURE.md](ARCHITECTURE.md) | 当前架构 |
| [API.md](API.md) | HTTP 接口 |
| [DB_SCHEMA.md](DB_SCHEMA.md) | MySQL 与 PostgreSQL 表结构 |
| [DEPLOYMENT.md](DEPLOYMENT.md) | 手动部署与真实 Provider 配置 |
| [QUICKSTART.md](QUICKSTART.md) | 只起 Java 媒体链路的无 Key 演示 |
| [L1_EVIDENCE_SYNC.md](L1_EVIDENCE_SYNC.md) | Java → Python Evidence 增量同步与索引状态 |
| [L2_STUDY_AGENT.md](L2_STUDY_AGENT.md) | Study Agent 工具契约、上下文和恢复 |
| [L2_QUALITY_REVIEW.md](L2_QUALITY_REVIEW.md) | 练习草稿复核与有界修订 |
| [L3_LEARNING_FLOW.md](L3_LEARNING_FLOW.md) | 作答、反馈与学习交互 |
| [STUDY_APPROVAL_RECOVERY.md](STUDY_APPROVAL_RECOVERY.md) | 可选发布审批与崩溃恢复协议 |
| [STUDY_METRICS.md](STUDY_METRICS.md) | Study Run 持久指标的口径与报表工具 |
| [AGENT_CONCURRENCY.md](AGENT_CONCURRENCY.md) | Run 并发通道与检索并发配置 |
| [LEARNING_SCOPE.md](LEARNING_SCOPE.md) | 课程问答与 Agent 共用的学习范围 |
| [LEARNING_WORKSPACE.md](LEARNING_WORKSPACE.md) | 课程学习工作区的布局与恢复方式 |
| [COURSE_POSITION.md](COURSE_POSITION.md) | 视频与原文时间轴的双向定位 |
| [LEARNING_PACKAGE_CONTEXT.md](LEARNING_PACKAGE_CONTEXT.md) | 学习资料生成的上下文预检 |
| [MODEL_MANAGEMENT.md](MODEL_MANAGEMENT.md) | 用户模型连接与 Agent 模型用途 |
| [SYSTEM_MODEL_MANAGEMENT.md](SYSTEM_MODEL_MANAGEMENT.md) | Java 系统级模型配置（默认关闭） |
| [MODEL_USAGE.md](MODEL_USAGE.md) | 课程页的只读模型使用记录 |
| [ASR_BAILIAN.md](ASR_BAILIAN.md) | 百炼同步 ASR 配置 |
| [DEEPSEEK_JAVA_PROTOCOL.md](DEEPSEEK_JAVA_PROTOCOL.md) | Java 侧 DeepSeek 请求与输出协议 |
| [EVAL_CLI.md](EVAL_CLI.md) | 实验准备与证据查询 CLI |
| [LOCAL_CHECK_EXECUTION.md](LOCAL_CHECK_EXECUTION.md) | 长时间本地检查的进程监督与收尾 |
| [PRODUCT_STAGES.md](PRODUCT_STAGES.md) | 阶段路线（仓库内副本） |
| [PRODUCT_GALLERY.md](PRODUCT_GALLERY.md) | 产品截图的来源、版本与授权说明 |
| [FRONTEND_UX.md](FRONTEND_UX.md) | 前端交互约定 |

## 实验记录（实验性功能或一次实验的设计与结果）

| 文档 | 内容 |
| --- | --- |
| [LIGHT_TUTOR.md](LIGHT_TUTOR.md) | 轻量课程 Tutor（L4 中正确率最高的路径） |
| [LIGHT_TUTOR_TRIAL.md](LIGHT_TUTOR_TRIAL.md) | Light Tutor 正常用户试学（单用户、需费用授权） |
| [P8_TUTOR.md](P8_TUTOR.md) | 多轮课程 Tutor（只有 Mock） |
| [P7_EVIDENCE_FLASHCARDS.md](P7_EVIDENCE_FLASHCARDS.md) | 证据闪卡与 FSRS 复习调度（只有 Mock） |
| [P9_EVIDENCE_CHOICE.md](P9_EVIDENCE_CHOICE.md) | 课程证据选择题与程序判分（只有 Mock） |
| [P10_CHOICE_REVIEW.md](P10_CHOICE_REVIEW.md) | 答错待回看 |
| [B1_WORKSPACE.md](B1_WORKSPACE.md) | 材料与学习并置的默认工作区 |
| [SUBTITLES_READY_LEARNING.md](SUBTITLES_READY_LEARNING.md) | 字幕就绪即可开始学习 |
| [PIPELINE_TRANSLATION_V2.md](PIPELINE_TRANSLATION_V2.md) | 全文翻译 v2 候选（未部署） |
| [ADAPTIVE_VIDEO_UNDERSTANDING_R1.md](ADAPTIVE_VIDEO_UNDERSTANDING_R1.md) | 自适应关键帧与视觉证据的离线评测 |
| [OFFLINE_COST_EVALUATION.md](OFFLINE_COST_EVALUATION.md) | Study 费用的离线评估 |
| [L1_DENSE_RETRIEVAL.md](L1_DENSE_RETRIEVAL.md) | 第一条 Dense 检索链路的实现记录 |
| [L1_REAL_COURSE_ACCEPTANCE.md](L1_REAL_COURSE_ACCEPTANCE.md) | 真实课程 QA 小规模验收（2026-09-15） |
| [L2_QUALITY_EVALUATION.md](L2_QUALITY_EVALUATION.md) | Study 真实课程质量与延迟评测 |
| [L2_MODEL_SELECTION_PLAN.md](L2_MODEL_SELECTION_PLAN.md) | 决策/复核模型选型准备 |
| [L2_PHASE_COMPLETION.md](L2_PHASE_COMPLETION.md) | Study 长任务验收记录 |
| [DESKTOP_LEARNING_REVIEW.md](DESKTOP_LEARNING_REVIEW.md) | 桌面端学习流程走查 |

## 历史（已被替代或只对应当时环境）

| 文档 | 内容 |
| --- | --- |
| [STUDY_AGENT_BLUEPRINT.md](STUDY_AGENT_BLUEPRINT.md) | 早期 Study Agent 升级蓝图 |
| [AGENT_MIGRATION_AUDIT.md](AGENT_MIGRATION_AUDIT.md) | Agent 升级前的技术债评估 |
| [C0_C3_EXECUTION.md](C0_C3_EXECUTION.md) | 可靠性清理（C0–C3）执行记录 |
| [REPOSITORY_CLOSEOUT.md](REPOSITORY_CLOSEOUT.md) | 仓库收尾与 CI MinIO 源码构建记录 |
| [LOCAL_FLYWAY_V21_RECOVERY.md](LOCAL_FLYWAY_V21_RECOVERY.md) | 一台开发机旧 V21 库的恢复步骤 |

`docs/verification/` 保存三次历史 PR 的浏览器验证截图；`docs/images/` 是 README 与截图说明使用的图片；`docs/media/` 是演示录屏。
