# LectureLens Phase 1-E3 本地验收

候选 `bf266725c689792caeec84a20937dc8cda726b38` 的运行时 SHA-256 为 `993e7617b1a1a29e91546df028558429c802ec4d4f9778558223d8801ca60903`。E1/E2 基线为 `b7f55920d7b1773a1e890a93000eb7364bb1f621`，报告提交为 `3659ca672de7c39329a7375ea03ebffdfe68391e`。Phase 0 GitHub CI 仍为 **PENDING**。

```text
PHASE1_E3_EXECUTION = BLOCKED
RETRIEVAL_COVERAGE = PREFLIGHT_9_FULL_1_EXPECTED_GAP / LIVE_NOT_RUN
TEACHING_QUALITY = UNRESOLVED
REAL_GENERATION_REQUESTS = 0
AI_REVIEW_REQUESTS = 0
TOTAL_LOCAL_COST_USD = 0.00 settled / 0.00 outstanding
SUPPLIER_BILLING = UNKNOWN
NEXT_RECOMMENDATION = BLOCKED
HUMAN_REVIEW = HUMAN_NOT_RUN
expert_verified = false
```

受控进程缺少本轮显式密钥注入。真实启动门禁退出码为 `2`，拒绝发生在创建真实授权、阶段锚点和供应商请求之前。正式首次试验的 10 个位置全部为 `NOT_RUN`，其中历史暴露开发 3 个、新开发 3 个、保留 4 个。教学必要点、引用语义支持和完整回合通过情况均未观察。没有新真实失败可以支撑修复或开发集复测。

隔离 Java、MySQL、Python 和 PostgreSQL 预检核对了四个不同课程、原始证据、索引修订和原定顺序。9 个可答回合命中全部所需证据，Git 拒答回合符合预期证据缺口。历史失败归档、上游来源与冻结清单均通过哈希校验。

E3 的首次与可选开发集复测各有独立目标、授权及账本，共用同一 PostgreSQL 阶段门禁。阶段上限为 USD 10、首次最多 10 次生成、一次开发集复测最多 6 次生成。未知费用保留责任并阻断后续发送。数据库外的追加式发送标记可发现恢复旧快照所造成的账本差异。当前官方模型与价格仍符合冻结契约。供应商账单硬限未经验证。[DeepSeek 模型与定价](https://api-docs.deepseek.com/quick_start/pricing/) · [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)

本轮没有可用且能纳入累计费用门禁的独立付费评审。已补充 [AI 交叉评审规则](REVIEW.md)，真实回复可导出绑定答案与证据摘要的私有评审包。当前没有真实回复可送评。默认需要两份独立评审给出一致通过才推进下一题，分歧、低置信度和无评审保留未决。

## 验证与原始证据

以下路径均相对本工作树。监督器记录包含退出码及进程清理结果。

| 检查记录 | 退出码 | 结果 |
| --- | ---: | --- |
| `e3-key-required` | 2 | 预期拒绝，真实启动未进入资源准备 |
| `e3-python-regression` | 0 | 296 项 Python 回归，真实隔离 PostgreSQL |
| `e3-final-specific` | 0 | 最终候选 50 项 Flash/E3 测试、1 项评审包测试、Ruff、离线 wheel、冻结清单 |
| `e3-cross-offline` | 1 | 检索预检通过。运行中改动导致 worker 与初始化 schema 版本不一致，启动失败。 |
| `e3-cross-frozen` | 0 | 四课程跨服务检索、1 次离线 Mock HTTP、请求与响应哈希一致、资源清理 |

- 真实试验的 [10 个未观察位置](../../.data/phase1e3/live-observations.json)。
- 原始监督器证据位于 `.data/phase1e3/checks/`，跨服务证据位于 `.data/phase1e3/cross-frozen/`，首次失败保留在 `.data/phase1e3/cross-offline/`。
- [安全注入和执行说明](README.md)涵盖受控进程、授权期限和外部独立评审交接。
