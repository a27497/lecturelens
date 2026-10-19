# 发布审批与 PostgreSQL 强杀恢复矩阵

本目录新增未发布能力的执行验证。默认不启用审批，不改变线上配置，不 push 或部署。P0-1、P0-2、P1-1 原始记录及冻结资产保持原样。机制验证使用确定性 MockProvider、合成课程及学习者作答，不评估真实模型的教学质量。

## 实现与权限

启动练习或反馈时可选 `approval_required=true`。经复核的草稿保存到审批表，独立 LangGraph 节点 interrupt 后等待；批准、人工修改后批准、拒绝的决定与重新入队同一事务持久化，恢复后再检查 Java 的课程权属、版本、删除状态以及取消/预算/worker token。拒绝进入 `failed / APPROVAL_REJECTED`，不创建已发布产物。等待时暂停执行时限，保留原有调用/token 预算与未完成读取尝试计数。

当前审批者是经过 Java 认证与课程所有权校验的课程所有者。仓库没有跨账号管理员角色，未增加代审权限。编辑限于练习发布说明或单独标明的人工反馈建议；答案、题目和 Evidence 引用不能由此接口替换。人工编辑不是模型复核的新金标准。[接口与恢复语义](../../docs/STUDY_APPROVAL_RECOVERY.md)。

模型调用日志和预算在 PostgreSQL 原子预留，观察与完成事件原子提交；稳定的节点调用位置键不含可变的提示预算。节点重放复用已提交观察；预留已提交、响应未落库的模型调用进入 `MODEL_OUTCOME_UNKNOWN`，不重发。逻辑工具预算以 call_id 预留；新的只读物理重试照常消耗持久预算。没有远端幂等协议时，无法保证所有 RPC 窗口都自动恢复成功。

## 开发失败保留

- `browser-development-failure.json`：首次浏览器刷新没有恢复 Run 的审批选项，后续反馈误用默认关闭。已修复并新增前端回归测试。
- `matrix-first/raw.jsonl` 和原 `summary.json` 保留。初版检查只核对预算数与日志数，无法发现两者同时重复。`AUDIT_v2.json` / `audit-v2.jsonl` 对原记录复核，发现 **69 个成功终态消耗了 5 次模型调用，健康对照为 4 次**。原因是提示中剩余预算改变了原重放键；反馈还存在由预算改变工具列表的问题。旧汇总中的“通过”不作为最终验收证据。
- 修复为稳定调用位置键、独立输入/schema 指纹，以及恢复时使用该节点预留前的规划预算。新增预算变化、协议修复、输入变更及反馈工具列表边界测试。
- `harness-interruption.json`：聊天工具中断导致一个额外工作进程停止。恢复已超过原持久 deadline，正确进入预算耗尽；单列保留，不计入计划 SIGKILL 注入的样本数。

## 最终运行

最终 **577/577 次计划注入通过不变量检查**：主矩阵 523 个位置各一次；审批 18 个位置各三次。主矩阵为 420 个发布成功、96 个 `MODEL_OUTCOME_UNKNOWN` 保守失败、1 个读取上限失败、2 个取消、4 个删除清理。审批重复样本为 36 个发布成功、18 个明确拒绝，拒绝无产物。没有观察到重复模型请求、重复逻辑预算扣除、重复发布或事件序列不连续。模型结果不明的失败不是恢复成功。

| 批次 | N | 检查通过 | 恢复 P50 ms | 恢复 P95 ms |
|---|---:|---:|---:|---:|
| 逐点主矩阵 | 523 | 523 | 1658.319 | 2641.105 |
| 审批边界重复采样 | 54 | 54 | 1140.497 | 1214.510 |

每个位置的样本量、通过数、耗时见 [完整矩阵表](MATRIX.md)，全部数字来自 [主矩阵原始记录](matrix-final/raw.jsonl)、[审批原始记录](approval-decisions/raw.jsonl) 和 [机器汇总](RESULTS.json)。恢复时新的只读物理尝试仍会扣预算；“不重复扣除”指同一逻辑模型/工具调用没有再次扣除，不表示所有外部只读请求都只发一次。主矩阵调用日志缺失窗口选择明确失败；模型观测已经落库的节点可以重放成功。
- `matrix-final/`：两个普通节点、两个反馈节点、审批等待/发布、模型/Java桩读取前后、预算/结果日志、checkpoint put/put_writes、终态及取消/删除清理。
- `approval-decisions/`：练习和反馈 × 批准/修改/拒绝 × 等待/决定已提交/发布或拒绝终态已提交，各点重复三次。
- `controls.jsonl` 是每条轨迹实际运行的健康对照；工具、模型预算不能只与自己的日志相等，还须与对照调用槽数量一致。模型 RPC 记录用稳定调用槽键检查重复。
- `identities.jsonl` 冻结 Python/runtime/确定性夹具/驱动身份，每个新 worker 检查源码 SHA；运行中源码变更会拒绝执行。

恢复耗时是重新启动 Python worker、重连 PostgreSQL、读取 checkpoint 至恢复完成的实际墙钟时间；不包含人为审批等待。全矩阵每个位置一个样本，P50/P95 相同，不提供统计可靠性或生产延迟置信区间。审批边界每个位置三个样本，P95 为三次最大值。

## 复现

只允许独立 PostgreSQL 实例上的 `lecturelens_agent_test`。目录必须不存在；中断批次可用 `--resume` 追加，已有原始记录不覆盖。

```bash
export AGENT_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:PORT/lecturelens_agent_test'
agent-service/.venv/bin/python scripts/eval/check-study-crash-matrix.py \
  --trials 1 --output eval/approval-recovery-NEW/matrix
agent-service/.venv/bin/python scripts/eval/check-study-approval-recovery.py \
  --trials 3 --output eval/approval-recovery-NEW/approval
```

串行运行测量，之后再运行全量 pytest。真实浏览器使用本地隔离 Java、MySQL、Agent、PostgreSQL、Vue 和 Chrome，HTTP 无 mock；合成 Evidence 从 Java 实際索引到 Agent。媒体上传/处理没有在本次重跑，示例媒体对象不用于审批验证。

## 验证

- 全量 Python **727 passed / 0 failed / 0 errors / 0 skipped**，分为四组独立 PostgreSQL 容器，完整 collection 的 727 个 case 覆盖一次；[JUnit 与校验](tests/verification.json)。新增审批/恢复测试 23 项。
- ruff check 与 format check 通过；相关 Java 12 项（权属/版本与网关审批 DTO）0 失败/跳过；前端 99 项全部通过，type-check 和 build 通过。构建仍有现有依赖 PURE 注释与 chunk-size 警告，不作为性能验收。
- 真实 Chrome **7/7 审批检查**通过：[主审批/等待强杀/越权](browser-final.json)、[反馈修改与拒绝](browser-feedback-final.json)。本地隔离 Java/MySQL/Agent/PostgreSQL/Vue，HTTP 无 mock，模型确定性。等待时 SIGKILL 后刷新仍可审批；另一认证账号审批被 Java 返回 404。
- 真实 Java 删除 **1/1**：Agent 在等待中强杀，Java 删除课程后 READ 和晚到批准立即 404；重启后 7,296.182 ms 内收到真实删除同步，Run/草稿/调用日志/预算预留及三类 checkpoint 表全部清零，[原始删除结果](deletion-final.json)。该数字是一个样本，不声明删除延迟 SLA。
- 最终主矩阵、审批重复、浏览器验证和全量 pytest 按顺序运行。测试未与恢复耗时采集并行。初版矩阵和聊天中断记录单列，未混入最终延迟。

## 边界

不声明真实模型质量、真实付费模型/发布服务的远端 exactly-once、数据库主机断电/磁盘损坏/主备切换、所有计算工具及语义修订分支的强杀覆盖，或跨账号管理员代审。历史无完整调用观察的模型 Run 采取保守失败；没有独立 token 明细的旧预留不能从日志估算。升级前在旧 `reserve` 与 `tool_started` 之间停止的历史 Run 未作强杀迁移验证；新运行的预留与幂等键同事务写入。


| 尚未覆盖的故障/能力 | 状态 |
|---|---|
| 真实付费模型 HTTP 调用中强杀及远端幂等协议 | 未运行；强杀矩阵使用确定性 provider |
| 真实 Java HTTP 读取进行中强杀 | 未运行；矩阵读取是本地桩，浏览器的 Java HTTP 和等待/删除重启是真实的 |
| PostgreSQL 进程强杀、主机断电、磁盘损坏、主备切换 | 未运行；本次强杀 Agent worker，数据库持续运行 |
| 所有计算工具、语义修订和反馈补读分支的逐点 SIGKILL | 未运行全覆盖；预算敏感的反馈补读恢复已用 PostgreSQL 单元测试覆盖 |
| 升级前没有 tool_started 的旧逻辑工具预留迁移窗口 | 未运行；已有 tool_started 的旧预留已验证导入 |
| 跨账号管理员代审 | 未实现；无现有授权规则 |

## 验收证据补充（2026-10-15，仅追加）

主矩阵 **523 次 = 523 个不同的 `(轨迹, 注入位置)` 各 1 次**，不是同一位置重复多次；审批边界 **54 次 = 18 个组合各 3 次**。577/577 表示不变量检查通过，含 96 个 `MODEL_OUTCOME_UNKNOWN` 保守失败，不表示 577 次发布成功。全量和审批两批的样本量及分位数均未调整。

特殊行 `retry_cap / SEARCH:three_crashes` 的一次场景在**同一 Run 强杀 3 次**。复算读取 `checks.three_injections`，不要求该行存在 `injection_reached`。冻结矩阵驱动实际比较三个返回码 `codes == [-signal.SIGKILL] * 3`，确认三次都是 SIGKILL；第四次恢复达到 `READ_CHECKPOINT_REPLAY`，没有重置持久尝试上限。该行仍为 N=1，其耗时只计第四个 worker 的恢复；不能把三次强杀当作三个独立样本。

此前已保存的最终 Chrome 截图现按原字节复制到 `browser-evidence/`，没有补拍或图像编辑：[练习批准](browser-evidence/final-approve.png)、[练习修改后批准](browser-evidence/final-edit.png)、[练习拒绝](browser-evidence/final-reject.png)、[反馈批准](browser-evidence/final-feedback.png)、[反馈修改后批准](browser-evidence/final-feedback-edit.png)、[反馈拒绝](browser-evidence/final-feedback-reject.png)。[来源与 SHA-256](browser-evidence/manifest.json)记录原文件、原修改时间与复制文件哈希。截图是终态画面；**等待中强杀/越权检查无截图，未保存 Playwright trace**，这部分证据仍为原 JSON。截图中的媒体请求错误属于原合成媒体夹具，不代表上传或播放验收。

审批评测依赖矩阵评测初始化的 Agent/checkpoint schema。旧脚本还依赖矩阵先建 `eval_remote_call`；本次仅调整评测脚本，使已初始化的测试库缺少该审计表时自动创建，缺少基础 schema 时明确报错并提示先跑矩阵。运行时代码未改变，旧版本源码哈希与全部结果保留。完整顺序见 [REPRODUCE](REPRODUCE.md)，数字出处与实际复算输出见 [VERIFY](VERIFY.md)。

本次补充验证：独立临时 PostgreSQL 上审批测试 **23 passed / 0 skipped**，Ruff check/format check 通过；审批缺审计表路径 **18/18**（等待强杀 **6/6**），矩阵 smoke **30/30**，空基础 schema 明确拒绝启动。新原始记录在 `documentation-check-20261015/`，不并入旧 577 次或旧恢复分位数。本次没有重跑全量 Python、Java、前端或浏览器；旧测试数字从保存结果复算。71 个已有结果文件哈希未变，README/MATRIX 原字节保持为未改动前缀，见 [保留校验](documentation-check-20261015/preserved-results.json)。
