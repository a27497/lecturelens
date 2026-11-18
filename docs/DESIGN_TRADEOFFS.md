# 设计取舍

每一条写明：选择了什么、放弃了什么、证据在哪。组件和协议细节见[架构](ARCHITECTURE.md)，代码入口见[仓库导览](PROJECT_MAP.md)。

## 1. Java 管课程事实，Python 管 Agent 执行

**选择。** Java（Spring Boot + MySQL）负责认证、上传、媒体处理和权威 Evidence：谁拥有课程、当前是哪个版本、是否已删除。Python（FastAPI + LangGraph + PostgreSQL）负责学习任务：模型决策、工具编排、Session / Run 状态、学习产物和反馈。Python 不读写 MySQL，Java 不写 Agent 表。Agent 每次调用课程工具（CHECK / SEARCH / READ / WINDOW）都通过签名 HTTP 回到 Java 校验所有权和版本。

**放弃。** 放弃了单体部署的简单：多一个服务、一个数据库、一层签名协议，每次工具调用多一次 HTTP 往返。也放弃了 Python 直接查 MySQL 的便利。

**换来。** 权限只有一个权威来源。Python 侧的索引、缓存或历史快照都不能授予访问权；课程删除或版本变化后，正在运行的 Run 在下一个工具边界被拒绝。Agent 的实验代码可以独立迭代，不碰课程数据。

**证据。** [产品契约](AGENT_PRODUCT_CONTRACT.md)；[多用户隔离实验](../eval/multi-user-phase-e/README.md)：2,160 次跨用户、跨课程、跨 Evidence 的负向请求，0 次越权。

## 2. 三条问答路径并存：RAG、Light Tutor、Study Agent

**选择。** 三条路径分开实现，界面上也是三个入口：

| 路径 | 做法 | 适合 |
| --- | --- | --- |
| 课程问答（RAG） | Java 检索 → 一次模型调用 → 引用校验；没有证据时在调用模型前拒答 | 快速查一个点 |
| Light Tutor | 检索 → 一次生成，回答内联引用 | 解释一个概念 |
| Study Agent | 模型选择工具（检索、补读、受限计算、出题、报告证据不足），观察结果后决定下一步；草稿经复核才发布 | 解释 + 练习 + 作答反馈 |

**放弃。** 没有把所有请求都交给 Agent。Agent 更慢、更贵，失败面更大：在 L4 留出集上 P50 延迟 14.5 s，对比 RAG 1.10 s、Tutor 4.45 s；每题成本 USD 0.0074，对比 0.00037、0.00075。

**结论。** L4 显示，**单轮问答**的正确率由 Light Tutor 领先（严格正确率 0.718，RAG 0.417，Study 0.426）。Study Agent 的价值在练习、作答和反馈这类多步任务，不在单题问答。它成功产出时答案正确率接近 Tutor（探索性：92/126），主指标低主要因为 29% 的 Run 以产品错误结束（见第 7 节）。

**证据。** [L4 结果](../eval/l4-benchmark/README.md)、[results.json](../eval/l4-benchmark/results.json)。

## 3. 预算持久化，重试有上限

**选择。** 每个 Study Run 默认最多 12 次模型调用、8 次工具执行、600,000 token 保守预留、90 秒 deadline。预算在调用**之前**扣减并写入 PostgreSQL，崩溃重启不会重置；deadline 从首次领取开始计时，包括停机时间。练习草稿最多提交两份候选。其他重试同样有界：MQ 投递最多 8 次后转 DEAD；检索槽位满时返回 `503` + `Retry-After: 1`，不排无限队列。

**放弃。** 部分本来能完成的 Run 会因预算失败：L4 留出集 288 次 Study Run 中有 11 次 `RUN_BUDGET_EXCEEDED`。"多试几次也许能过"的成功率被有意让出。

**换来。** 失控循环和成本上限可预期；缺失 usage 不当作零成本记账。

**证据。** [架构 · 预算、取消与删除](ARCHITECTURE.md#预算取消与删除)；[Agent 执行说明](L2_STUDY_AGENT.md)；[并发配置](AGENT_CONCURRENCY.md)。

## 4. Fail-closed：拿不准就停，不降级

**选择。**
- 课程问答没有检索到证据时，在模型调用前直接返回“当前课程内容中没有找到明确依据”。模型回答没有有效引用时同样拒答，不会把全部候选当作引用。
- Dense 检索出错时报告不可用，不悄悄切回关键词检索。
- Study 草稿的复核输出不合规（`MODEL_REVIEW_CONTRACT`）时，Run 失败，不发布未复核的内容。
- 真实 Provider 失败不切到 Mock；Mock 与真实 Run 不能互相恢复；演示模式启动时拒绝与真实 ASR / LLM 混用。

**放弃。** 可用率。L4 里 63/288 次 Study Run 因复核输出不合规失败，这是 Study 主指标偏低的最大原因；RAG 有 17/216 次误拒（应答题被拒答）。

**换来。** 用户看到的每条结论都有可定位的课程原文；系统出错时用户看到的是失败，而不是一段看起来正常的错误内容。

**证据。** [架构 · 课程阅读与 QA](ARCHITECTURE.md#课程阅读qa-与浏览器恢复)；[复核说明](L2_QUALITY_REVIEW.md)；[L4 失败类别](../eval/l4-benchmark/results.json)。

## 5. 版本栅栏与幂等

**选择。**
- 课程内容每次变化递增 revision。Study Session 绑定 owner / course / revision；revision 变化后旧 Session 失效。
- Java 的 `GenerationFence` 在生成前记下来源版本，发布时重新加锁核对；过期 worker 的结果不能覆盖新数据。
- 创建 Session / Run 用 `request_key` 幂等；工具结果以 `run_id + call_id` 唯一。崩溃恢复先回读已提交结果，不重复执行副作用。
- 媒体任务的投递是"至少一次"，执行资格由数据库租约保证每个 task ID 只执行一次。

**放弃。** 不承诺分布式 exactly-once，也不承诺外部模型恰好调用一次：模型响应在 checkpoint 之前崩溃，恢复时可能重发请求，这次调用的预算已经扣过。

**证据。** [架构 · 持久状态与恢复](ARCHITECTURE.md#持久状态与恢复)、[投递、执行与故障恢复](ARCHITECTURE.md#投递执行与故障恢复)；[可靠性验证](C0_C3_EXECUTION.md)；[审批与崩溃恢复](STUDY_APPROVAL_RECOVERY.md)。

## 6. 冻结评测与留出集纪律

**选择。**
- 评测前先写计划：题集、指标、裁判提示词、停止条件和费用上限，冻结后只公开哈希。
- 题目在开发集上只用来调裁判，最多 2 轮；留出集讲次与开发集不重叠，跑完、校验通过后才揭盲。
- 失败的试验和产品失败照实计入，不重跑来"洗"成绩。改了产品行为就要新的候选身份和新的留出集，旧候选不再编辑。
- 账号余额耗尽这类外部事故导致的单元，按预先写定的规则只重跑一次，并保留原记录。

**放弃。** 速度和"好看的数字"。L4 的金标准经过三轮审核和一次方法修订（改为 nugget 金标准），每次修订都在任何产品输出之前完成并留了记录。

**证据。** [L4 freeze.json](../eval/l4-benchmark/freeze.json)（计划、题集、审核文件的哈希与冻结历史）；[评测索引](../eval/README.md)（历史候选、失败试验）；[评测工具审查分诊](../eval/l4-benchmark/HARNESS_REVIEW.md)。

## 7. L4 暴露的局限（仍然存在）

| 局限 | 数据 | 现状 |
| --- | --- | --- |
| Study 复核输出不合规导致失败 | 63/288（22%）为 `MODEL_REVIEW_CONTRACT`，总失败 83/288 | 未修；修复需要新候选和新留出集 |
| RAG 检索漏召回时正文写"课程没有依据"，但不返回结构化拒答 | 实质错误率 0.186，多为这类情况 | 未修 |
| Study 练习产物附带大量与论断无关的引用 | 引用精确率（ALCE 逐对）0.255 | 未修 |
| 方法局限 | 题目与金标准由 AI 撰写（经 Codex 全量审核）；裁判 deepseek-v4-pro 与被测模型同厂商，且在复核样本上偏宽（18 对 1）；只有 6 个留出讲次；公开课可能在预训练数据中 | 写在每处结果旁边 |

**证据。** [L4 README](../eval/l4-benchmark/README.md)、[results.json](../eval/l4-benchmark/results.json)。

## 8. 一键演示默认用 Mock

**选择。** `scripts/demo/up.sh` 默认使用仓库里的确定性 Provider（Java 演示 LLM、Mock ASR、Agent `AGENT_LLM_MODE=mock`），不需要任何 key，界面上标“本地演示 · 无外部 AI”和“Mock 流程测试”。`--real` 用调用者自己的 key。

**放弃。** Mock 模式看不到真实的回答质量，也演示不了真正的拒答：Mock 回答总是引用检索到的第一条证据，而 Dense 检索总会返回最相近的片段。README 的录屏因此用真实模型录制，并在每一帧标注 Real。

**证据。** [一键演示脚本](../scripts/demo/stack.py)；[录屏脚本](../scripts/demo/record-demo.mjs)。
