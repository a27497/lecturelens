# L2.1：可恢复的解释与出题闭环

日期：2026-09-15。实现边界：单课程、短会话、解释与两道练习。前置索引见 [Evidence 同步](L1_EVIDENCE_SYNC.md)。

## 已实现的行为

课程详情新增「学习助手」。用户输入目标，Java 核验当前用户、课程存在、处理成功及索引 READY；Python 创建 Session / Run，后台运行 LangGraph。模型通过标准 chat-completions `tool_calls` 选择工具，结果经过参数、引用、版本和预算校验后保存。模型消息使用标准 assistant tool_calls / tool_call_id 配对返回工具结果；不会用普通用户消息冒充工具返回。

线上 C 保持原四个工具。以下为当前未发布工作区的九个固定工具；增加核算工具不代表质量门槛已通过：

| 工具 | 行为 |
| --- | --- |
| `search_course_evidence` | 模型选择主题和查询，通过 Java 权威入口检索；线性主题补入所选工具的方法与联立概念查询，优先保留关键片段的相邻上下文；总计最多8条，显式时间范围保持 |
| `read_evidence_window` | 按同一 source_type 的时间顺序补读已选 Evidence 的前后相邻条目，最多 3 条；没有任意 URL、路径或 SQL 能力 |
| `create_practice_set` | 提交解释与两题草稿；参数、引用和模型复核通过后原子保存，否则返回修订反馈 |
| `check_python_example` | 模型选择课程相关的小程序，受限 AST 解释器返回计算结果或明确的错误/不支持/超限观察；无导入、I/O、循环和任意方法 |
| `create_python_practice` | 字符串路径由模型选择概念、引用和受限操作计划，安全渲染同一程序后计算输出题、私有答案与自查要点；其他Python路径保留原程序契约，仍复核课程与原目标 |
| `create_interval_practice` | 模型选择减半/比较重点、概念题、实数区间及严格反馈；程序保留条件生成方法说明、应用题与精确答案，可附已解示例；比较结果原样引用所选课程片段 |
| `create_sequence_practice` | 模型选择课程所教的最大值移右或最小值移左方法、2—8个不同整数及1—3轮；逐轮核算完整数组与已排序部分，同源生成题目及私有答案，可附请求的已解数组 |
| `create_linear_practice` | 模型选择课程概念、方法、1—2个方程与1—3个候选点；绑定搜索前的任务计划；误读的点数/逐点条件可引用原目标显式修正并留档，再逐点逐式计算。新构造最多检索41×41整点；无解返回观察而不出题。课程支持与原始目标仍独立复核 |
| `report_insufficient_evidence` | 提交当前检索证据不足的说明；复核通过后保存，否则返回反馈 |

`create_practice_set` 合并了蓝图中的练习草稿与保存操作。L2.1 最初直接保存，L2.2 后续增加独立上下文的模型复核；未通过时将反馈交回 Agent，最多提交两份候选。实现和验证边界见 [草稿复核与修订](L2_QUALITY_REVIEW.md)。每个模型响应最多接受三个调用，按顺序逐个执行和 checkpoint，不并行执行工具；产物工具必须位于批次末尾。模型必须调用检索取得引用，再保存练习；重复相同工具参数、未知工具、越权引用和无效结构都会明确终止。结构与来源校验不能证明每项论断都正确；真实课程质量结果与进入 L3 的门槛见 [L2.2 评测](L2_QUALITY_EVALUATION.md)。

原 QA 与原学习资料入口继续可用。Agent 不触发文档建索引，查询也不携带全文。每次工具或生成上下文前后均核验 Java 当前 owner/course/revision；Java 不可用时拒绝使用缓存证据。

当前实验的学习目标仍为课程解释与练习，不做学生自动评分。模型选择搜索、补读、探索计算或具体练习工具；不支持/错误结果和有来源的复核观察会影响下一次选择。成功保存题面、私有答案及评分依据，原始计算/接受或拒绝记录进入私有工具结果；公开事件只报告状态。参数/权属/版本不符、额度耗尽、连续两份草稿未通过、取消或 deadline 均停止。数值工具使用声明的实数条件，不将整数题悄悄改成实数题；Python 工具只接受有界、成功且非空的输出。程序计算只能验证条件对应的结果，课程相关性与自由解释仍需复核。

每个候选默认一次课程证据复核。双重独立模型求解仅保留显式回放入口，真实试验未证明其收益。参考答案和评分点由同一 `answer_points` 生成，旧自由评分草稿不被静默追认。每个字段的引用可补入已选同类字幕的直接相邻上下文（间隔最多 3 秒，向前续接已选字幕的未完句直到句末，通常不另取来源，仍最多8条；线性题可通过同一权限与版本校验补读最多两个窗口，只加入被引用未完句的连续后文，完整记录补读并在最终复核中使用）；原始草稿的显式引用不匹配仍单独检查，补充上下文不能把该错误隐藏。见 [长任务验收进度](../eval/l22-completion/README.md)。

## 持久状态与恢复

Python 使用 PostgreSQL 保存：

- `study_session`：owner、course、不可变 revision；同一 Session 最多一个活跃 Run。
- `study_run`：目标、模式、状态、调用计数、保守 token 预留、deadline、worker token 与失败代码。
- `study_tool_result`：`run_id + call_id` 唯一工具结果。
- `study_artifact`：每个 Run 最多一个学习产物。
- `study_event`：每个 Run 单调 sequence，公开步骤与结果状态。
- LangGraph 的 PostgreSQL checkpointer 表：Session ID 作为框架 thread ID，保存工具间恢复点。

LangGraph 采用同步 checkpoint 持久化；使用官方 `PostgresSaver`。每个节点完成后可恢复；外部副作用的幂等性另由业务唯一键、工具结果回读保障。[LangGraph 持久化说明](https://docs.langchain.com/oss/python/langgraph/persistence)

关键故障窗口：练习和工具结果已提交、框架 checkpoint 尚未保存时进程退出。恢复后重新执行工具节点，先回读同一 `run_id + call_id` 的结果，不重复生成或保存练习。模型调用返回但尚未 checkpoint 的窗口可能重发模型请求；不承诺外部模型恰好调用一次。预算在外部调用前持久扣减，重启不会重置调用额度。

每个 Session 使用专用 **autocommit 连接上的 PostgreSQL advisory lock** 保证不会同时写框架 checkpoint；它不持有跨模型请求的数据库事务。进程退出后连接释放；慢 worker 仍持有锁时，其他 worker 不接管该 Session。业务结果还受 worker token 与运行状态校验，取消后的晚到结果不能成功发布。

当前每个 Python 进程一个后台 worker，单次依次执行课程学习任务，队列持久存在 PostgreSQL。Session 会带入最近两个已完成轮次的有限摘要与产物引用；不是长期记忆、学习画像或完整上下文压缩实现。

## 预算、取消与删除

默认每个 Run：6 次模型调用、8 次逻辑工具执行（内部权威读取另受固定窗口/查询上限约束）、90 秒 deadline，64,000 的保守 token 预留上限。输入以 UTF-8 字节数加工具 schema 估计上界，加决策900 / 目标逐条复核1200 / 字段及课程覆盖复核900 / 旧契约复核300的输出token预留；该字段不是 provider 实际计费 token。checkpoint 最多保留 8 条候选引用；模型上下文按相同时间区间去重后最多发送 8 条、每条最多 600 字符，并使用仅在本次决策内有效的短编号。返回编号经映射及可见集合校验后才恢复成 canonical ID；短编号不作为持久来源。模型响应限制为 128 KiB，单次网络等待不超过剩余运行时间。

`AGENT_RUN_DEADLINE_SECONDS` 支持 30–300 秒，默认 90；deadline 从首次 worker claim 起持久保存，含重启停机时间。CPU 验收可显式加大预算，必须单独报告，不能记成满足默认延迟。

取消请求即时将 Run 标记 `cancelled`；正在进行的外部模型请求采用协作式取消，可能继续到 HTTP 超时或返回，但不能发布为成功。达到预算则 `budget_exceeded`；工具或 provider 错误为 `failed`，脱敏代码对外。当前没有 `waiting_user` / 人工审批节点。语义复核失败可以反馈修订；工具参数不合法仍明确失败，不混为可修复的语义问题。

Java 删除立即关闭全部课程、Session、Run、答案及事件访问。Evidence DELETE 同步持久写入 Python tombstone；后台清理器取得 Session 锁后删除学习产物、工具结果、事件及 LangGraph checkpoints，失败会在后续轮询继续尝试。活动 worker 完成或退出后才能清理其 checkpoint，避免删除后又被旧线程写回。源版本变更使旧 Session 失效，新会话使用新 revision；旧版本学习产物不被当作当前资料。

## API 与前端

浏览器使用现有 Java 鉴权入口：

- `GET /api/tasks/{taskId}/study/status`：功能开关和当前 revision。
- `POST /api/tasks/{taskId}/study/command`：`CREATE_SESSION / LIST / START / READ / CANCEL / EVENTS / ANSWERS`。
- `GET /api/tasks/{taskId}/study/runs/{runId}/events?sessionId=...&after=...`：SSE 支持 `Last-Event-ID`；25 秒一段，前端按最后 sequence 重连与去重。

创建 Session 和 Run 使用 `request_key`，重复提交回读原结果；同一个 key 更换目标会冲突。同一 Session 已有活跃 Run 时明确返回冲突。字段由 Java 注入 owner/course/revision，浏览器不能覆盖这些身份信息。

Python 内部 `POST /internal/v1/study/command` 与 Java 内部 `POST /internal/v1/study/evidence` 使用单独的 `lecturelens-study-v1` audience；HMAC 绑定实际路径、POST、时间戳和原始请求体。复用服务密钥，但 retrieval audience 的签名不能调用 study 端点。Python 不读取 MySQL，也不接收用户 JWT。

SSE 包含执行开始/恢复、模型和工具开始/完成、草稿复核状态、产物创建和终态，不暴露隐藏推理、源正文、答案或评分依据。普通 Run 读取也不包含参考答案；用户点击「查看参考答案与自查要点」才请求 `ANSWERS`。文本通过 Vue 普通插值显示，引用按钮使用原始毫秒时间跳转视频。`kind=insufficient_evidence` 产物没有练习和答案按钮。当前作答文本仅保留在页面，评分与作答事件归属 L3。

模型开始/完成事件用 `purpose=decision|review` 区分决策与复核；完成事件记录耗时及 provider 实际返回的 prompt/completion tokens（若可用），与保守预算预留分开。失败调用可能只有开始事件，不能把缺失 usage 计作零成本。首次模型决策只暴露检索工具；得到证据后才开放生成、补读和证据不足工具。质量与延迟的冻结评测见 [Study v1](../eval/study-v1/README.md)。

## 运行

1. 按 [Evidence 同步](L1_EVIDENCE_SYNC.md) 配套更新 Java/Python，启用 Flyway，执行 V24；`uv sync --locked` 安装 LangGraph/checkpointer 与依赖。
2. 为 Java 和 Python 都设置 `STUDY_AGENT_ENABLED=true`，共享 `AGENT_SERVICE_SECRET`，开启 dense。
3. Python 配置 `AGENT_JAVA_BASE_URL`、`AGENT_LLM_BASE_URL`、`AGENT_LLM_MODEL`、必要的 `AGENT_LLM_API_KEY`。示例在 `.env.agent.example`。使用支持标准工具调用的模型；服务不会因真实 provider 失败而切换 mock。
4. 启动 Java、Python 和前端；课程 READY 后打开「学习助手」。Python 启动时幂等建立学习状态表和框架 checkpoint 表。

`AGENT_LLM_MODE=mock` 是明确的固定输出流程演示，产物与 UI 标记 mock；不能用于真实模型能力展示。真实模式可先启动，再通过 [模型管理](MODEL_MANAGEMENT.md) 配置个人连接与用途；全局 URL/model 是可选的服务器默认。未选择可用模型时，新 Run 不入队并要求先配置。已运行的 Run 不允许切换真实/mock 模式后恢复。

## 验证入口

```bash
# 使用单独的测试数据库，不能与正在运行的 Agent worker 共用测试队列。
AGENT_TEST_DATABASE_URL=postgresql://.../lecturelens_agent_test uv run --directory agent-service pytest -q
uv run --directory agent-service ruff check src tests
uv run --directory agent-service ruff format --check src tests
cd backend && ./mvnw test
cd ../frontend && npm run test:unit && npm run build
```

真实课程、本地实际模型、无 HTTP mock 的验收脚本：

```bash
python3 scripts/eval/accept-study-agent.py --phase prepare
python3 scripts/eval/accept-study-agent.py --phase run
uv run --no-project --with playwright python scripts/eval/accept-study-agent-browser.py
# 浏览器验收后，仅删除脚本自己创建的课程
python3 scripts/eval/accept-study-agent.py --phase delete
```

脚本不启动或购买外部模型，只连接已经配置好的本地服务；默认使用此前的真实 MIT 课程嵌入字幕视频。凭据和完整派生产物写入被 Git 忽略的 `.data/l2-acceptance`，素材许可沿用 [原课程验收记录](L1_REAL_COURSE_ACCEPTANCE.md)。

### 自动化验证（2026-09-15）

- Java：1,358 项通过；Python：61 项通过；前端：47 项通过，生产构建通过；Ruff 检查通过。
- PostgreSQL 集成测试覆盖会话单活、幂等请求、工具副作用去重、预算持久化、版本/身份隔离、取消与重启。真实子进程在产物提交后被 SIGKILL，恢复后仍只有一份产物。
- 前端测试覆盖 SSE 去重、会话恢复、取消、答案按需加载，以及切换课程/开始新轮次时忽略旧响应。

### 真实课程验收

配套启动 Java、Python、V24 与本地实际 Qwen2.5-3B-Instruct Q4 模型，以已有 MIT 课程真实字幕视频创建独立验收课程。课程处理完成后，仅轮询索引状态即达到 READY，尚未发起问题或读取 Evidence。真实 HTTP 验证另一个用户的 READ、CANCEL、ANSWERS、EVENTS 和 SSE 均为 404。

初次联调暴露了普通消息不能替代标准工具返回、模型可能一次返回多个合法工具调用、CPU 生成超过固定单请求时限三个问题。已改为标准工具消息、最多三个调用串行 checkpoint，并让网络等待使用 Run 剩余时间。未采用固定答案或失败后切换 mock。CPU 验收显式使用 240 秒总预算，默认仍为 90 秒；此验收不证明默认时限的达标率。

最终真实 Run 成功：3 次模型调用、4 次工具执行（检索、两次窗口读取、保存练习），端到端 186.09 秒，保守 token 预留 22,746。生成解释与两道题；每条引用的 Evidence ID、正文前缀及起止时间与 Java 原始 Evidence 对照一致；重复 START 返回同一 Run，SSE 按游标续传无重复，答案仅按需返回。两题主题接近，题目多样性与语义正确性仍需后续质量评测。

真实 Chromium 验收通过：会话/产物刷新恢复、两题呈现、答案默认隐藏且点击后加载、引用跳转至非零时间 17.13 秒；390px 手机视口无横向溢出。截图和结构化结果保留在本地忽略目录 `.data/l2-acceptance/`。

删除验收课程后，Study/Evidence 立即 404。随后 PostgreSQL 实查：`evidence_index.state=DELETED`；该课程的向量、indexed Evidence、4 个 Session/Run、工具结果、事件、练习产物及三个框架 checkpoint 表中的关联数据均为 0。仅删除验收脚本创建的课程，未删除其他课程或共享数据卷。

验收使用隔离的本地基础设施、真实服务调用与实际本地模型，无付费模型调用；不是生产部署。测试日志和包含凭据的运行环境均留在 Git 忽略目录或 `/tmp`，不进入提交。

## L2.2 真实课程评测

新增 20 个固定任务、开发/保留课程拆分、真实调用日志、语义复核与全结果延迟报告。完整结果见 [质量与延迟评测](L2_QUALITY_EVALUATION.md)。本页上方 1,358/61/47 项测试与 186.09 秒单次运行是 L2.1 历史记录，不能代表 L2.2 的质量门槛。

## 下一阶段

L2.1 提供受限循环、持久会话/执行、产物、取消与恢复的最小闭环。完整 L1 RAG 对照评测、题目质量评测、人工交互暂停、长期 Memory、作答评分和复习调度仍需分别验收；不由本次闭环自动宣称完成。


2026-09-19 未发布 AP 补充：首次检索由模型选择 `practice_kind`（通用、Python 输出或实数区间减半），工具结果保存该选择，后续决策只提供相应生成工具。模型观察证据后可重新检索改选；历史省略该字段的回放保持兼容。选择不传入 Java Evidence 接口。通用生成 schema 明确分为概念题和具体应用题，内部仍存两道有序题；答案与评分依据同源。区间已解示例若与应用条件重复，工具按明示规则使用相反反馈作为应用变式，保留原请求和实际条件。复核中的接受字段可选复述不替换答案，拒绝修正仍受长度、字段和证据约束。所有改变仍属隔离实验，未通过质量门槛。


AU 未发布补充：选择排序步骤工具不会调用通用排序后冒充中间状态，课程是否教授所选方法仍由语义复核检查。计算应用题只有在本地重新构造验证题面和答案一致后，才从模型复核请求中去掉该应用的答案/计算结果；实际题面、方法、证据、解释与概念答案仍可见。原完整输入继续用于本地证据校验和私有持久化。预算按实际发送视图保守预留；六次调用、八次工具和90秒上限未变。目标不匹配意见的内部容量支持候选字段、最多两段课程来源和目标原文四段，求解观察最多三段；不增加模型允许的课程引用数量。决策输出截断可共用一次持久决策格式纠正额度，复核格式失败可在同一次复核位置纠正一次，失败调用均计入原总预算。

AY 未发布补充：区间工具当前schema以 `focus` 选择方法说明，比较模式需要 `reported_evidence_ids`；短ID经显式转换并在两个工具边界检查。旧自由解释输入仍可回放。比较结果不从次数推断隐藏范围或目标，工具仅引用权威片段；片段是否足以支持解释和题目仍需语义复核。全量350项机制测试通过，不代表真实质量验收通过。

AZ 未发布补充：`search_cost` 是模型选择的学习主题，复用 `create_practice_set`，工具总数仍为8。该模式只处理课内 n log n 排序/log n二分查询/n扫描的成本比较，生成单次查询遗漏准备阶段或重复排序的纠错应用；其他成本模型与具体线性扫描追踪仍用通用模式。模型仍负责解释、概念题与逐字段引用。程序生成的成本答案仍接受完整课程语义复核，不是数值计算豁免。358项完整机制测试及最后59项相关检查通过，真实质量另行评测。

BA 未发布补充：区间工具的新概念输入为 `concept.skill`（中点原因、反馈作用、两种方法比较）及自身证据ID，程序生成问题与参考答案，避免自由概念答案混入另一套数值结果。原自由概念输入仅保留旧请求回放兼容。工具引用和语义复核仍要求所选概念确由课程教授。367项机制测试通过；完整Phase尚未完成。

BB 引用修复：受限成本应用包含的固定方法代价必须引用模型选择的共享方法来源及场景来源。概念题独有来源不自动传入，逐题语义复核仍检验这些实际引用能否支持结论。368项机制测试通过。BA开发语义分数已由16/16更正为13/16，正式评测未启动，详见[审阅更正](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/citation-review-errata.json)。

BC未发布实现补充：检索时模型可选择`python_strings`，随后用`immutability`或`rebinding`概念技能生成字符串方法说明与概念题，避免额外错误类名和对象生命周期结论；其他Python代码仍保留自由概念契约。选择排序概念用`boundary`、`placement`或`progress`技能，说明与应用使用同一模型所选方法，已解示例不得使用相反方法。模型仍选择证据、程序/数组/轮数及工具；这些模板没有来源豁免，只有重新核算匹配的应用答案可移出模型复核视图。旧自由契约仅用于已有记录和测试回放。

最终BC已完成本轮L2.2有限范围验收，20/20类型、16/16语义、4/4拒答；391项机制测试与完整恢复、浏览器、取消和删除检查通过。候选未发布，线上C未变。开发仍观察到误拒绝/预算失败，模板与小样本通过不能推广为通用可靠评分，见 [最终报告](../eval/l22-completion/FINAL_BC.md)。

本轮学习闭环 Phase 的目标条件、拒答正文、线性计算、引用补读及独立质量结果见 [Phase 验收](../eval/phase-completion/RESULTS.md)。模型原始判断与保守规则拦截分别报告；线上 C 不随工作区开发改变。

2026-09-20 学习闭环Phase补充：来源集合与规范ID保持不变，带时间的复核片段及共享正文按课程时间顺序展示；排序不推断相邻关系或支持。字符串计划最多三次绑定、四次打印；固定线性输入不预猜成立条件，旧版本计划保留回放语义。当前候选、完整机制测试、开发与新保留质量分别见 [Phase记录](../eval/phase-completion/RESULTS.md)。本文件早期同名候选字母属于历史L2.2阶段，不等同于学习闭环Phase的源码身份。
