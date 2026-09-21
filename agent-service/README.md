# LectureLens Study Agent — Python 核心服务

当前开发状态（2026-09-20）：学习闭环 Phase 开发与有限范围验收已完成，未发布。冻结 AU：开发严格31/31、新保留严格8/8、独立PostgreSQL机制547项及真实闭环／恢复／权限验收通过，见 [Phase 完成报告](../eval/phase-completion/FINAL_AU.md) 为准。下方各冻结候选的结果是历史记录；线上 C、默认反馈关闭和原账号路由保持不变。

Python/FastAPI + LangGraph + PostgreSQL/pgvector。负责模型工具决策、Context、持久 Session/Run、checkpoint、解释与练习产物，以及本地多语言 Evidence 检索。Java 提供课程、权属、版本与签名入口。职责约束见 [Agent 项目约束](../docs/AGENT_PRODUCT_CONTRACT.md)。

Study Agent 默认关闭，需在 Java/Python 两端显式启用并配置模型。当前处于实验阶段；隔离BC通过本轮有限范围门槛，线上C仍未达标；运行与恢复机制见 [L2 实施说明](../docs/L2_STUDY_AGENT.md)，真实效果见 [L2.2 评测](../docs/L2_QUALITY_EVALUATION.md)。

草稿复核与反馈修订在 Python runtime 中执行，决策与复核共享调用和时间预算；模型复核不保证事实正确。机制与真实试验范围见 [L2 质量修订](../docs/L2_QUALITY_REVIEW.md)。

复核采用仅问题代码的短输出契约，逐字段检查显式引用编号；决策工具格式错误在原预算内最多纠正一次，失败用量可追踪。百炼最新六题开发回归完成 6/6、完整拒答 2/2，但课程内语义仍为 1/4，见 [回归报告](../eval/bailian-pilot/REGRESSION.md)。

上述为线上 C 状态。此前冻结的未发布 BC 实验：`answer_points` 同源生成答案和评分依据；`create_python_practice` 由有界 AST 解释器从同一程序生成输出题、答案和评分点，仍须检查课程支持。`create_interval_practice` 从明确的实数区间和严格反馈生成边界与中点练习，可附已解示例，保留提交条件；模型选择减半或比较重点，工具生成方法说明并原样引用选中的课堂结果；整数专属问题不使用此工具。`create_sequence_practice` 逐轮计算课程方法对应的数组和排序区域，最多8个不同整数、3轮。`check_python_example` 可提供计算观察，禁止导入、I/O、循环及任意方法。拒绝理由/计算记录只在私有工具结果中保存，公开事件不含答案。独立双重求解保留为显式回放实验，默认不启用；实测未证明其收益。线上 C 快照及个人模型连接保持不变，用户已授权仅在隔离测试采用 qwen3-max 生成。BC已完成本轮小样本质量与恢复验收，仍不代表通用自动评分，见 [长任务记录](../eval/l22-completion/README.md)。[M](../eval/reviewer-probe/COURSE_ANSWER_FIRST.md)、[L](../eval/reviewer-probe/FEEDBACK_PRESERVATION.md)、[K](../eval/reviewer-probe/CLAUSE_REVIEW.md)、[J](../eval/reviewer-probe/FIX.md) 和 [D/E](../eval/bailian-pilot/FIELD_REVIEW.md) 历史失败全部保留。现有服务启动源路径固定在 C 快照，勿将普通重启视作候选发布。

后台索引、删除同步、状态与契约升级见 [Evidence 同步](../docs/L1_EVIDENCE_SYNC.md)。

`lecturelens_agent.benchmark` 是隔离的 [Phase A 检索评测入口](../eval/retrieval-phase-a/README.md)，复用 Dense 模型、chunker 和 PostgreSQL 检索；BM25、RRF、多语言 Cross-Encoder 与固定读者仅用于离线消融。其 Torch/Transformers 依赖由独立 eval 环境锁定，生产 app 不导入此模块，默认检索不变。运行方式见 [复现说明](../eval/retrieval-phase-a/REPRODUCE.md)。

运行诊断使用 `python -m lecturelens_agent.study.trace_cli`，支持按 run_id 导出私有 Trace、启动受权新 Run Replay 和对比；复用现有事件与 checkpoint，只增加非索引 `study_event.trace_detail`。CLI 同时需要运维数据库访问和 Java 用户登录；说明、真实失败 Case 和计量边界见 [Phase B](../eval/agent-trace-phase-b/README.md)。

可选 `AGENT_COURSE_TOOL_TRANSPORT=mcp` 启用唯一 Course MCP stdio 集成；默认 `internal`。官方 MCP Client/Server 转发原 Java 签名请求，Server 不持有签名密钥，失败不回退直连。工具、真实端到端结果、故障与复现说明见 [Phase C](../eval/course-mcp-phase-c/README.md)。

完整启动步骤、Java/Python 契约、验证与边界见 [L1 实施文档](../docs/L1_DENSE_RETRIEVAL.md)。

```bash
uv sync --locked
uv run --env-file ../.env.agent.local uvicorn lecturelens_agent.app:create_app --factory --host 127.0.0.1 --port 8090
```

`/healthz` 在模型及数据库初始化后可用。内部端点接受 Java 签名的检索、差量同步和 Study 命令，不接受浏览器用户自报身份。Embedding 使用固定版本的本地 ONNX 权重；Study 的真实 LLM 请求使用配置的 Provider，是否收费由该服务决定。mock 不会作为真实模型失败时的自动回退。

```bash
uv run ruff check src tests
uv run ruff format --check src tests
AGENT_TEST_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_agent_test uv run pytest -q
```

先创建独立测试数据库。测试使用确定性模型/向量夹具；数据库相关用例使用真实 PostgreSQL/pgvector，覆盖取消、幂等、进程退出恢复、持久预算与课程删除。未设置测试数据库地址时这部分用例会 skip，不能将其报告为完整通过。CI 提供真实数据库并执行全部用例。真实 Study 模型验证使用 `scripts/eval/evaluate-study.py`，Java 的 `DenseRetrievalLiveIT` 仅验证检索服务契约。

## 用户模型管理

启用 Study Agent 后，浏览器 `/settings/models` 管理个人连接和决策/复核用途。真实模式可不设置全局 `AGENT_LLM_BASE_URL` / `AGENT_LLM_MODEL`，先启动服务再配置个人模型。全局配置仍可作为只读默认。每个新 Run 冻结模型和加密凭据，编辑连接不改变已创建运行。加密密钥、允许地址和兼容协议见 [模型管理说明](../docs/MODEL_MANAGEMENT.md)。

BC未发布实现补充：检索时模型可选择`python_strings`，随后用`immutability`或`rebinding`概念技能生成字符串方法说明与概念题，避免额外错误类名和对象生命周期结论；其他Python代码仍保留自由概念契约。选择排序概念用`boundary`、`placement`或`progress`技能，说明与应用使用同一模型所选方法，已解示例不得使用相反方法。模型仍选择证据、程序/数组/轮数及工具；这些模板没有来源豁免，只有重新核算匹配的应用答案可移出模型复核视图。旧自由契约仅用于已有记录和测试回放。

## L3.1 作答与证据反馈（未发布）

`study_attempt` 保存不可变的逐题作答版本，`study_feedback` 和 `study_feedback_note` 分别保存模型反馈和用户核对记录；都由课程 Session/Run 的外键链级联清理。新命令经同一签名入口、当前权属与版本校验，不向 MySQL 写学习状态。默认入口、字段和恢复说明见 [学习交互开发](../docs/L3_LEARNING_FLOW.md)。

反馈是新的 `task_kind=feedback` Run，引用精确的 `source_attempt_id`；复用同一队列、Session 单活、模型快照、6模型/8工具/64k预留/90秒预算与 LangGraph checkpoint。通过 `STUDY_FEEDBACK_ENABLED=true` 在 Python **单独启用实验能力**，默认 false；该开关仅控制新反馈请求，不中断已持久化的运行，已有结果和纠正记录仍可读。模型只选来源，程序回填权威原文；模型语义复核与精确引用检查不是自动评分可靠性的证明。

当前新增反馈质量需看 [独立验收](../eval/feedback-v1/README.md)，不能复用 BC 生成练习的质量分数。没有自动成绩、掌握程度标签或长期记忆写入。

2026-09-20 反馈验收完成：冻结 `feedback-P` 在已见MIT课程的新合成作答上开发6/6、新保留8/8通过，另有旧题回归8/8；AI来源核查，仍有一次复核误拒绝，所有历史失败保留。学习入口、不可变作答历史、独立证据反馈和用户核对记录已实现，反馈默认关闭且未部署。该结果不证明未见课程、自动评分或长期记忆能力；详情见 [学习交互验收](../docs/L3_LEARNING_FLOW.md)。


2026-09-20 真实闭环后续验收：实际浏览器上传→新执行出题→作答→反馈→修改→再次反馈，以及重启、调用中断恢复、取消、越权和删除检查已完成；补上取消后查看历史反馈的入口，前端79项及独立PostgreSQL作答/反馈46项通过。未见MIT线性代数课程严格质量仅4/6，提示调整候选Q未改善并已恢复P；四份新课程作答反馈正确不抵消出题/拒答问题。暂未开发同Session自适应后续练习，线上不变。见 [真实学习闭环结果](../eval/learning-loop/RESULTS.md)。

2026-09-20 字段支持修复后续：候选 T 已增加逐字段来源隔离、候选不可见的课程覆盖观察、相邻教学步骤补读和答案匹配记录；独立 PostgreSQL 的完整 Python 测试459项通过。R/S/T对七个已消费目标严格通过4/7、5/7、6/7，最终仍误接受课程未讲授的解集分类。新保留题未消耗，当时工作区T保持实验状态，线上C与原模型路由不变；先修复应用任务与已演示方法的范围对应，再推进新保留验收。见 [字段支持修复结果](../eval/field-support/RESULTS.md)。

2026-09-20 方法范围约束后续：实验候选X新增生成前的课程方法观察、模型选方法及独立范围判断，原交点越界开发问题已通过回归。完整Python测试467项、固定诊断4/4、已消费开发7/7；新保留八题严格质量5/8，仍有双点任务错误拒绝、明确条件遗漏和拒答夹带未教答案。当时的工作区X未发布，线上C和原路由不变；下一步先修复目标条件与拒答正文，再冻结新目标。见 [方法范围结果](../eval/method-scope/RESULTS.md)。
