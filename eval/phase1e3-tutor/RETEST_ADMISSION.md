# E3 开发集复测准入核对

**RETEST_READY = NO**。运行 `441d4faab7f1` 的保留数据库可核对，但缺少通过 Java Tutor 网关所需的原课程所有者登录态。按本轮停止条件，开发到此结束。提交仅记录准入审计。

## 原阶段状态

原真实候选为 `f73931ec1742c6a62446f0e9d5333cf4690a5aca`，已验证的纯文本候选为 `db558ca790ca1f2da3e3905ff8d770e36f2c4568`。原修复报告 SHA-256 为 `7f14dfebb6b368da94ea056b4a61e5caa835b492c7bfb7920004cdb89be90ed4`。原始 Java JAR、冻结数据清单、Git 身份和原收据均通过核对。 [原修复报告](LOOP_1_REPAIR.md)

原 PostgreSQL 和 MySQL 卷仅以只读方式挂载给取证复制进程。查询在临时卷上进行，数据库容器禁用网络，事务为只读，核对完成后删除临时容器及临时卷。取证副本仅用于核对，无发送资格。

- PostgreSQL 的 phase ID、初始 target、收据摘要、十个位置的绑定、请求与响应摘要、未发布的失败回合、账本与原归档一致。唯一发送标记 `initial-1` 与账本请求摘要匹配。初始审批尚未关闭，复测 schema 和收据尚未创建。
- MySQL 的四门课程均属于原合成 owner，仍为 `SUCCEEDED`、未删除、revision 5。16 条 Evidence 的摘要、权威快照清单、原始 `loop-1` 所选正文和 PostgreSQL 的 `READY` 索引条目均匹配。
- 阶段账本累计 **1 次**，已结算 **USD 0.0013386**，未结算 **USD 0**。本轮新增真实请求为 **0**。原阶段上限为 **USD 10**、**16 次**，授权截止于 **2026-11-12 23:59（Asia/Taipei）**。DeepSeek 公示的 `deepseek-flash` 版本及峰值费率与收据匹配。 [DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)

## 停止依据

首次 runner 在内存中随机生成合成 owner 的密码，只取登录返回的 access token 用于当次运行。runner 已退出，留存运行工件未保存该密码或可用 token。保留库中的密码和 refresh token 存储为哈希。现有认证接口提供注册、登录和刷新，均无法在没有原 owner 凭据的情况下恢复其登录态。 [首次 runner](../../scripts/ci/mock-study-tutor-e2e.py) · [认证接口](../../backend/src/main/java/com/example/courselingo/auth/controller/AuthController.java)

Tutor 网关从认证会话得出 owner，并按该 owner 读取当前课程 revision。新建账号会得到另一 owner，原收据绑定因此无法复用。接线若依赖直接签发 owner token、改写账号或课程归属，便会越过现有认证或阶段绑定。恢复原 owner 的受支持认证路径是继续工作的先决条件。原阶段的审批尚未消费。 [Tutor 网关](../../backend/src/main/java/com/example/courselingo/study/TutorController.java)

## 离线验证与证据

| 检查 | 实际退出码 | 结果 |
| --- | ---: | --- |
| `volume-audit` | 0 | PG/MySQL、冻结课程和外置发送标记核对通过 |
| `e3-gates` | 0 | 独立 PostgreSQL 上 80 项通过，覆盖现有审批、重复审批拒绝、旧账本与标记不一致拒绝、累计费用与次数、失败停止、证据记录、SSH 隐藏输入和匿名管道 |
| `java-owner-gate` | 0 | 26 项 Java 认证与 Tutor 网关测试通过，覆盖缺少登录态、owner 归属和 revision 校验 |

真实保留栈的完整复测入口未交付。初始 10 回合验收仍为 **FAIL**，其余 9 回合均为 `NOT_RUN`。纯文本协议的真实模型表现和独立教学质量均待验证。

原始证据仍在 `.data/ll-eval/e3/441d4faab7f1/evidence/`，live anchor 与发送标记仍在 `.data/phase1e3/`。本轮卷核对与监督器终态在 `.data/e3-retest-admission/`。
