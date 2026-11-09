# Phase 1-E3 首次真实失败修复

原始候选 `f73931ec1742c6a62446f0e9d5333cf4690a5aca`，运行 `441d4faab7f1`。初始 10 回合验收为 **FAIL**。`loop-1` 在开发集首位失败且未发布，教学质量未决。其余 9 个位置均为 `NOT_RUN`，包括 4 个 holdout 位置。

## ROOT_CAUSE

冻结候选要求 DeepSeek Flash 在 `choices[0].message.content` 内再生成一个 JSON 对象，将整段教学正文放进 `text` 字符串。实际请求包含 `response_format.type=json_object`、系统提示中的 JSON 示例、非流式、关闭 thinking 和 `max_tokens=4096`。按冻结代码重新构造的请求与原始请求逐字节一致。 [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)

HTTP 200 的完整外层响应可解析，`finish_reason=stop`，输出 734 tokens。内层字符串在零基字符偏移 552（第 1 行第 553 列）出现首个未转义 LF，冻结解析器返回 `TUTOR_FLASH_INVALID_JSON`。内容共 2,038 字符，包含 16 个 LF 和 337 个尾部 ASCII 空格。正文停在第三节标题，缺少该节所需代码和 JSON 闭合结构。即使允许字符串内的控制字符，解析仍因字符串未闭合而失败。DeepSeek 文档描述了 JSON Output 无法识别内容时可能返回空格，即使结束原因为 `stop`。原始记录能确认上游交付了无效的内层正文，无法区分生成和供应商格式处理各自造成的缺失。 [DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)

| 原始记录 | SHA-256 |
| --- | --- |
| HTTP 请求体 | `0e8563d93a6e491feb138bf7e00ce88bd0c51f3fa8a0b048388db24357bab77e` |
| HTTP 响应体 | `8604c54af79c65c90ed2a0fe02d1d563dc0cb24dbac09b488007c739775c9b86` |

## 修复

E3 `retest` 收据使用 Chat Completions 明确支持的 `response_format.type=text`。教学正文以原样文本传输，可包含 Markdown、代码、引号与换行。控制器按首行构造原有 `Reply`。`answered` 后是正文，`socratic_prompt` 后是焦点行及正文。发布层核对真实的 Socratic 模式、当前问题与追问共同包含的字面焦点，以及当前课程权威证据。单独一行 `insufficient_evidence` 映射为原有固定拒答，无引用；夹带正文或把固定拒答放进正向结果的输出会失败。答复超过 1,600 字符、缺少引用、引用超限或越权、正文截断及非法帧仍停止。两个正向状态必须由模型明确声明，实际教学正确性仍由独立评审判断。 [DeepSeek Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)

修复沿用一次生成、单次结算与失败停止。原始响应原样重放时，旧解析器报 `TUTOR_FLASH_INVALID_JSON`，新文本解析器报 `TUTOR_PROTOCOL_FAILURE`。初始候选与 E2 离线入口继续使用原 JSON wire。冻结题目、课程证据、答案参考、holdout 和私有原始结果均保留。

## 离线验收

**FIX_STATUS = PASS**。新候选的运行时构建摘要为 `7360e00f7d84dc116541b4ac8505c3817bdf8b853f0b084b54e97c713519509d`。

**OFFLINE_REGRESSION = PASS**。独立 PostgreSQL 的 E3、Tutor 和 CLI 相关回归共 258 项通过，无跳过。三门合成课程覆盖多行代码回答、字面焦点追问、固定拒答、错误模式或焦点、越权引用、空白、超长和截断。另有 1 项独立评审包测试通过，离线 wheel、Ruff 和冻结清单校验通过。

监督器保留了首次回归中因缺少历史归档环境变量而失败的两项结果。使用哈希匹配的原始归档后，这两项均在 258 项复跑中通过。全 Agent 套件在部分 MCP 测试出现失败后中止，未计入离线通过范围。

## 复测准入

**RETEST_ADMISSION = BLOCKED**。归档的原始收据、账本、live anchor 和外置 `initial-1` 标记相符。`loop-1` 属于开发集，已观察到一次可修复的协议失败，费用已结算且未发布。该错误符合 `approve_retest` 对可恢复失败的条件。独立 PostgreSQL 验证了协议失败后可关闭初始授权、同阶段绑定新收据、复用累计限额，以及重复审批被拒绝。

原运行的 PostgreSQL 与 MySQL 卷仍在，隔离运行已拆下。本轮仅核对原始导出的账本与文件标记，原库当前的审批状态仍待接入后核对。两个现有公开入口只准备首次运行。CLI 在已有 live anchor 时拒绝，独立 `preflight.py` 同样会尝试准备新阶段和首次收据。worker 已能接收复测收据，但仓库没有已验证的入口来重新接入这次保留的课程和数据库、复核账本与来源，并走认证网关完成有序复测。尚未对原阶段调用 `approve_retest`。

后续操作者需先在原保留栈恢复已验证的复测接入，核对同一阶段的 PG、MySQL、live anchor 和外置发送标记，以及原课程、owner、revision 和 Evidence 绑定。确认当前数据库状态、期限、模型和价格后，才可用原收据、`loop-1` 和本报告的 SHA-256 调用一次 `approve_retest`。为同一数据库的 `retest` 目标签发绑定新候选的短期收据，至少覆盖 `loop-1`，可扩展到最多 6 个有序开发前缀位置。已有 worker 使用原 anchor 和发送目录，经 Java 网关逐回合提交；首个失败或未获两份独立通过评审即停止。原首次启动命令会拒绝已消费阶段，保留原账本和标记。

阶段截止于 2026-11-12 23:59（Asia/Taipei），总上限 16 次、USD 10。当前已发送 **1** 次，结算 **USD 0.0013386**，未结算 **USD 0**。本次修复没有增加生成请求。开发复测结果单独记录，初始 **FAIL** 和未运行的 holdout 保持原状态。

## 审计

私有首次原始记录在 `.data/ll-eval/e3/441d4faab7f1/evidence/`。本轮重放的结构诊断、原始文件哈希和监督器终态在 `.data/e3-loop1-repair/`。离线结果衡量执行和协议机制，真实教学质量仍待复测。
