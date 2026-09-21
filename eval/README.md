# LectureLens Evaluation Index

`eval/` 保存可公开的冻结任务、汇总报告和失败历史；原始 provider 请求/响应、凭据、媒体、数据库快照和大体积回放留在 Git 忽略的 `.data/`。

## 当前结论

当前最新的 Study Agent 有限范围候选是 **AU**。开发目标严格 31/31、全新保留目标严格 8/8，独立 PostgreSQL 机制测试 547 项通过，并完成真实浏览器学习闭环、恢复、取消、越权和删除验收。候选尚未发布，也不证明未见课程泛化、自动评分或长期记忆能力。

- 当前完成报告：[`phase-completion/FINAL_AU.md`](phase-completion/FINAL_AU.md)
- 完整持续记录：[`phase-completion/RESULTS.md`](phase-completion/RESULTS.md)
- 调用审计：[`phase-completion/AUDIT.json`](phase-completion/AUDIT.json)
- AU 开发逐题复核：[`phase-completion/AU-development-review.json`](phase-completion/AU-development-review.json)
- AU 全新保留复核：[`phase-completion/AU-holdout-review.json`](phase-completion/AU-holdout-review.json)

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

历史失败是评测证据的一部分，不因后续候选通过而删除或改判。阅读项目时优先从当前完成报告进入，再按需要追溯历史目录。
