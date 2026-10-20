# P0-3A：20 CNY 费用出口与离线验收

2026-10-20。只验证隔离请求出口的执行机制。真实付费模型请求 **0**，没有账户 API 探测、生产数据库访问、生产服务/模型配置修改、部署或合并。没有使用原失败 Run `631c3d65-9787-4393-aeb4-8632ccdd9d9d`，也没有改写历史失败。

## 身份与实现

- 原冻结 Agent：`7b60d94dc0a221217e595dfb5fe5205ba474d03a`。
- 初始费用实现提交：`576a2b2558bf426c2975fd323ce651f924d94086`。
- **本次最终组合候选：`c7c5d3ddc1f0c4137c642f6b6ef20c7811a302d8`**，本地独立分支 `codex/study-deepseek-cost-cap`。初始版本后补充了只读测试样本权限修正、libpq 目标地址固定（`e2972d4`）及 Docker 转发地址断言修正；费用规则和原 Agent 不变。
- 原 54 个 Python 模块、依赖声明及 lock 均保持原样，详见 [身份对照](identity-proof.json)。新增费用表只通过隔离工具显式安装，不加入普通应用迁移或启动过程。
- 从该 SHA 导出独立制品，离线 frozen/non-editable 安装，核验已安装包的原模块摘要，再对只读导出源码运行测试；源码包、测试辅助包和新增费用模块摘要见 [candidate.json](candidate.json)。

实现位置：`agent-service/src/lecturelens_agent/study/acceptance_cost.py` 保存原子金额预留和拒绝，`acceptance_egress.py` 提供独立本地出口与受限 Provider，`scripts/eval/acceptance-cost-egress.py` 提供只读 plan 和需另行授权的 serve。当前行为、接入条件和成本范围见 [费用出口说明](../../docs/ACCEPTANCE_COST_EGRESS.md)。没有把普通 worker 改成付费验收 worker。

## 路由与费用边界

隔离 worker 的**实际冻结快照**由 `worker_snapshot` 创建，两个角色均为 `deepseek-flash`；禁止服务器默认回退、个人绑定、Pro 和未知模型。快照强制使用不可付款的公开占位符，真正供应商密钥只能进入独立代理。P0-2 旧夹具使用 Pro 复核的事实保留，不能把它直接当成本次路由。

| 检查项 | 本次隔离请求的约束 |
| --- | --- |
| 官方上游 | `POST https://api.deepseek.com/chat/completions`，无其他路径/域名 |
| 决策 / 复核模型 | 均为 `deepseek-flash`，出站强制 `thinking.type=disabled` |
| 输出 | 决策 900、出题复核至多 1200、反馈 900；必须匹配已有 journal |
| 输入 | 完整出站 UTF-8 JSON ≤65,536 字节；纯文本与客户端函数工具 |
| 次数 | 单 Run ≤6，总 ≤12；一个出题 Run 及其一次作答对应的一个反馈 Run |
| 金额 | 整数 micro-CNY 原子准入，总预留 ≤20,000,000，即 20 CNY |
| 未知 / 重复 / 重试 | 不返还、不重发；未知阻断后续，协议/质量拒绝后不付费修复 |

已联网读取[官方价格页](https://api-docs.deepseek.com/zh-cn/quick_start/pricing/)和[请求契约](https://api-docs.deepseek.com/api/create-chat-completion/)，没有调用模型。当前 Flash 高峰输入未命中 2、输出 8 CNY/百万 token；上下文标为 1M，输入与生成之和受上下文限制。核对记录见 [pricing-verification.json](pricing-verification.json)。没有读取生产个人路由或凭据；这里只确认隔离候选的路由。

按完整上下文向上取 1,048,576 输入 tokens，独立增加该次输出上限，忽略缓存和闲时折扣：

```text
R = 1,048,576 × 2 / 1,000,000 + max_tokens × 8 / 1,000,000 CNY
900 输出 → 2.104352 CNY；1200 输出 → 2.106752 CNY
仅当累计 R + 下一次 R ≤20 时，才提交预留并允许发送。
```

这不依赖 UTF-8 字节与 tokenizer 的经验换算。12 次全部放行的资源上界为 25.266624 CNY，超过拟批准金额，因此**当前策略实际最多放行九次**；第十次最低输入预留已不足。九次的一般上界为 18.960768 CNY。严格九次夹具恰好可完成，不保证真实模型也只需九次；费用不足时应保留失败并停止。

成立条件是供应商遵守核实的价格与上下文/输出契约、没有额外计费项目，本次所有请求经过同一持久 envelope 且记录没有丢失/回滚。价格确认最多有效 24 小时，到期拒绝。本机制不能锁住供应商改价、纠正误计费或约束同账户其他进程；不能据此宣称账户级总账单被锁在 20 CNY。

## 确定性结果与账单口径

通过真实 loopback HTTP、原 `ChatProvider` 解析、原 LangGraph/质量校验和独立 PostgreSQL，供应商端完全使用 Fake Provider。正常流程和提交前 checkpoint 中断恢复均得到：

| 阶段 | 原 Run 预留 | 模型 / 工具 | 本地金额预留 | 产物 |
| --- | ---: | ---: | ---: | --- |
| 两次检索重叠五条、补读、解释与两题、必要复核 | 61,790 /64,000 | 5 /4 | 10.524160 CNY | 成功保存解释及两题 |
| 保存具体作答、课程依据、独立反馈复核 | 28,524 /64,000 | 4 /2 | 8.417408 CNY | 成功保存，绑定精确 attempt_id |
| 合计 | 两个独立 Run | 9 /6 | **18.941568 CNY** | 重启 Store 后可读取 |

Fake usage 的高峰未命中上界换算为 0.005400 CNY，**不是实际账单**；本地 18.941568 是不返还的预留，也不是账单。`provider_usage`、本地预留和 `usage_peak_upper_micro_cny` 分开存储；没有供应商账单凭据时 `provider_billed_micro_cny` 始终 NULL。真实付费请求为零。

专项覆盖正常放行、金额精确边界/不足、输入超限与禁止参数、路由与角色、54 模块身份漂移、不可付款的 worker 快照、只读 plan/拒绝假授权启动、重复请求、16 路并发抢占、取消、显式调用上限、未知结果、无重定向/HTTP 重试、另一 journal 不能绕过未决记录，以及三种真实 SIGKILL 恢复点。新增地址反向检查拒绝非本机 hostaddr/service，并在注入 PGHOSTADDR 时核验 libpq 仍实际连接 loopback 的测试库。另通过费用出口验证原取消、质量拒绝、伪造引用、Evidence 版本变化及 64,000 预算终态不发布产物。

最终只读冻结制品的专项结果为 **54 passed、0 failed、0 skipped**，22.95 秒；包含原 51 项与新增 3 项 libpq 地址检查。完整 Python 与独立 PostgreSQL 回归为 **847 passed、0 failed、0 skipped**，188.71 秒；有一条已有 Starlette/AnyIO 弃用警告。最终结果、命令、网络计数和 supervisor 终态见 [verification.json](verification.json)。专项属于完整集合的子集，不重复累计。所有长测试由既有 `scripts/dev/run_check.py` 管理；出网保护只允许独立测试 PG 和本地测试端口。

保留了初次冻结 `576a2b2` 的失败诊断：篡改测试复制只读文件后，临时副本也只读，写样本时报 PermissionError。该轮全量被按 PID/start ticks 定位取消，独立诊断明确 FAILED；最终 `41565cf` 仅给临时样本增加写权限，原冻结源码仍只读。见 [失败记录](prior-frozen-diagnosis-output.txt)。另一次地址断言误把 Docker 容器侧地址当成客户端目标；53 项通过、1 项失败，记录在 [地址诊断](prior-address-assertion-output.txt)。最终断言改查 libpq 的客户端目标和独立库名。地址固定前 `41565cf` 的 844 项全量通过记录也独立保留；它不冒充最终身份的结果。没有把旧失败标成成功。

## 隔离、风险与回退

- 最终测试使用本轮新建的 `lecturelens-p0-3a-final-pg-20261020`，loopback 25479、独立 `lecturelens_agent_test`、PostgreSQL 17.11/pgvector；fsync 与同步提交开启。测试使用 tmpfs，验证代理/worker 强杀后的 PG 持久记录，不宣称验证了宿主机掉电恢复。真实金额库必须用持久磁盘，禁止恢复旧金额快照后续付费。
- 本轮账户隔离状态为**未核验**，没有供应商密钥、账户余额、充值或账户级硬限的证据，也没有账户 API 查询。独立进程接口、无云凭据的 worker 快照和持久费用出口已实现；专用真实账户/凭据、操作系统权限与出口隔离尚未配置/验收。少数单测用合成 live policy 加 MockTransport 覆盖真实发送分支，并不构成用户授权或账户设置。
- 本地费用表只记录安全统计、指纹和错误码，不保存模型输入；已有运行时的私有 trace 契约不变。冻结 `ChatProvider` 将代理 HTTP 拒绝映射为通用 Provider 错误（例如本地 403 对应 `MODEL_AUTH_FAILED`）；具体费用拒绝原因以独立 `acceptance_cost_event`/envelope 为准，不能把该公开映射当成供应商鉴权实测。
- Python socket 保护不是 OS 网络沙箱；native libpq 使用明确校验的独立 DSN。正式验收还需限制 worker 只能访问隔离 Java/PG/本地代理，只有代理能访问官方模型出口，且只有代理持有专用凭据。无任何机制能阻止掌握宿主机/数据库管理权限的人重置本地账本；真实执行应限制 worker 的数据库权限并保留账本。
- 没有真实 DeepSeek 教学质量、延迟、usage 或账单验收；Flash 复核不继承 P0-2 Pro 的质量结论，P0-2 本身也只是确定性机制证据。本轮没有启动 Java/浏览器，不冒充真实权属全链路验收。
- 当前无需生产回退。后续隔离试验如失败，停止对应 worker/代理，按授权撤销专用凭据，保留费用表和所有 Run/作答/产物。不要清空账本、新建 request_key 自动重跑，或恢复原 Agent 后绕过代理继续付款。生产 PR/部署保持原状态。

**STOP。费用机制通过不等于最终执行授权。未经用户审阅并另行批准 P0-3，不得启动真实模型或自动进入出题、反馈与部署。**
