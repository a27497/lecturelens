# 独立验收的费用出口（实验工具）

仅用于冻结 Study Agent `7b60d94dc0a221217e595dfb5fe5205ba474d03a` 的隔离验收。普通应用、生产 worker 和 PR #36 不自动安装或启用本工具。本轮只验证 Fake Provider，真实执行需要另行明确授权。

## 当前实现与保证范围

`study/acceptance_cost.py` 在独立 PostgreSQL 上保存一个不可重置的费用 envelope、逐请求记录和拒绝事件。发送前锁住 singleton 行，校验原 Run/journal，再原子提交费用预留与幂等身份。唯一键为 `(run_id, operation_key)`；同一请求、并发代理、重启都不能再次付款。预留永不按低 usage 返还；取消、丢响应、超时和强杀也不返还。

`study/acceptance_egress.py` 是独立 loopback HTTP 出口。`AcceptanceProvider` 沿用原 `ChatProvider` 的协议、解析及质量契约，但只能访问本地出口。`worker_snapshot` 固定两个角色为官方 `deepseek-flash`，并强制 credential 为不可付款的公开占位符；不使用个人模型绑定或环境默认路由。唯一供应商密钥留在独立代理进程，经预先打开的私有文件描述符注入，不通过 worker、环境、命令行或响应传递。

代理只允许 `POST https://api.deepseek.com/chat/completions`，强制非思考、单输出、客户端函数工具；拒绝其他供应商/模型、图片、文件、stream、未知额外参数、服务端搜索工具及超过 65,536 UTF-8 请求体字节的输入。保留决策 900、出题复核最大 1200、反馈 900 的 `max_tokens`，并与当前 journal 的请求指纹和输出额度匹配。不开启重定向、环境代理、供应商探测或 HTTP 重试。发生协议/质量拒绝或重试事件后，不允许后续付费修复请求。

费用预留、调用记录、当前 Run 和取消状态在发送前再次核验。只能消费一个出题 Run 及其已保存作答所对应的一个反馈 Run；每 Run 最多 6 次，总最多 12 次。原 64,000 token/字节保守预留、8 次工具、deadline、Java 权属与 Evidence 版本检查、checkpoint 和持久化仍由未修改的运行时负责，费用出口不替代它们。

## 20 CNY 计算与成立条件

2026-10-20 核对的[官方人民币价格](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)：Flash 高峰输入未命中 2 CNY/百万 token、输出 8 CNY/百万 token；缓存和闲时折扣不用于减少预留。[Chat Completions 文档](https://api-docs.deepseek.com/api/create-chat-completion/)说明输入与生成总长度受上下文长度限制。

不把 UTF-8 字节数称为 tokenizer 的严格上界。对每次请求，按整个 1M 上下文向上取 `1,048,576` 输入 tokens 预留，涵盖消息、函数 Schema 和模板开销；另加该次 `max_tokens` 的输出费用。这故意重复覆盖部分上下文，避免依赖尚未核实的本地 tokenizer/模板。

```text
R = 1,048,576 × 2 / 1,000,000 + max_tokens × 8 / 1,000,000 CNY
max_tokens=900  → 2.104352 CNY
max_tokens=1200 → 2.106752 CNY
原子准入条件：累计 R + 下一次 R ≤ 20 CNY
```

内部使用整数 micro-CNY（百万分之一元），不使用浮点金额。即使保留 12 次次数上限，也不能保证全数获准：未经货币拦截的 6 次出题 + 6 次反馈上界为 25.266624 CNY。因此当前策略**最多放行 9 次**，第 10 次连最低预留都不足。九次请求一般上界 18.960768 CNY；确定性健康链路实际预留 18.941568 CNY。没有通过返还或降低复核质量腾出第十次额度。

此为通过该出口的请求，在以下条件下的本地费用上界：供应商遵守已核实的模型、上下文、输出限制及该价格，没有额外收费项目；所有本次验收请求都经过同一持久 envelope；数据库不丢失/回滚费用记录。价格确认窗口最长 24 小时，失效即拒绝。它不能锁住供应商未来改价或阻止供应商错误计费。实际响应超过 token 上界、model 不符或 usage 不可靠时，保存已知 usage 并停止，不能追回已经发生的供应商计费。

## 未知结果、账单与隔离

`reserved_micro_cny` 是不返还的本地上界。`provider_usage` 独立保存供应商报告的安全整数统计；`usage_peak_upper_micro_cny` 只是按高峰未命中价对 usage 的上界换算。`provider_billed_micro_cny` 在本实现中保持 NULL，没有账单证明时不填“实际费用”。Fake usage 也不是账单。

费用状态 `reserved`/`sent` 是未决，`unknown` 是响应或计费依据不可靠，均阻止后续发送。HTTP 错误、缺失 usage、超界或模型不符将持久阻断整个 envelope。只有 `observed` 表示收到可用 token 统计，不表示账户账单已经对账。强杀后不自动重发，也不通过新请求键或新 envelope 掩盖未知结果。

本轮没有供应商密钥、独立账户身份、充值/赠送余额或账户级硬限的证据；没有调用账户 API。**账户级 20 CNY 硬限未核验、未配置。** 当前费用表、Fake Provider 和独立 PG 只落实请求级机制。真实执行前还需确认专用凭据/账户状态、代理与 worker 的操作系统权限/出口隔离、持久磁盘及数据库 fsync，并复核价格和候选指纹。其他进程持有相同账户的凭据、供应商后台扣款、改价、数据库丢失或绕过本代理的流量不在本地机制保证内。

## 离线检查与后续接入

只读命令，不创建 Run、不读凭据、不发模型请求：

```bash
agent-service/.venv/bin/python scripts/eval/acceptance-cost-egress.py plan
```

可用 `plan --routes <隔离快照.json>` 核验待执行配置；只输出公开路由字段。启动与安装均比对原候选 54 个 Python 模块的 SHA256；任何源文件漂移即拒绝。费用模块自身还必须匹配当次冻结的新组合制品 SHA。

未来获得 P0-3 明确授权后，独立执行器才能使用 `serve`，提供包含授权记录、Session ID、价格确认/失效时间的 `mode=live` 不可变 policy，以及专用 credential FD。脚本不获取余额、不探测模型、不自动出题或反馈。endpoint 文件以 O_EXCL/0600 创建，只含本地 URL 与独立本地 capability，属于私有文件，不得打印或入 Git。worker 用该文件初始化 `AcceptanceProvider`，用 `worker_snapshot` 初始化独立 `StudyStore`；不能调用生产 loader、连接生产数据库或启动普通消费生产队列的 worker。

数据库仅允许 loopback 的 20000–32767 端口，库名为 `lecturelens_agent_test` 或 `lecturelens_agent_acceptance`。拒绝非 loopback `hostaddr` 和 service 引用，显式固定 libpq 的 `hostaddr=127.0.0.1`，防止 `PGHOSTADDR` 覆盖。连接强制 `synchronous_commit=on`，安装要求 `fsync=on`。测试库可用临时存储；真实费用库必须使用持久磁盘，并禁止从付款前的快照回滚后继续发送。singleton 的 policy 不允许修改、重新充值或自动解封。过期/未知/取消后需要停止和人工审阅，不能清空表继续试跑。

本工具未改变任何生产路由或服务，不需要执行生产回退。后续隔离验收要回退时，停止验收 worker 和对应代理，撤销专用凭据，保留费用表、失败 Run、journal、作答和产物；恢复原冻结运行时不等于获准绕过费用出口继续调用。
