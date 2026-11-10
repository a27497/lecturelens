# LectureLens Phase 1-E 本地验收

候选实现为 `b7f55920d7b1773a1e890a93000eb7364bb1f621`，从 Phase 1-D `8ac7933b39dc03ec996e7e9ac61ad1d4e4d8e6d3` 建立。冻结标识见 [CANDIDATE.json](CANDIDATE.json)。Phase 0 集成基线为 `17d78636cf97fcf55fe642b1ecc30c5e2ea48865`，GitHub CI **PENDING**。

```text
PHASE1_E1_STATUS = PASS
PHASE1_E2_STATUS = PASS
OFFLINE_REGRESSION = PASS
REAL_PROVIDER_REQUESTS = 0
REAL_MODEL_QUALITY = NOT_RUN
E3_READINESS = READY
```

## E1 教学评测准备

- [冻结集](dataset.json)覆盖 4 门课程材料、4 个对话、10 个回合。原 v19 的 2 个教学失败与 1 个未发布回合保留为已暴露开发回归。SQLite 是新增开发材料，Shell 与 Git 共 4 回合作为本候选保留材料。保留集作者可见，课程为公开材料。
- 核验了三份上游源码、课内片段行号、历史归档及成员 SHA-256，并实际执行了 SQLite、Shell、Git 和 Python 参考。冻结 SHA-256 见 [SHA256SUMS](SHA256SUMS)。
- 隔离 Java 权威、真实 PostgreSQL/pgvector 和本地 embedding 检索预检为 **9 FULL、1 EXPECTED_GAP**。仅适用于冻结的小课程包。SQL 负控分别覆盖正确证据已传达但引用不支持解释、以及所需证据未命中两种情形。教学评分采用 [独立评分规则](RUBRIC.md)，本轮未评分。

## E2 Provider、费用与安全停止

- 独立实验入口接入 `deepseek-flash` 非思考 JSON 生成。一次生成、六轮会话、Java 授权与引用复核仍走同一条 Tutor 链路。普通入口只接收 Mock 配置。
- 授权绑定 PostgreSQL 目标标识、候选、任务、证据、有效期、模型/价格和美元预算。运行大小预留与费用预留在发送前同事务落盘。用实际 usage 按冻结峰值费率结算。未知费用保留全额预留并阻断后续发送，重复请求和进程恢复不会重发已预留位置。取消、版本和删除条件仍在发布前生效。
- 完整链路从 Java 鉴权和签名请求到 Python、离线 HTTP、PG 账本与 Java 证据回读。合成请求 1 次，保存 150 Token、319,488,000 nanoUSD 预留、84,120 nanoUSD 模拟结算，账本请求哈希与实际离线 HTTP 内容一致。真实费用为 USD 0。跨账号、未批准会话、未签名请求均被拒绝。
- 负向验证涵盖空白、截断、坏 JSON、429/503、重定向、超时、响应大小、异常 usage、预算和授权失效、请求竞争、未知发送、恢复、取消后晚到结算、来源版本/文本变化和删除。普通 Mock 另经 Chromium 验收。

## 验证记录

原始日志保留在本工作树的 `.data/phase1e/checks/<记录名>/`，包括 `run.json` 与 `output.log`。完整链路报告、检索与浏览器证据位于 `.data/phase1e/cross-b/`。

| 记录 | 退出码 | 验证 |
| --- | ---: | --- |
| `phase1e-freeze` | 0 | 冻结哈希、上游与 v19 原件校验、固定参考、Ruff |
| `phase1e-frozen-flash` | 0 | 39 项 Flash 测试、离线 Python wheel、Ruff、冻结清单 |
| `phase1e-current-regression` | 0 | 287 项当前 Tutor、引用与供应商适配回归，隔离 PostgreSQL |
| `phase1e-java-package` | 0 | 19 项 Java 网关和权威测试，Maven 离线打包 |
| `phase1e-frontend` | 0 | 338 项 Vue 单测、类型检查与构建 |
| `phase1e-cross-b` | 0 | Java/Python/PG 离线链路、Chromium、冻结集检索与资源清理 |
| `phase1e-cross-a` | 1 | Chromium 临时目录使 Unix socket 路径过长。短路径重跑通过。 |
| `phase1e-python-final` / `phase1e-inherited-p8-gate` | 1 / 1 | 额外运行的旧 P8 冻结评测因哈希不匹配拒绝。原 Phase 1-D 已有相同拒绝，旧门禁与证据继续保留。 |

当前离线回归结果覆盖本轮 Tutor 与接线范围。Java 真实模型出口通过配置关闭，Python 集成包含 loopback socket 审计，Mock HTTP 通过进程内 transport 截获。供应商的实际可用性、计量及教学价值均待 E3。

## E3 交接

[E3 方案](E3.md)建议使用同一冻结候选和 10 个回合，单并发、最多 10 个请求、4,096 completion tokens、本地 USD 0.55。单请求按当前文档峰值费率的保守预留为 USD 0.319488，10 个最大请求的保守总暴露为 USD 3.19488。供应商硬限未经验证。真实准入需要重新核对官方模型和价格、在目标隔离环境重跑检索预检、取得新授权和用户安全注入密钥。本轮只创建了隔离数据库上的离线测试收据。
