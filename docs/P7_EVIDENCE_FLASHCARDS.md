# P7 证据闪卡与 FSRS（实验性，离线 Mock）

学习者在课程页打开「闪卡复习」，显式生成一组卡片，先回想、翻面核对、用 Again / Hard / Good / Easy 自评。每张卡至少引用一条当前版本 Evidence，可沿现有原文定位和 revision 双检查回看视频。评分不是程序判分，也不是掌握程度判断。

## 生成与执行边界

`GENERATE_CARDS` 需要显式 Session 和 request_key，产生 `task_kind=flashcards` 的 Run。
模型协议选择 `search_card_evidence` → 根据观察选择继续搜索、`create_evidence_cards` 或 `stop_cards`。
每组 1–6 张；检索观察最多 8 条；每卡 1–4 条引用，引用必须来自已观察集合，提交时重新 READ。
程序回填权威原文与时间，拒绝空文本、无时间区间或缺失来源。Mock 当前生成最多 3 张，答案直接摘自来源，**只证明机制**。

复用现有 LangGraph checkpoint、持久调用 journal、Session 执行锁、worker token、取消和版本栅栏。
每 Run 最多 6 次模型决策、8 次工具、64,000 保守 token 预留、默认 90 秒；重启不重置预算。
工具结果与卡组在一个事务保存，Run 成功前卡片不可读；迟到取消、删除、revision 变化导致结果不可发布。
未知模型调用结果按原 journal fail closed。无证据时保存 stop 工具结果，不伪造卡片。

本轮 **只有 Mock 生成入口**，`real` 模式在模型配置解析前拒绝 `FLASHCARDS_MOCK_ONLY`。
没有真实 Provider 适配或真实质量结论。Mock 不作为真实失败的回退。

## 数据、调度和恢复

Python 启动时按现有幂等 DDL 初始化方式新增：

- `study_deck`：唯一 Run、标题、调度 policy 快照。
- `study_card`：卡面、答案、canonical citations、FSRS JSON 状态、UTC due_at 和乐观 version。
- `study_review_log`：card/request_key、expected_version、自评、服务端 UTC 时间、调度前后状态与 policy；应用只追加，不改写。

全部属于 Python/PostgreSQL 学习产物，经 Run/Session 间接绑定 owner/course/revision。
Java 不新建表、不写 PostgreSQL；Python 不写 MySQL。
每个读写以签名 owner/course/current revision 加成功 Run 连接查询，卡 ID 不授予权限。
旧 revision 的卡立即从新快照队列消失，不迁移旧调度到新 Evidence；旧行保留以免篡改历史。
课程删除由原 Evidence tombstone → `purge_deleted` 清理 Session/Run/checkpoint，外键级联清理卡组、卡、评分。
Java 和 Python 的权威 CHECK 同步拒绝已删除课程，异步清理期间也不能读取缓存。

采用官方 [py-fsrs 6.3.0](https://github.com/open-spaced-repetition/py-fsrs/tree/v6.3.0)，[MIT 许可](https://github.com/open-spaced-repetition/py-fsrs/blob/v6.3.0/LICENSE)，锁定 wheel hash。
FSRS-6 默认 21 参数、目标记忆率 0.9、learning 1/10 分钟、relearning 10 分钟、最大 36,500 天，关闭 fuzzing。
完整参数写入 deck/review 的 policy，代码入口 `study/scheduling.py`。
调度使用 aware UTC 时间；客户端不提供 review 时间。数据库 `timestamptz` 保存绝对时刻，UI 下次到期按本地显示；「今日已复习」按 UTC 日计不同卡数。
固定 golden 覆盖首次四评分、学习、遗忘、重新学习和时区等价。没有参数训练或长期学习效果验证。

评分先锁卡，再检查已有 `(card_id,request_key)`：正文/expected_version 相同返回最初 log，即使当前卡版本已前进；不同则 409。
新 key 必须匹配当前 version 且卡已到期，否则 409；日志和 version+due_at 同事务提交。
两页签同版本只有一次有效评分；同 key 并发返回同一结果。
未知网络结果在 UI 提供「重试上次评分」，保留原 key 和评分；冲突刷新，禁止把旧评分重试意外应用到下一卡。

队列按 due_at/card_id 稳定排序，一页最多 50 张并返回总到期数。已提交评分改变队列，因此刷新、换页签、切回课程均恢复当前已到期卡与今日已复习数；翻面本身不是学习记录，刷新重新显示卡面。不承诺未提交自评或某次翻面跨刷新保存。

## 网关命令

继续使用 `POST /api/tasks/{id}/study/command`，浏览器不传可信 owner/revision。

| operation | 参数 | 返回 |
| --- | --- | --- |
| `GENERATE_CARDS` | session_id/request_key；可选 goal | 原 Run；通过 READ/CANCEL/EVENTS 恢复和取消 |
| `DUE_CARDS` | 无 Session 要求 | cards≤50、due_count/total_count、reviewed_today、next_due_at、server_now、generation |
| `READ_CARD` | card_id | 当前快照的完整卡与版本 |
| `REVIEW_CARD` | card_id/request_key/expected_version/rating | 不可变 review、replayed |

生成作用于整门课程，独立于练习/Tutor 的段落选择；闪卡页面不显示其选择器。
Java 对生成检查 readiness，对读/评分不要求检索索引已就绪；全部操作前后校验 owner/course/revision。
`DUE_CARDS` / `READ_CARD` / 原文跳转不创建 Session/Run、不调用模型、不写调度。
初次打开只读，生成必须点击；评分不调用模型。`queued_cards_v1/running_cards_v1` 隔离旧 worker，唯一活动 Run 索引同时覆盖旧/新状态。
本轮不部署；回滚先停止新生成、取消/排空闪卡 Run，保留新增表与状态，不把新状态改名让旧 worker 消费。

## 产品对照与限制

沿用 YouLearn 的卡面→翻面→按回忆难度安排下次复习，以及已存学习对象可重开的交互。
差异是每张卡拥有版本化 Evidence 身份、原文与视频时间入口；来源存在性和语义支持率分别验收。
对照依据为用户提供的 P1A 只读竞品报告，本轮未访问竞品或调用其服务。
选择题程序判分、薄弱点、多轮 Tutor、PDF、播客仍属后续方向；开放题继续只给反馈。

机制结果与失败记录见 [P7 报告](../eval/p7-flashcards/REPORT.md)，
出处核验见 [通用离线入口](../eval/source-support/README.md)。真实生成的出处支持 ≥0.90、未见课程泛化、长期复习效果均为 **NOT_RUN**，不继承 AU/P6 质量结论。

独立的[真实评测通道](../eval/p7-real/README.md)已实现双开关、隔离双账本与 24 任务本地快照运行器；本轮仅离线验证，真实 Provider 请求为 0。产品仍为 Mock only，原冻结身份与上述质量边界不变。
