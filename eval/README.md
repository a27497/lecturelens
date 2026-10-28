# LectureLens Evaluation Index

`eval/` 保存可公开的冻结任务、汇总报告和失败历史；原始 provider 请求/响应、凭据、媒体、数据库快照和大体积回放留在 Git 忽略的 `.data/`。

## 阅读导航与证据状态

| 要核对的结论 | 入口与边界 |
| --- | --- |
| main 的实现与实际部署 | [仓库导览](../docs/PROJECT_MAP.md)、[版本快照](../docs/PROJECT_MAP.md#版本与部署快照)；本目录不是部署清单 |
| 冻结候选的真实任务质量 | [AU 完成报告](phase-completion/FINAL_AU.md)；开发/新保留分别统计，保持已知课程范围和原候选身份 |
| 工具与恢复协议 | [容错报告](tool-resilience-20261014/README.md)、[审批恢复](approval-recovery-20261014/README.md)；main 已收录实验实现，确定性模型验证机制，不重评 AU 教学质量 |
| 检索对照与失败演进 | [检索 v2](retrieval-v2/README.md)及下方历史目录；检索指标、执行完成率和答案正确性分别解释 |

下文“未发布”及各实验的线上状态指验收当时；报告不是当前提交重新运行的成绩。原候选身份、保留集边界和失败判定保持不变，本轮只补充导航，不删除或移动证据。

部分历史验收链接指向未公开的本机回放，不能在 GitHub 打开；审批矩阵的 `matrix-final/raw.jsonl` 链接指向还原后生成的文件，公开分片及哈希见[清单](approval-recovery-20261014/public-record-parts.json)，还原入口见[既有脚本](approval-recovery-20261014/restore_public_records.py)。本轮未生成或改写这些记录。

## 最新冻结候选的历史结论

当前最新的 Study Agent 有限范围候选是 **AU**。开发目标严格 31/31、全新保留目标严格 8/8，独立 PostgreSQL 机制测试 547 项通过，并完成真实浏览器学习闭环、恢复、取消、越权和删除验收。候选尚未发布，也不证明未见课程泛化、自动评分或长期记忆能力。

- 当前完成报告：[`phase-completion/FINAL_AU.md`](phase-completion/FINAL_AU.md)
- 完整持续记录：[`phase-completion/RESULTS.md`](phase-completion/RESULTS.md)
- 调用审计：[`phase-completion/AUDIT.json`](phase-completion/AUDIT.json)
- AU 开发逐题复核：[`phase-completion/AU-development-review.json`](phase-completion/AU-development-review.json)
- AU 全新保留复核：[`phase-completion/AU-holdout-review.json`](phase-completion/AU-holdout-review.json)

求职增强实验最新完成 **Phase E · Multi-user Agent Concurrency & Isolation**：5/20/50-user 固定响应、5/10-user 真实模型、取消晚到结果及两种进程崩溃恢复已实测，2,160 次负向权限请求 0 绕过；并发检索 503 和全部失败保留。这是执行/隔离实验，不更新 AU 的教学质量结论。见 [Phase E 报告](multi-user-phase-e/README.md)；本轮停止，不开启 Phase F。

未发布的工具容错候选增加持久预算内的有界只读重试、严格参数校验和公开失败分类。固定本地 HTTP/MCP 故障矩阵与改动前源码对比见[工具容错报告](tool-resilience-20261014/README.md)；确定性 provider 只验证机制，不更新 AU 教学质量结论。

该候选的健康路径连接开销已有独立 profiling 和串行对照修复，旧并发延迟口径在[延迟复核报告](tool-resilience-latency-20261014/README.md)中更正；旧原始记录与结果保持原样。

后续执行指标统一从持久记录生成，命令、缺失处理和本轮 1,260 Run 报表见[指标汇总](study-metrics-20261014/README.md)。这不改判已有质量评测，也不将预留 token 换算为金额。

工具请求与已执行调用的分母修正、15 个真实持久化 Run 的 DB/JSONL 对照见[指标补充验收](study-metrics-requests-20261014/README.md)，旧报表与故障资产保持原样。

[检索评测 v2](retrieval-v2/README.md)已完成 6 门 MIT OCW 课程、18 个讲次、735 Evidence、120 题的固定对照：80 开发/40 按课程隔离的保留题，保留仅采集一次，模型辅助标注、无人工金标准。CE 的保留 Coverage@3 观测最高，但配对区间包含 0、延迟明显增加，不改变生产默认。Phase A 原数据与结果保留。

未发布的可选审批断点与强杀恢复验证见[审批与恢复报告](approval-recovery-20261014/README.md)：523 个不同注入点各一次、18 个审批边界组合各三次，共 577/577 次不变量检查通过；96 次模型结果不明采用保守失败。审批仅限课程所有者，默认关闭。确定性模型机制验证不更新 AU 教学质量结论；[验收包](approval-recovery-20261014/VERIFY.md)提供原始记录复算与抽样复跑命令。

## 历史目录

| 目录 | 作用 |
| --- | --- |
| `study-v1/`, `study-v2/` | 早期 Study Agent 任务与真实课程基线 |
| `bailian-pilot/` | 百炼模型接入及初始真实调用 |
| `reviewer-probe/` | 复核器、反馈与评分一致性诊断 |
| `l22-completion/` | L2.2 BC 正式候选及历史门槛 |
| `feedback-v1/` | 作答与证据反馈候选 |
| `learning-loop/` | 真实作答→反馈→修改闭环与新课程尝试 |
| `field-support/` | 逐字段证据支持修复 |
| `method-scope/` | 方法范围约束及失败候选 X |
| `phase-completion/` | X 之后到最终 AU 的 Phase 完整收敛记录 |
| `model-management/` | 用户模型连接/路由机制验收 |
| `multi-user-phase-e/` | 最终求职增强实验：多用户并发、权限/产物/checkpoint 隔离及取消/恢复 |
| `tool-resilience-20261014/` | 有界读重试、拒绝与终止的机制测试及每类二十次本地故障基线对比 |
| `tool-resilience-latency-20261014/` | P0-1 连接开销 profiling、健康与故障串行对照及旧延迟口径更正 |
| `study-metrics-20261014/` | 只读执行指标命令、1,260 条持久记录的分队列报表及 PostgreSQL 验证 |
| `study-metrics-requests-20261014/` | 请求/执行工具分母修正、原指标不变核对与保留 Run 的 DB/JSONL 对照 |
| `retrieval-v2/` | 120 题/6 课程/18 讲次的冻结四路检索、课程保留集、配对置信区间与全部失败分桶 |
| `approval-recovery-20261014/` | 可选发布审批、523 个逐点 SIGKILL 与 54 次审批边界重复、持久预算/产物/checkpoint 不变量及浏览器证据 |

历史失败是评测证据的一部分，不因后续候选通过而删除或改判。阅读项目时优先从当前完成报告进入，再按需要追溯历史目录。

## 证据保留策略

主分支只保留最终报告、冻结身份、关键保留集结果和能够解释失败演进的少量机器可读证据，避免数百份中间 JSON 淹没代码 review。完整的公开评测快照固定在 Git tag `study-agent-au-evidence-2026-09-20`；原始 provider 请求/响应、凭据、媒体和数据库快照仍只保存在 Git 忽略的 `.data/`，不会进入公开仓库。

历史失败没有改判或删除：主分支的 Markdown 持续记录负责叙事，evidence tag 负责完整公开快照，私有 `.data` 负责原始回放。

- [发布审批与 SIGKILL 恢复矩阵](approval-recovery-20261014/README.md)：默认关闭的学习者审批、持久预算/调用日志与真实 PostgreSQL 子进程恢复；确定性执行验证，不是教学质量评分。

- [P8 Tutor](p8-tutor/README.md): 24 dialogues/80 turns across eight public lecture snapshots; deterministic multi-turn/Socratic/abstention mechanisms and separate Flash/Pro ledger channel. Offline only; real-model task quality NOT_RUN. Does not modify frozen P7/AU assets.
