# L2.2：草稿复核与修订循环

**2026-09-19 当前验收状态：** 冻结BC在隔离qwen3-max生成／复核下完成L2.2既定Phase验收：20/20类型结构、16/16内容、4/4拒答；391项Python／独立PostgreSQL测试、20份产物重启与幂等恢复、浏览器、取消及删除检查通过。范围为两门已见课程、四段视频上的10道开发与10道新目标，AI来源核查，不代表未见媒体泛化。候选未发布，线上C及个人模型配置不变；L3未启动。 见 [最终报告](../eval/l22-completion/FINAL_BC.md)。

以下保留按日期与候选记录的历史过程；旧轮次失败不被覆盖。

**历史轮次质量未达标。** 2026-09-15 本地配置六题全部耗尽 90 秒预算，见 [历史试验](../eval/study-v2/README.md)。2026-09-17 百炼最新开发回归 6/6 完成、完整拒答 2/2，但课程内语义仅 1/4，复核漏过三份错误练习；该轮尚未观察到有效语义修订，见 [历史回归报告](../eval/bailian-pilot/REGRESSION.md)。

后续 D/E 实验仍未改善完整语义：E 完成 4/6，课程内 1/4，拒答 2/2。工作区有尚未发布的逐字段复核、具体修订反馈、代码格式与 AST 观察实现；线上仍使用 C。下述运行行为描述线上 C，新候选的实现、118 项机制测试和失败边界见 [D/E 报告](../eval/bailian-pilot/FIELD_REVIEW.md)。

随后用八份固定正确/错误草稿直接对比复核器，C/E 都判对 6/8；E 降低一次误接受、增加一次误拒绝，两版均漏掉评分点矛盾，未部署候选。该轮只测复核、没有 Agent Run 或修订，见 [定向诊断](../eval/reviewer-probe/README.md)。

后续工作区已更新为未发布的 J：显式检查标准答案与评分规则，练习拒绝须附可校验原文，规范 Evidence ID 与私有反馈一起持久化恢复。最终旧开发集 7/8、新八份草稿 6/8，仍漏检新评分矛盾，并存在分类/引文导致的协议失败；170 项 Python 测试（独立 PostgreSQL、无跳过）通过不代表语义质量达标。线上仍为 C，详见 [本轮修复及失败记录](../eval/reviewer-probe/FIX.md)。

2026-09-19 工作区进一步更新为未发布的 K：逐条判断评分规则，模型选择片段编号、程序回填原文。旧两组 7/8、6/8，新八题判定 8/8，但最终纠正反馈仅 6/8 可靠；观察到错误规则分类覆盖有效事实纠正，不能据二元成绩放行。177 项 Python 测试通过，线上 C 与全部预算不变，见 [K 实验](../eval/reviewer-probe/CLAUSE_REVIEW.md)。

2026-09-19 同日后续：工作区 L 将事实纠正与待核对的规则观察分别持久化，修复错误规则标签覆盖有效建议的问题。20 次真实调用：已见/新八题二元判定均为 8/8，含有效建议均为 7/8；两条预置错误草稿的真实 LangGraph/PostgreSQL 修订中，1 条有效修订并保存，1 条首次复核协议失败。仍有与引用原文相反的建议，不证明自主生成或完整 L2 质量通过。181 项 Python 测试通过，线上 C 和模型配置不变，见 [L 实验](../eval/reviewer-probe/FEEDBACK_PRESERVATION.md)。

2026-09-19 后续 M 实验：同一次复核先输出课程求解，再检查原答案与评分规则，并保存私有求解观察；试跑可保留校验前的已解析参数。20 次真实调用中，已见八题判对 5/8，新八题仅 2/8（含有效反馈 1/8）；两条预置草稿修订 1/2 成功，成功案例保留正确答案并修正矛盾规则，但整体候选失败，误拒绝及重复问题报告仍在。189 项 Python 测试通过，M 保留为未发布实验，线上 C 与模型配置不变，L2.2 未完成，见 [M 实验](../eval/reviewer-probe/COURSE_ANSWER_FIRST.md)。

2026-09-15。目标是让错误检查成为 Agent 的工具观察，支持下一步修订；不把模型复核等同于事实正确性证明。L3 作答评分与长期记忆仍未开放。

2026-09-19 长任务继续：工作区 BB 使用同源答案要点和可核算代码输出题，并将接受字段的冗余重写移除，给拒绝修正留出输出空间。双重独立求解默认停用（仅保留显式回放），因为多轮真实试验未证明其收益；每个候选仍有一次课程证据复核。X 完整入口十题全部完成，但支持题语义仅 2/8；后续试验仍有协议、内容和预算失败。用户已授权隔离 qwen3-max 生成，线上 C 与个人配置不变。**Phase 尚未完成**，AT 新保留集与配对基线已完成，但完整门槛未通过，见 [长任务记录](../eval/l22-completion/README.md)。

## 运行行为

1. 用户给出学习目标，模型先选择课程检索。
2. 模型提交解释与两题草稿，或提交“当前检索证据不足”的说明。
3. Python 重新读取当前课程的权威 Evidence，先检查各字段显式行内引用与该字段声明引用是否一致；不一致则直接反馈。否则在独立上下文中调用 Run 冻结的复核用途模型。复核只开放 `assess_study_candidate`，没有其他工具权限，不接收之前的生成对话。
4. 复核检查解释引用、每题自己的引用、完整答案和评分要点、题型区别、答案泄露、目标语言、目标匹配及错误拒答。网络输出仅含有限 `issues` 代码，本地生成有界修订提示；证据不足候选只允许 `unjustified_abstention`。拒绝的草稿不会进入学习产物表。
5. LangGraph 将反馈作为工具观察交回决策模型。模型可以修改草稿或补查证据；只有实际缺乏目标证据时才能申请拒答。通过复核的候选原子保存，随后结束。

因此本轮新增的 Agent 行为是 **目标 → 检索 → 草稿 → 复核观察 → 下一步工具选择 → 可持久化产物或明确失败**。复核节点由程序强制执行，下一步动作仍由模型选择；这不代表通用规划能力。

实现：[runtime.py](../agent-service/src/lecturelens_agent/study/runtime.py)、[quality.py](../agent-service/src/lecturelens_agent/study/quality.py)、[provider.py](../agent-service/src/lecturelens_agent/study/provider.py)。学习逻辑和状态继续由 Python / PostgreSQL 管理。

## 约束与故障处理

- 每个 Run 最多提交两份候选（`RUN_CANDIDATE_LIMIT`），练习与拒答合并计数；被关闭模板的候选除外（见下文）。第二份仍被拒绝时，终止为 `QUALITY_REPAIR_EXHAUSTED`，不会用“证据不足”掩盖生成质量失败。
- 修复候选若除 `title` 外与某份已被拒绝的候选完全相同，不执行也不再送审：决策收到一次 `repair_notice`（指明被拒候选和问题，要求改内容，或在当前模板无法表达学习目标时按匹配的 practice_kind 重新搜索），并记录 `protocol_retry_scheduled`（`REPEATED_TOOL_WITHOUT_PROGRESS`，purpose=`quality_repair`）。再次仅改标题则直接终止为 `QUALITY_REPAIR_EXHAUSTED`，不消耗复核调用。
- 固定计算模板（`interval_halving`、`selection_steps`、`search_cost`）的候选若被判定为模板不匹配，该 practice_kind 在本 Run 内关闭。判定条件：复核给出 `goal_mismatch`，或者 question_2 被判 `unsupported_question`。question_2 的归属来自字段级复核的 `field_issues.question_2`；运行时的 `method_citation_check`（question_2 未引用所选方法的来源）不写 `field_issues`，它的问题全部归属 question_2，走同一判定（这三个模板的 question_2 由工具生成，问题出在模板本身；question_1 和讲解仍按原模板修复）。当前只有 general 和 linear_points 检索会观察课程方法，带 `method_id` 的 cost 模式候选以 `UNOBSERVED_APPLICATION_METHOD` 终止，因此这条检查暂时到不了模板类型，这一归属只是关闭规则的保护，尚无对应的真实 Run。关闭后，决策上下文加入 `closed_practice_kinds` 和固定说明，该模板的生成工具不再提供，`search_course_evidence` 的 practice_kind 枚举也去掉它，只能按其他 practice_kind 重新检索或报告证据不足。重新检索之后，运行时仍会拒绝已关闭的专用模板。通用练习仍可使用自己的共享生成工具。模型若仍调用已关闭的模板或用它检索，运行时以 `INVALID_TOOL_ARGUMENTS` 终止，不再消耗复核调用。被关闭模板的那份候选不计入候选上限（`RUN_CANDIDATE_LIMIT`=2，`budget.candidates_left` 同步）；每个模板最多返还一次，因此一个 Run 最多复核 2+3 份候选，12 次模型调用和 8 次工具调用的持久上限不变。可调整输入的模板（`linear_points`、Python 字符串）和通用练习不受影响，仍在原工具内修复。
- 通用练习选了 `method_id` 时，运行时在送审前把所选方法的来源 ID 并入 question_2 的引用，与 `create_linear_practice` 绑定方法来源的做法相同。来源已经过 `METHOD_EVIDENCE_NOT_SELECTED` 授权；复核仍按 `METHOD_FIELD_SYSTEM` 判断方法是否一致、来源是否支持，概念题和讲解的引用不变。2026-11-14 开发探测中，`method_citation_check` 的 3 次拒绝全部是 question_2 漏引方法来源，三个耗尽 Run 中有两个的最终拒绝属于这一类。这条检查保留下来，只对绑定之前已写入 checkpoint 的候选生效。
- 一个 Run 的第一次 `report_insufficient_evidence`（响应中只有这一个调用），如果当前提供检索工具，且预算还够一次检索加一次拒答（`ABSTENTION_NOTICE_MIN_TOOL_CALLS`=2，`ABSTENTION_NOTICE_MIN_MODEL_CALLS`=3），先不执行：决策收到一次固定的 `abstention_notice`，要求用课程自身术语换措辞再检索，并记录 `protocol_retry_scheduled`（`SEARCH_REQUIRED`，purpose=`abstention_check`）。第二次拒答照常执行并复核。拒答复核只看已检索的段落，发现不了检索遗漏；三份样本中 b2-cost-lure 的三次假拒答都是检索没拿到 1D 复杂度段落后、在仍有预算时直接拒答。通知后的决策使用独立的 journal slot。代价是每个拒答 Run 最多多一次决策、一次检索及其覆盖观察。
- 决策历史回放 `create_linear_practice` 时去掉运行时绑定的顶层 `evidence_ids`（`LinearPracticeArgs`）：决策契约 `LinearSelectionArgs` 禁止该字段，回放它会让修订照抄并以 `MODEL_TOOL_CONTRACT`（`extra_forbidden`）终止。私有记录、契约校验、运行时绑定和引用授权不变；引用只在 `concept` 和 `application` 中提交。
- 同一响应中的多个 `read_evidence_window` 按做决策时的选中集合授权：前一次补读把后一次的锚点挤出 8 条选中范围时，后一次仍然执行，不再以 `EVIDENCE_NOT_SELECTED` 终止。锚点在决策时必须可见，Java WINDOW 仍复核归属、版本与删除。
- 每次复核调用在 `MODEL_REVIEW_CONTRACT`（schema 不符）或 `MODEL_TOOL_CONTRACT`（工具参数不是合法 JSON）时各最多重试一次，仍计入同一 Run 预算。重试反馈只包含运行时生成的固定说明和经校验的违规位置与声明上限（例如 `methods` 超过 `max_length` 2 项），不转发模型原文或自由文本。
- 决策与复核共享同一 Run 上限：12 次模型调用、8 次工具调用、600,000 保守 token 预留和默认 90 秒 deadline。复核输出最多 300 tokens，决策输出最多 900。没有额外重试预算。
- 8 次工具调用中的最后一次留给候选或 `report_insufficient_evidence`：会用掉它的检索、窗口补读或 Python 检查不执行，记录 `tool_rejected`（`TOOL_CALL_BUDGET_RESERVED`，类别 budget）；同一响应中较早的调用和末尾候选照常执行。剩余工具调用不超过 2 次时，预算观察加入 `tool_calls_left` 和固定说明；只剩 1 次时决策 schema 撤下探索工具。只剩不可执行的探索调用时以 `INVALID_TOOL_ARGUMENTS` 终止；已无剩余调用时仍由持久预留以 `budget_exceeded` 终止。限制：剩余超过 2 次时模型看不到工具预算；补读结果是否已全部在选中集合内，要等 Java WINDOW 返回后才知道，无法提前拒绝。
- 决策的非法工具格式最多获得一次明确纠正观察，仍扣减原有预算并记录 `model_failed` / `protocol_retry_scheduled`；错误响应的工具不执行。持续失败、其他调用错误、复核错误均终止；页面显示纠正进度。失败调用的已知 usage 保留。
- 复核输入最多 8 条、每条最多 1,200 字符的当前权威 Evidence；引用映射为临时短编号。逐题仍保留自己的引用集合。
- 复核从输入中选择支持来源时，`evidence_ids` 上限与复核输入条数共用 `REVIEW_EVIDENCE_LIMIT`（8，即 Java READ 的 ID 上限），schema、提示词和测试都引用这一常量。此前课程覆盖/方法观察限 3 条，模型在真实长课中反复列出 4 条以上，每次多花一次复核重试。
- 复核后重新检查取消、owner/course/revision、worker token 和 deadline。错误工具名、错误结构、模型不可用等情况均阻止发布，不自动切换 mock。
- 拒绝结果与公开事件在同一事务内写入 `study_tool_result` / `study_event`。提交后、checkpoint 前崩溃时，恢复直接回读复核结果，不再次调用模型，也不重复产物。
- 模型已经返回但结果尚未提交时，恢复可能重新调用模型；调用前已持久扣减预算，不承诺外部模型恰好调用一次。
- `quality_checked` 公开事件仅包含调用 ID、接受标志、有限错误代码和检查来源。修订建议、草稿答案与评分要点只保留在私有工具记录和 checkpoint；不会放入 SSE 或普通 Run 响应。
- 成功产物的 `quality_check=model_review` 只表示经过模型筛查；mock 明确为 `mock_demo`。旧产物没有这个字段，不追认已复核。

前端显示“草稿需要修订”“模型复核已完成”，两次不通过时显示明确失败原因。用户实际作答仍只留在页面；本轮没有引入自动评分。

## 验证与真实模型边界

机制测试使用确定性 provider 与真实 PostgreSQL，覆盖拒绝后修订、错误拒答后改为练习、两次拒绝、崩溃恢复、取消、版本变更、超时和非法复核结果。它们不证明模型能够识别或改正真实错误。

模板关闭、名额返还和窗口补读授权的真实模型开发探测（DeepSeek，已知课程，非保留集）：7f97823 两份样本共 54 Run，窗口补读修正真实触发 3 次全部通过；模板关闭与名额返还 0 次触发，只有机制测试覆盖。见[第二样本记录](../eval/study-development-20261115.md)。2026-11-15 对 `study-content-2131d025b61561e5` 做了两轮真实模型探测（DeepSeek，开发集，非保留集），见 [T2 旧目标归因](../eval/study-development-20261115.md) 和 [T3 新目标](../eval/study-development-20261115.md)。T2 跑满 27 个 Run，通过 23 个（可比子集 18/21）；T3 在执行 16 个 Run 后早停，通过 13 个（评分方式待批准，标为 PROVISIONAL）。逐项结果：
- 修订回放：`extra_forbidden evidence_ids` 降为 0。但 c1-linear 改为以 `QUALITY_REPAIR_EXHAUSTED` 结束，原因是 system_solution 模板固定生成的讲解句“只检验其中一个方程还不足以确认一个点是方程组的解”被判 `unsupported_explanation`，模型无法修订这句话。
- 最后一次工具调用的预留：`RUN_BUDGET_EXCEEDED` 为 0；它以撤下工具 schema 的方式起作用，没有出现跳过执行。
- 模板关闭：第一次被真实触发（T2 R1 b2，search_cost）。但关闭后需要重新检索，而最后一次调用的预留不允许检索，决策只剩拒答；模型调用了未提供的工具，Run 以 `MODEL_TOOL_CONTRACT` 结束。名额返还没有产生可用的效果。
- 方法来源绑定：带 method_id 的通用候选共 38 份，其中运行时补入方法来源 2 次，其余 36 次是模型自己引用的。
- 首次拒答扣留：在 T3 n-calc-angle 触发 1 次，但当时没有提供检索工具，Run 以 `MODEL_TOOL_CONTRACT` 结束。T2 中 b2 的假拒答没有出现，原因是模型这一轮写出了能检索到相关段落的查询，不能归因于这项修正。
诊断摘要见[开发探测记录](../eval/study-development-20261115.md)。

新试验使用 MIT 6.0001 第 4 讲函数课程的官方字幕，固定片段、六道新的保留任务、同一 Qwen2.5-3B Q4 模型及资源预算，比较冻结的旧运行时与本轮候选。真实执行 Python LangGraph、ChatProvider 和 PostgreSQL；Evidence 入口使用固定片段回放，所有检索返回同一范围的正文。这能隔离 Agent 行为，但不验证 Java 鉴权、向量召回、媒体摄取或浏览器全链路。

这个六题试验的规模和范围不足以替代原有完整 L2 质量门槛；不会据此直接放行 L3。数据、来源、配置与结果见 [Study v2 试验](../eval/study-v2/README.md)。候选在查看任何本轮模型产物前冻结；保留题一经复核即不能再作为下一次调参后的未见测试集。

## 2026-09-15 历史自动化验证

Python 84 项通过（真实独立 PostgreSQL，无跳过），前端 48 项通过、生产构建通过；Ruff 与补丁空白检查通过。本轮没有改 Java，也没有重跑 Java 或浏览器全链路。此前的 Starlette/AnyIO 弃用提示与前端依赖注释/大包提示仍存在。见 [验证摘要](../eval/study-v2/verification.json)。

2026-09-17 短复核与一次格式纠正修复：Python 112 项（独立真实 PostgreSQL、无跳过）、前端相关 16 项、TypeScript 与生产构建通过；对应真实模型质量仍未通过，见 [开发回归](../eval/bailian-pilot/REGRESSION.md)。

AV 继续区分复核输入与存储原文：`verified_worked_example` 重建区间/排序步骤并严格匹配解释末尾及自身引用，只有完全一致的程序计算后缀才从发给模型的解释和重复片段目录中移除，输入问题仍可见。模型继续检查方法支持、目标匹配和全部自由解释；原文用于结果验证及私有追踪。无匹配、错误参数或越权引用均不能隐藏内容。该标记不证明方法受到课程支持，也不保证自由解释正确。347 项 Python 机制测试通过；AV 的真实质量评测单独记录，尚未验收。

AW 区间工具不再自动翻转与解释示例相同的应用题反馈；题目、答案和计算证明都保留提交条件。是否另设应用参数由模型在目标约束下决定，概念与应用仍需通过不同技能检查。历史 AM–AV 的自动变体记录不改写，冻结旧代码保留其旧语义。

AX 的区间练习新增 `focus=halving|compare_sequential`。模型选择学习重点、课程结果片段、概念问题和计算参数；工具生成有限的方法说明，比较模式从权威READ结果引用 `reported_evidence_ids` 原文。该字段在决策与执行两处校验观察范围，不允许外部课程引用。旧自由解释输入可回放，但不在当前工具schema中提供。模板和计算不证明课程支持，仍必须通过自身引用复核。350项机制测试通过；真实质量单独验收。
