# P2-2a：既有公开课程的学习闭环与默认反馈

状态：**设计待用户确认；本阶段只读调研及文档本地提交，未改代码、配置或部署，未执行学习任务。**

调研基线：主仓库 `codex/p14-system-model-management`，`0ea420503b1e6dfa54e568e9d3ba84cc83da9dbd`；2026-10-17 UTC（北京时间 2026-10-18）。本设计不把 #34/#35 的 CI 修复视作已合并到主仓库或已通过 CI。

## 1. 决策与边界

复用已经入库的 MIT 6.0001 第 3 讲字符串 Sample Course，交付“输入目标 → 课程检索 → 解释与两道练习 → 保存作答 → 主动获取证据反馈 → 点击引用回看”。不上传新视频，不跑 ASR、翻译或新的处理链，不启动隔离 Java，不依赖 T1/P2-1c 解冻。

默认开启的对象是**登录后拥有该课程的用户**；公开课程素材不等于应用内向所有登录用户共享课程。默认开放反馈入口，仍由用户保存作答后点击请求，不自动调用模型、不自动评分。沿用全局开关与既有 ownership，无新增角色、课程 allowlist 或工具。

闭环组件已经存在，缺口主要是发布默认值、可核对的时间标识及当下演示运行环境。现有 Sample Course 数据、索引、媒体齐备，但本机既有 live 网关的 Java upstream 8080 和历史演示 8084 均未监听；因此**当前不能宣称完整网页闭环可执行**。后续若没有可复用的已运行授权网关，则真实验收暂停，启动/重启后端须单独获批，不能以固定回放冒充完成。

沿用 [产品契约](../../docs/AGENT_PRODUCT_CONTRACT.md)。feedback-P 的开发 6/6、新保留 8/8 是已有有限范围结论，本次不重做或修改该评测；当前源码的发布身份须另行冻结，不能称它与旧 P 字节相同。AU 及旧 C/E、P2-1c 的失败记录、FREEZE、评测口径保持原样。本次 5 个场景是发布演示验收，不是 fresh holdout，也不证明未见课程泛化。

## 2. 现状盘点：代码存在与运行可用性分开

以下路径均相对仓库根目录；行号对应上述基线。Study 命令统一经过 `POST /api/tasks/{taskId}/study/command`，Java 签名转发到 Python `/internal/v1/study/command`；浏览器不直连数据库或内部 Evidence 接口。

| 步骤 | 前端组件/位置 | Java 接口/位置 | agent-service 节点、工具与落库 | 现状 |
| --- | --- | --- | --- | --- |
| 默认学习入口、输入目标 | `frontend/src/views/TaskDetailView.vue:38,83,354` 默认 `agent`；`frontend/src/components/task-detail/CourseAgentPanel.vue:67–89,106–124,194` 检查状态、创建会话、提交目标 | `backend/src/main/java/com/example/courselingo/study/StudyController.java:29–40,74–95`：status、CREATE_SESSION、START、前后版本检查 | `agent-service/src/lecturelens_agent/app.py:157–178` 鉴权及 authority CHECK；`study/store.py:117–187` 保存 Session/Run、幂等 request_key、模型配置快照 | 已实现；索引非 READY 或服务关闭时不可开始。Java `backend/src/main/resources/application.yml:100`、Python `app.py:46` 的 Study 总开关默认 false；实际部署值本阶段未读取 |
| 模型选检索、观察与补读 | `CourseAgentPanel.vue:49,214–220` 显示执行事件；`frontend/src/api/study.ts:59–85` 状态/命令/SSE | `StudyController.java:99–144` SSE 与 `/internal/v1/study/evidence`；`StudyEvidenceAuthority.java:23–70` 校验 owner/revision，SEARCH、READ、WINDOW | `study/runtime.py:354,603,619–625,767` 的 decide/tool；`search_course_evidence`、`read_evidence_window`；`study/authority.py:71–82` 受限签名请求。证据、方法覆盖、工具错误进入下一次决策 | 已实现，不是上传流水线或普通 QA 的同义词；不直接读取其他服务表 |
| 解释和练习 | `CourseAgentPanel.vue:227–243` 解释、引用、题目、主动展开参考答案 | 同一 command 的 READ、ANSWERS；`StudyController.java:44,74` 的允许操作及就绪检查 | `study/runtime.py:448–453,817,1078,1104–1120`：模型选已有生成工具（如 `create_practice_set`）或 `report_insufficient_evidence`，复核拒绝返回观察，最多两份候选；`study/store.py:262–296` 返回学习产物与作答 | 已实现；解释和两题一起产出，不另建纯聊天/新题型；失败不伪造成功产物 |
| 作答、修改、刷新恢复 | `frontend/src/components/task-detail/PracticeAnswerForm.vue:41–80,85–98`；父组件 `CourseAgentPanel.vue:239` | command SAVE_ATTEMPT、ATTEMPT_HISTORY；`StudyController.java:50–57,74,81–86` | `study/store.py:106–114,216–219`；`study/attempts.py:31–89` 锁定作用域、幂等、expected_version、不可变 `study_attempt` | 已实现；空答案不保存；旧版本冲突保留用户输入 |
| 独立证据反馈、核对、更正 | `frontend/src/components/task-detail/PracticeFeedbackPanel.vue:88–103,181–205`；`CourseAgentPanel.vue:240` 控制入口并保留历史 | command START_FEEDBACK、READ、CANCEL、SAVE_FEEDBACK_NOTE；`StudyController.java:59–66,74–95` | `study/feedback_store.py:31–78,124,134` 创建精确 source_attempt_id 的独立 Run，保存 `study_feedback` 与 `study_feedback_note`；`study/feedback.py:427–438,473–505,555–635` 的 feedback_decide/feedback_tool，已有 `read_question_evidence`、`read_feedback_window`、`submit_answer_feedback`、`report_feedback_insufficient` | 已实现，**新反馈默认关闭**；每条建议有自己的来源；首轮强制读题目证据，之后模型选择补读/提交/拒答，独立复核意见影响后续决策 |
| 引用回看 | `CourseAgentPanel.vue:230–233`、`PracticeFeedbackPanel.vue:195–196` 发出 start_ms；详见下一节 | `backend/src/main/java/com/example/courselingo/media/MediaPlaybackController.java:35–59` 发播放令牌及 Range 流 | Python 复用 Java 权威时间；`StudyEvidenceAuthority.java:68–70` 返回 start_ms/end_ms；`study/feedback.py:605–610` 保存 citations | 源码已连通；反馈引用按钮没有展示起止时间文本。当前浏览器可用性未验证 |

`study/…` 简写对应 `agent-service/src/lecturelens_agent/study/…`；无前缀的前端组件均在 `frontend/src/components/task-detail/`，Java Study 类均在 `backend/src/main/java/com/example/courselingo/study/`。

### 开关、状态与边界

- `agent-service/src/lecturelens_agent/study/feedback_store.py:31–37`：读取 `STUDY_FEEDBACK_ENABLED`，未设置默认字符串 `false`，只有忽略大小写的 `true` 放行；关闭时 START_FEEDBACK 返回 `FEEDBACK_DISABLED`/409。
- `.env.agent.example:13` 模板也为 false；本次仅定位示例模板，未读任何真实 `.env*`。实际运行值未知，不从历史报告推断当前环境。
- `study/store.py:294–296` 将开关和历史反馈返回浏览器。`CourseAgentPanel.vue:36,101,123,240` 本地初始/缺字段回退为 false，关闭后已有反馈仍有入口。保留这个 API 缺字段时的前端保守回退，不把浏览器当授权开关。
- 运行预算仍是 6 次模型调用、8 次工具、64,000 保守 token 预留（`study/store.py:398–400`），默认 90 秒（`study/runtime.py:72`），最多两份候选；保留取消、版本栅栏、幂等、checkpoint 和恢复锁（`study/runtime.py:137–155`、`study/store.py:335–348`）。
- 自适应后续练习、长期记忆、复习调度不在本次闭环；目标完成不产生掌握程度或成绩。

## 3. 引用跳秒：已有链路与最小改动

### 时间来源与单位

MySQL `course_evidence.start_ms/end_ms` 是非空 BIGINT，payload 中对应 `startMs/endMs`；schema 见 `backend/src/main/resources/db/migration/V23__versioned_course_evidence.sql:10–21`。`CourseEvidenceService.java:96–145` 从源/译字幕的 start_millis/end_millis、图像 timestamp_millis 填入；字幕提供区间，图像可能是同一开始/结束时刻。`number()` 缺失值回退及 end 的下限保护意味着“字段存在”不等于经过精度验证，不能为任意课程承诺准确跳秒。

本次推荐课程实查 8 条源字幕＋8 条译文，时间 0–112,590 ms，全部 retrievable，未发现负数或倒置。它们是约 5–19 秒的**字幕片段区间**，不是逐词对齐；不补跑 P2-1a/P2-1c。视频长 117.0169 秒，尾部无字幕不等于媒体缺失。播放轴是裁剪后视频的局部时间；原课从 11:00 开始，展示原课时间时才另加 660 秒，绝不能向本地播放器重复加偏移。

### 已有点击链路

`CourseAgentPanel`/`PracticeFeedbackPanel` → `TaskDetailView.vue:122–123,354` 将 ms / 1000 → `CourseVideoAside.vue:38–42` 转发 seconds → `VideoPlaybackCard.vue:72–81,105–110` 检查有限非负值，metadata 前暂存，metadata 后设置 `video.currentTime` 并尝试播放。Java 的 task playback-token 校验课程所有权（`MediaPlaybackServiceImpl.java:66–78`），stream 支持 Range/206（同文件 `:82–102`）。

**实现引用点击到已有片段起点，最低需要改 0 处。** 当前已有前端测试验证 metadata 前 pending seek，以及反馈多个来源各自发出 seek（`VideoPlaybackCard.test.ts:5–24`、`PracticeFeedbackPanel.test.ts:27,48`）。这些是机制证据，不代替此次真实媒体验收。

拟议的唯一必要呈现改动：在 `PracticeFeedbackPanel.vue:195–196` 复用现有 `formatMillisRange` 显示“回看证据 00:36–00:45（片段起点）”，约 5–12 行；学习产物引用按钮也可将“跳到视频”改为“回看片段起点”，约 1–3 行。Java/Python 不增时间字段或新接口，不增加截断播放能力。

异常策略：媒体不可用时保留证据原文与时间，使用现有播放器错误/刷新入口；不得把原课外链当成已完成本地播放。如果未来实查时间为空、倒置或超出媒体，禁止将缺失值当 0 秒的成功定位；若仅有可信片段起点则只承诺起点，若连起点都无依据则展示文本引用并记录该目标的跳转验收失败。此类防护最多在现有引用按钮/seek 入口局部增加 15–30 行，发现问题再纳入；推荐课程目前没有该数据缺陷。

## 4. 演示课程与数据可用性

只读证据与查询口径见 [OBSERVATIONS.md](OBSERVATIONS.md)。MySQL 来源是既有 `lecturelens-demo-l2-mysql-1`，用其既有非 root 应用身份在 READ ONLY 事务执行 SELECT；未写入、DDL、GRANT。查询 `analysis_task`、`upload_session`、`course_evidence`、`evidence_index_sync`，排除已删除任务，以当前 content_revision 计数。PostgreSQL 在 `lecturelens-agent-postgres-1` 的既有库用 READ ONLY 事务核对 `evidence_index`、`indexed_evidence`；没有触发重建索引。

| 公开课程/讲次与实例 | MySQL 库 / 状态 | 当前 Evidence、时间 | PostgreSQL | 媒体与推荐 |
| --- | --- | --- | --- | --- |
| **MIT 6.0001 Fall 2016 Lecture 3，字符串 11:00–12:57**；`task_9530f04391b94c84b1ffc6a49228cecc` | `lecturelens_learning_loop`；SUCCEEDED，revision 2，READY | 16＝8 源字幕＋8 译文；0–112.590s | `lecturelens_agent_loop_test`：revision 2、READY、16 条 | **推荐**。既有专用 Sample Course；117.0169s，H.264/AAC，文件 hash 与公开历史记录一致，36.34s 处抽样音视频解码退出 0。现有浏览器完整链路仍待批准后的运行条件满足 |
| MIT 18.06 Spring 2010 Lecture 1，Row picture 04:20–08:39.679；`task_0119d101510843d18346ba9fa9467740` | `lecturelens_learning_loop`；SUCCEEDED，revision 2，READY | 36＝18＋18；0–259.679s | 同上库：revision 2、READY、36 条 | 备用。259.692767s，H.264/AAC，文件及 hash 符合来源清单；片段覆盖更多方程概念，但本阶段不扩大数学任务范围 |
| MIT 18.06 第 1 讲 07:00–08:30 片段；`task_70ec3dd6189843979174ed6d32d1237f`、`task_95c8e25dc07944cd82f20d567745738f` | `courselingo`；均 SUCCEEDED，revision 2，READY | 每个 12＝6＋6；0–90.005s | `lecturelens_agent`：均 revision 2、READY、12 条 | 不首选。数据库中上传状态 STORED，但在本次查找的本仓 `.data` 与 `/tmp/courselingo` 中未找到对应 assembled 文件；当前可播放性未证实，不能仅凭 STORED 断言存在 |

`strings.mp4` 总计有 57 个未删除成功实例（不是 57 节课程），只选上述已记录专用演示任务，不触碰其他账号。另查到 knapsack-dev（28 条、0–199s、媒体在）和两个各 4 条的历史视频；本次未核实它们完整的公开来源/许可对应关系，不列为已确认公开课程或扩大访问范围。其他已查询历史 schema 未发现未删除 SUCCEEDED 课程；此列表不声称覆盖所有容器/用户数据。

来源沿用 [Study v1 素材清单](../study-v1/sources.json)、[既有 Sample Course 报告](../recruiter-demo-phase-d/README.md)、[Row picture 来源](../learning-loop/new-course-source.json)。保留 MIT OCW 署名、裁剪/字幕平移说明及 CC BY-NC-SA 4.0 标记，不重新发布媒体或字幕全文。

字符串课胜在：课程主题集中，4 个学习目标能在两分钟内回看；Evidence 和源文件可直接核对；有明确的专用演示身份和历史真实链路。其旧结果是已消费历史证据，不能当本次通过。公开来源也不解除 owner 校验；只有合法控制原课程的账号可进入。若没有该账号的可用授权登录，不读凭据绕过、不重分配 owner，验收暂停。

## 5. 默认开启 feedback 的发布口径

建议在设计获批后的实现中，将 `feedback_store.enabled()` 的**未配置默认值**改为 true，示例模板同步 true；保留显式 `STUDY_FEEDBACK_ENABLED=false` 关闭。只改变发布默认值，不改 feedback-P 的提示词、工具集合、复核契约或预算。Java/Python Study 总开关、真实模型路由及鉴权均继续独立受控，不随此次默认值暗中打开。

- 生效用户：课程所有者。任意已登录用户可以在自己拥有且已就绪的课程使用；不能访问其他人的公开素材实例。共享 Sample Course 仍是既有专用身份，合成作答可被同身份访客看到；不在设计里加入或打印该身份凭据。
- 触发：先 SAVE_ATTEMPT 再点击“获取证据反馈”；保存即调用模型不在范围。API 返回的 feedback_enabled 控制显示；缺字段继续 fail closed。配置不完整、模型不可用时保留作答并给出现有可恢复提示。
- 降级：失败、超时、预算耗尽、复核两次失败或取消均保留原终态/Trace，继续阅读 Evidence、修改作答、按需查看参考答案；不自动换模型、补常识答案、改成 mock、把旧反馈挂成新版本。网络暂断先 READ 同一个 Run，同一提交重试沿用 request_key，终态后用户再主动开始新反馈。
- 权限/版本变化：401/403/404/409 回到登录或重新打开课程；不复用失效引用。旧反馈仍显示其 answer_version，不声称适用于新答案。用户核对/更正独立保存，不改模型原文。
- 回退：显式 false 后拒绝**新**反馈；已有作答、历史反馈和核对记录仍可读取。该开关不是热配置 API，修改进程启动环境通常需要重新加载 Agent 进程，不能承诺即时无重启回滚；此阶段不修改环境或重启任何服务。回退新反馈前由既有授权入口取消/排空活动 Run；关闭开关本身不会取消在途 Run。不删表、不换旧 worker 执行 feedback 队列。若需要进程操作，必须先单独获批，所有 `lecturelens-live-*` 等禁操作目标继续受原约束。
- 发布措辞：“实验性课程证据反馈默认可用，可核对、更正，不作为成绩。”验收前仍写“拟默认开启，未发布”。保持 P 的 6/6、8/8 和 AU 的有限结论，不替换旧报告或扩大为自动评分能力。

## 6. 验收方案（本阶段未执行）

### 5 个目标与时间标准

使用推荐课程 revision 2。下列时间来自本次数据库原字幕；E1–E8 的完整 ID 见 OBSERVATIONS。**正式执行前由人工观看原片核定目标、语义和可接受时间窗口，冻结后不按模型输出移动窗口。** 当前窗口是 Codex 按来源文本整理的模型辅助草案，尚无人工审阅者签名。

| ID | 学习目标（交给原 Study 入口） | 课程内通过标准/对应窗口 | 作答与反馈检查 |
| --- | --- | --- | --- |
| G1 | 解释“字符串对象不可修改”与变量绑定的区别，并给我两道基于本片段的自测题 | 引用 E1 0–17.574s、E2 17.574–36.340s；若解释重新绑定，须另引用 E6/E7 78.020–107.210s。不能把变量不可重新赋值当作不可变 | 保存一份“变量以后也不能改指向”的合成误解；反馈针对实际原句纠正并有对应时间引用 |
| G2 | 解释为什么对字符串第 0 个位置赋值不可行，结合片段出题 | 引用 E3/E4 36.340–63.954s，明确索引读取与索引赋值不同；题面/答案/评分依据均受这组证据支持 | 保存正确释义；反馈不应凭不同措辞制造错误；回看引用落在此区间 |
| G3 | 按课程的拼接和切片示例，解释如何让变量指向 yello，并给出自测题 | 引用 E5/E6 63.954–91.330s，涵盖新首字符与从位置 1 开始的剩余字符；不能声称原地修改 hello | 保存“这是修改原对象第一个字符”的合成错误；反馈引用支持新建/重新绑定的修正，不扩展到未教机制 |
| G4 | 用对象和变量的关系解释重新绑定以后原 hello 对象发生了什么，并出题 | 引用 E6/E7 78.020–107.210s，说明旧对象仍在别处、新对象不同；不讲课程未给出的 GC/内存回收结论 | 先保存错误版本，再保存正确版本并重新反馈；两次 feedback 精确绑定各自 attempt，历史结果不被覆盖 |
| G5 | 根据这段课程确定 Kubernetes 集群节点数量，并给出部署步骤 | **必须拒答**，产物为 insufficient_evidence，无 Kubernetes 实质答案、无无据练习；不以执行失败代替拒答。可以保存解释缺证据的理由 | 拒答路径不制造作答/反馈。此课程外目标不要求拼出无关 citation；这是对课程内引用要求的明确例外 |

G1–G4 每个目标必须同时满足：解释及每道题有相关、可解析的引用；Evidence ID、文本、revision 与 MySQL 权威快照一致；反馈的每条建议有自己的支持引用，实际点击后 `seeked` 时的 currentTime 距 start_ms/1000 不超过 1 秒，目标落在人工冻结的对应片段内（边界允许 1 秒播放器采样误差）；人工回看确认该时段确实支持结论。只比对 ID 存在或数据库时间合法不算通过。跨片段解释要覆盖全部必要来源；译文可用其同源、同时间片段，但不得靠译文错误支撑结论。若浏览器自动播放受限，允许人工点击播放，仍须验证定位和实际画面。

最低发布演示门槛：G1–G4 全部完成真实学习→实际合成作答→独立反馈且引用/时间通过；G5 正确拒答；刷新恢复、至少一次修改后反馈及关闭新反馈后历史可读通过。所有首次失败/重试均逐条保存，不选择成功历史 Run 冒充本次完成。

### 审阅与证据

结果表预留 `goal_id / run_id / source_attempt_id / feedback_run_id / revision / citations / expected_window / observed_seek / model_mode / result / failure_reason / reviewer / review_mode / reviewed_at`。正式 reviewer 必须是实际人工审阅者，review_mode 如实写“人工（模型辅助整理）”或“人工”；若仅由 Codex 核查则写“模型辅助，待人工”，不计为人工验收通过。运行时复核器不是外部审阅者。

冻结实现 SHA、模型用途/版本和预算后才执行，期望答案不进入模型上下文。模型调用、token、延迟、工具决策与改变后续行动的观察分别记录；未知值不填零。反馈既有质量评测不重跑，本组目标仅检查当前发布链路与引用。不得把这里的数据再称为 fresh holdout。

### 服务、进程与批准边界

| 需要的能力 | 可复用资源/检查 | 本阶段与后续条件 |
| --- | --- | --- |
| 浏览器、Vue | 当前代码的原生学习页，后续可用本地前端预览和 Chromium | 本阶段仅源码调研；已有固定组件测试可复用，真正 E2E 不 mock HTTP |
| Java 鉴权/课程/Evidence/媒体网关 | 必须连接匹配 `lecturelens_learning_loop`、原 owner 和对应 assembled 根目录的**已有授权服务** | 本机 8080/8084 无监听；没有证明其他现存端点具备该对应关系。若验收必须启动/重启 Java/后端：**需用户批准，本阶段不执行**。不运行旧 serve.py backend，不恢复 P2-1c，不以新隔离 Java 解阻 |
| Python Study/反馈及既有检索 | 与该 Java 互认的 Agent、原模型配置和对应 PostgreSQL | 不能把“8090 有监听”当作已绑定正确课程库/版本。部署、配置启用、服务重载需另行批准；本阶段不读密钥、不调用模型 |
| MySQL 权威课程 | 已有 demo 容器内 `lecturelens_learning_loop` | 当前仅 READ ONLY 查询，验收亦不在该实例做 DDL/GRANT/直接写入；不上传、重试处理或删除课程。若旧后端启动会迁移/写库，不满足本方案前提，停止申请进一步授权 |
| PostgreSQL 学习状态及索引 | 课程派生索引现存于 `lecturelens_agent_loop_test`；它虽名含 test，却有既有演示数据 | 后续学习 Session/Run 只经原 Agent API 写入；**不能将此库用作会清理数据的机制测试库**。机制测试另用新建独立 `*_test` 库，不覆盖既有记录 |
| 媒体、基础设施 | assembled 本地视频；现有 Redis/MinIO 等依后端依赖复用 | 播放源码实际读本地 assembled，并非直接读取 MinIO；不启动/重启任何容器，不新建媒体任务/ASR/翻译。RocketMQ 不承担当次学习编排 |

未来若实现默认值改动：用 `scripts/dev/run_check.py` 按 [执行指南](../../docs/LOCAL_CHECK_EXECUTION.md) 运行相关 Python 机制测试，指定独立 PostgreSQL 测试库，DB 用例跳过不算通过；前端只跑所改引用/反馈和播放器相关用例及必要构建。Java 无改动，不运行会启动 JVM 的构建/测试。机制检查与真实模型结果分表汇报。

本阶段不启动服务栈，未运行这些测试或真实验收。后续时间盒内若合法既有服务不可用，交付设计/实现与“真实验收受阻”状态，不能通过启动隔离 Java、直连 Python 绕过 Java 权威、改库身份或重新入库来绕开限制。人工未确认或真实链路未通过均不发布默认开启。

## 7. 预计改动与 1.5 天时间盒

以下均是**设计获批后**的预计工作，不是本次已修改内容。以 8 小时/天计，总计 12 小时；不含用户审批等待，不以等待为由自动扩大授权。

| 文件/范围 | 预计变更行数 | 用途/预算 |
| --- | ---: | --- |
| `agent-service/src/lecturelens_agent/study/feedback_store.py` | 1–3 | 仅未设置开关的默认值；不改反馈算法，0.5h |
| `.env.agent.example` | 1–3 | 示例默认值与显式回退说明；不修改真实环境，计入上项 |
| `agent-service/tests/test_study_feedback.py` | 20–40 | 将旧“默认关闭”断言改为默认开启＋显式 false 拒绝，并检查历史可读/作答不受影响；真实独立 PostgreSQL，2h |
| `frontend/src/components/task-detail/PracticeFeedbackPanel.vue`、`CourseAgentPanel.vue` | 合计 6–15 | 复用现有时间格式，明确片段起点，1h |
| `frontend/src/components/task-detail/PracticeFeedbackPanel.test.ts` 等现有相关用例 | 10–25 | 时间文本与原 seek 单位、多个引用仍正确，1h |
| `docs/DEPLOYMENT.md`、`docs/ARCHITECTURE.md`、`docs/L3_LEARNING_FLOW.md`、`docs/AGENT_PRODUCT_CONTRACT.md`、`agent-service/README.md`、必要的根 README 说明 | 合计 40–80 | 发布状态、启用/回退/owner 范围一致；保留历史日期结论，1h |
| 新 `eval/p2-2a-acceptance-<UTC>/` 的计划、结果与审阅记录 | 约 100–180 行文档/脱敏结果 | 预标注、5 个目标、回看和失败记录，4h |
| 既有环境只读预检、审核收尾 | 不承诺新增代码 | 1h 预检＋1.5h 缓冲；无 Java/SQL 变更 |

预计生产代码 7–18 行，测试 30–65 行，模板/公共文档 41–83 行，验收文档另计；无需新文件抽象或框架。若出现无效时间的真实缺陷，最多追加现有入口 15–30 行和相应测试，消耗缓冲而非自动扩大范围。

12 小时到点先报告实际状态；**预计超过 2 天时**收缩为单一字符串课程、原有片段起点 seek、默认值和显式关闭、既有页面内反馈，不做额外呈现/无现象的防御改造；保留 4 个课程内目标＋1 个拒答和人工审阅门槛。若服务/账号不可用或质量不达标，不降低门槛、不替换为录屏通过，保留失败并暂停发布。数学备用课、多课程推广、逐词时间和媒体链修复全部移出本次。

## 8. 明确不做

- Agent 调用 ASR/翻译；新课程上传或处理链运行；T1/P2-1c 重试/排障、启动隔离 Java。
- C/E、主动提醒、联网检索、多 Agent、新工具、新框架、新抽象、Agent 重写。
- feedback-P 重评或改提示/评分口径；自动评分、长期记忆、自适应复习调度。
- 公共素材跨 owner 共享、修改课程所有权、直接向对方服务表写入、变更历史 Evidence/失败记录。
- 本阶段代码修改、运行配置变更、部署、合并 PR、改 base、force push、推送本设计。

待确认的是上述范围、推荐课程、默认开启与验收口径。设计确认不自动等于部署、进程操作或扩大数据访问授权。
