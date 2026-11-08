**PHASE1_C_STATUS = PARTIAL**

**ROOT_CAUSE = PARTIAL**

**OFFLINE_REGRESSION = PASS**

**REAL_MODEL_QUALITY = NOT_RUN**

**NEXT_RECOMMENDATION = SIMPLIFY_TUTOR**

已完成一次有界修复及离线验证，但没有证明真实教学质量改善，也没有解决同一历史第三回合在原预算内完成修复的问题。因此不建议立即申请下一次真实费用授权。已证实的协议／状态／预算因果与模型为何忽略前提的推断分开记录，不能以 197 项机制测试替代教学验收。

工作树 `/home/dev/.codex/worktrees/phase1c-tutor-repair-20261108/phase1a-v19-runner-20261108`，分支 `codex/phase1c-tutor-repair-20261108`，实现基线为 frozen runner HEAD `2ecf4d52af1084bad405e98a6e78027bf4c5ab5d`。这是独立实验修复，没有整体合并 v19 到 Phase 0。失败证据来自 Phase 1-B commit `b550fc8a762fa20e75ca029198f0eea35e860f87`，ZIP SHA256 `832e20a6e066603b57a858a50ddbd2eda355757ba821e4119c6056339299b30d`。原 Packet SHA256 `ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e`、原 Candidate SHA256 `16a094317ba06b3c1932280c7dbb15a07d47200dc74ed8e08e25465e10549ae9` 不变。测试对整个 ZIP 和包内 manifest 逐字节核验；私有副本为只读 0400，不提交真实回答正文到 Git。收尾 commit 可用 `git log -1 --format=%H -- eval/phase1c-failure-repair/REPORT.md` 解析。

| 回合／问题 | 已证实的证据与根因 | 未证实的部分 |
| --- | --- | --- |
| 1：completed 却缺必要讲解 | `003-response.body` 的四个块全是 source；发布答案 2680 字符包含原课程 `length=0` 示例，未包含题目要求的 Ada／Grace 变式。SelectedFinish 允许此组合，UsableTutorRuntime 检查归属、长度、模式、来源后即可发布，没有教学内容或语义覆盖门禁。 | 不能证明模型只因某一句提示而选择摘录；也不能因有一个 explanation 块就断定所有必要点已覆盖。 |
| 2：泛化提问 | 响应 005／006 均选择 locate_rule，最终答案来自 HINT_ACTS 的固定泛问，不含 final print 焦点。已有 locate_body 可更具体，故不是“协议完全无法表达缩进提示”；缺陷在于合法泛意图没有绑定当前学习问题。响应 005 还选择了 389 字符的 hint span，超过 240，使用了本轮唯一共享修复。 | 新 focus 只能绑定学习者短语，不能自动证明意图／来源在教学上相关。 |
| 3：变式被替换 | 请求 007–009 的 history 均完整含原第一回合 learner_text，明确初值 2、Ada／Grace。响应 009 却明确改述原课程的 0、Curie／Darwin／Turing。**缺少前文传输已排除**；语义上确实偏离，而非调用失败。 | 来源示例和先前摘录竞争注意力是合理推断，不能从单次输出证明模型内部因果或保证提示修复有效。 |
| 3：无法预留修复 | 首个 feedback anchor 655 字符超过 400，第二个也有 475；一个 explanation 为 1043，超过 900。冻结代码离线重建精确得到普通预留 53839、修复 25954，总计 79793＞64000，在修复发送前停止。源文、完整历史、schema 与被拒全文重复进入请求放大了代理量。 | 美元账本未耗尽；不能以提高 US$0.30 上限解释这次停止，也不能把 UTF-8 请求大小代理量说成真实 token 数。 |

原三回合 2 completed／1 failed、9 个真实请求、本地历史费用 US$0.011272800、供应商账单 UNKNOWN、无未知发送责任等结果保持原样。旧授权已消费，未清除 claim、改写结果或重新执行。完整结构化独立 AI 语义评审仍未完成；上述可直接观察的遗漏不冒充专家评审。

本轮只改两个现有 Python 实现模块，没有新增一串 Tutor 版本：

- `selection_runtime.py`：answered 至少有 explanation／calculation；source-only 使用原一次共享修复，重复违规停止。上下文保留全部已完成学习者原话及教学解释，省去先前纯来源摘录；计算等无法无损分离时保留原答案。完整已发布答案、引用和被拒提案仍在 PostgreSQL／GET，未隐式截断。多于六回合的前提继续保留。
- 同一模块：focus 必须是当前 learner_text 的有界原文短语，不能凭空加入答案；与现有受控 hint act 合成问题，没有开放自由解答通道。source_units 保持完整，新增计算得出的 span_ends 观察以暴露原字符容量，验证规则不变。修复输入只重复结构／大小和确切拒因，完整原草稿留在持久 checkpoint。
- `usable_runtime.py`：仅抽出默认行为完全相同的 render_hint 钩子，由实验 selected 候选使用 focus。其他候选的受控提示、字段、限额不变。新身份为 `phase1c-tutor-repair-development`；工厂没有启动或设为产品默认。

没有把题目名字、固定数值、答案或正确引用写进产品逻辑。只在测试／不可变失败分析中使用原题事实。正例还覆盖另一课程主题的有界计算；A03 的“合法引用＋错误解释”依然能穿过结构验证，专门作为已知语义负例保留，不能当作质量 PASS。

所有限额保持原样：三次普通决策＋一次共享 Finish 修复／回合，原实验账本最多 12 请求、输出 4096 tokens／请求、并发 1、HTTP retries 0、本地 US$0.30，正文 4096／反馈 1024 字符，以及原 block、anchor、deadline、session、wire 上限。没有调整费用账本、预算结算、权限、取消、幂等或恢复语义。旧冻结入口在本工作树会因源码改变而拒绝，不能使用旧 manifest／grant 调用本候选；没有新真实入口或新授权。

关键负例没有消失：对相同历史第三回合输入与提案，修复后重建为 **47630＋21725＝69355＞64000**，仍不能发送修复。下降了 10438 代理单位，但没有据此宣布该路径成功。合法人工编写的完整讲解可在预算内保存；完整三回合 authored 对话可执行，source-only 历史重放可在第四个 authored 修复响应后保存；这些都不是新的真实模型生成。没有为了绿色结果放大上限、丢弃前提、删掉必要内容或自动补跑。

验证结果与真实退出码见 CHECKS.json，原始记录在 `.data/phase1c/evidence/`：

| 检查 | 实际结果 |
| --- | --- |
| 初次组合回归 | 192 passed、3 failed，退出 1；两个错误是回放适配器未按真实 Provider 归一化 usage，另一个是测试误读幂等返回字段。原日志保留，未修改历史输出；修复测试适配后继续。 |
| 候选专项 | 23 passed、0 skipped，退出 0，24.60 秒。 |
| 最终组合回归 | **197 passed、0 skipped，退出 0，118.38 秒**；含候选、Python Tutor／引用、未修改 v18 机制。原 frozen CLI／grant 的三个旧入口节点不适用于改过源码的候选，选择清单明确列出，没有修改它们。 |
| 真实 PostgreSQL | 新容器、新持久卷，仅 `127.0.0.1:25841`；fsync／synchronous_commit=on，独立 acceptance 库。每例独立 schema；最终只读核对剩余测试表 0。 |
| 状态及跨边界机制 | 完整讲解与注释代码、索引、历史条件与纠错、具体 hint、另一主题、幂等 GET、超过六回合、预付修复恢复、来源变化、越权、取消、预算不足；另含原 Python ASGI 签名／权限回归。没有运行真实 Java 服务栈。 |
| 原／新请求构造分析 | 各退出 0，无 Provider／数据库连接；旧值精确复现 79793，新值仍为 69355。 |
| 静态检查与保护 | Python Ruff、格式、内存编译、原 v19 只读 verify 均退出 0。初轮回归失败日志保留；lint／格式问题修正后通过。 |

长检查由原样复制的 `scripts/dev/run_check.py` 在任务专用 `/dev/shm/lecturelens-phase1c-checks-20261108` 管理；该日志／临时文件系统约 8 GiB，原磁盘门禁实际通过，没有修改或关闭门禁。源码只读位于新工作树，所有记录和回放产物已复制为持久 `.data/phase1c/evidence/`；Supervisor 终态、退出码、子进程回收及 hash 可复核。Python socket fence、真实 HTTPTransport 禁止替身、凭据读取失败断言共同保护离线测试；PostgreSQL 使用已验证归属的固定 loopback 目标。未调用付费生成、reviewer 或 embedding，**本轮新增真实请求 0，新增模型费用 US$0**。

Java、Vue、浏览器和整栈部署未运行：这两个 Python 模块未改变浏览器 API、Java Evidence 权威或前端代码，不继承历史全栈通过状态。Phase 0 **GitHub CI=PENDING**。测试库已停止且卷保留；原工作树、冻结源码、旧失败 ZIP／原始证据、业务数据库和既有服务保持不变，详见 PRESERVATION.json。无 push、PR、main 合并、部署、压测或 full16。

下一步建议 **SIMPLIFY_TUTOR**：先简化教学／修复输入表达，并在不丢学习者前提、完整产物或来源条件的情况下，用同一失败回放证明关键四调用路径能够容纳，再考虑新冻结身份和新授权。当前预算负例仍失败，语义必要点也缺独立完整评审，因此不把本候选列为已具备真实复测准备状态。不自动进入新 Smoke、Phase 2 或生产。
