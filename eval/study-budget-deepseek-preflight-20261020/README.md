# P0-2：PR #36 与现有 DeepSeek 适配兼容性预检

2026-10-20。结论限定为代码、依赖、配置接口和确定性执行机制；没有真实供应商调用、生产数据库访问、生产服务/模型配置修改或部署。原失败 Run `631c3d65-9787-4393-aeb4-8632ccdd9d9d` 及旧评测记录保持原样。

## 精确候选

- PR #36：`bf90b28d2fb069744c37d90de68f747b6d176d44`，原分支保持不变。只读核验四种 CI Job 均 SUCCESS；这些是 PR 原身份的结果，不替代本组合的测试。
- 声明的线上基线：`bc2e6cc79f1a3311b90cc4d407f75d2e20048275`。
- **独立组合候选：`7b60d94dc0a221217e595dfb5fe5205ba474d03a`**，本地分支 `codex/study-budget-deepseek-preflight`。
- 当前线上 `provider.py` SHA256：`3b70650ec0fbd2423683b2b976a017eb9e2940a31a604776cf21f9f0602172c8`；与原工作区未提交适配逐字节相同。
- 组合后 `provider.py` SHA256：`d3ab712d178b8c8e5fdc25f9c253fefbe26fc785b3ee7bf0415e315d01d6f45d`。
- 源码包 SHA256：`1a627ffebb05fdf0a0e89e0886115d6d2e4c3c3bc259d40734f9bbc46a10ee39`；完整测试辅助包 SHA256：`f244ca7a3a504d0ff095f98fc5ef3ce76ad45eb26a8435087b191a4a692c079c`。本地位置见 [候选清单](candidate.json)。包从上述 Git SHA 导出，不包含生产 loader、密钥或配置文件。

在新工作树完成组合。冻结包另行解包，使用与线上同一 Python 3.12.14 可执行文件、`uv sync --frozen --offline --no-editable --python 3.12 --link-mode copy` 安装；非 editable 包的 provider 摘要也匹配。正式全量检查在该导出目录运行，源码与检查脚本设为只读，未用开发工作区替代冻结源码。

## 组合差异与兼容性证据

线上源码相对 `bc2e6cc` 只有 `study/provider.py` 的独立适配：增加官方域名/路径及两个模型 ID 的 `deepseek_nonthinking()` 判断，并在请求中发送 `thinking: {type: disabled}`。只读源码核验未发现其余 Python 模块漂移。

PR 与线上基线的 Agent 差异只涉及 `runtime.py`、`call_journal.py`、`context.py`、`method_scope.py`、`provider.py`、`store.py` 六个运行时文件。组合相对 PR 只增加线上现有的 **15 行 provider 适配**，不修改预算/质量实现；新增文件均为离线检查和测试。

两个方向都按字节验证：

1. 从组合 provider 去掉 DeepSeek 函数及两行请求参数，结果精确等于 PR provider。
2. 从组合 provider 去掉 PR 新增的 `request_reservation()`，结果精确等于线上 provider。

差异可直接检查：[PR → 组合运行时](pr36-to-candidate-runtime.patch)、[线上 → 组合运行时](live-to-candidate-runtime.patch)；逐文件摘要见 [组合证明](combination-proof.json)。补丁采用零上下文格式，离线应用检查需 `git apply --unidiff-zero`。两处改动互不覆盖。`pyproject.toml`、`uv.lock` 完全一致；线上和候选的 **83 个已安装包版本无差异**，Python 可执行文件路径一致，不需要新增依赖。`models.py`、课程工具契约、质量复核、反馈实现和其他配置读取模块均沿用原代码。无需新增环境变量，不修改现有个人模型路由、加密密钥、deadline 或功能开关。

`store`、`attempts`、`feedback_store`、`approval`、`models` 的 SQL `SCHEMA` 字面值与线上一致，本组合不增加数据库迁移。新增预算诊断和观察指纹使用已有 JSON 字段/事件表。旧终态状态/公开错误码保留，跨版本在途 checkpoint 的消息指纹变化仍 fail closed。

另从线上启动器提取纯 `frozen_command` 函数，在隔离路径和假配置上验证：能选择新解释器/PYTHONPATH，保留其他配置值，仍显式开启反馈，并拒绝非 Agent 命令。未执行启动器 main、原环境 loader 或 execve。**没有读取生产凭据、个人模型绑定或生产数据库**，因此这里确认的是配置接口兼容，不宣称验证了当前账号的供应商连接或远端模型可用性。

## 确定性出题与反馈

新回归使用 `ModelRegistry` 的合成加密凭据与冻结路由：决策 `deepseek-flash`，复核 `deepseek-v4-pro`，地址为官方 `/v1`。实际走 `RegistryProvider → ChatProvider → 标准 HTTP 请求/响应解析 → LangGraph → PostgreSQL`；HTTP 用 `httpx.MockTransport` 返回预置响应。没有替换 runtime 的模型调用、引用验证、质量复核或预算扣减。

每次请求检查 non-thinking 参数、`required` 工具选择、原输出额度和超时。课程方法观察、逐句解释支持、逐项目标、答案与方法范围均走当前严格契约。合成课程证据明确支持本夹具的停止条件任务；检查结果只证明协议/执行机制，不能当作真实模型质量评分。

| 机制阶段 | 预留 | 模型调用 | 工具调用 | 结果 |
| --- | ---: | ---: | ---: | --- |
| 两次六条检索（重叠五条）→补读→解释及两题→独立复核 | 61,790 / 64,000 | 5 | 4 | succeeded，产物保存 |
| 保存具体作答→盲课程依据→独立反馈复核 | 28,524 / 64,000 | 4 | 2 | succeeded，绑定精确 attempt_id |
| 最终出题复核已记 journal、产物提交前中断后恢复 | 同上 | 同上 | 同上 | 不重发 HTTP，不重复扣费/发布 |

健康完整链路为九次 **Mock HTTP**，真实付费调用零。方法观察仅一次；反馈不覆盖作答，重新创建 Store 后仍能读取已保存反馈。取消、版本变化、伪造引用、质量拒绝和预算不足均不发布产物。预算不足在任何 HTTP 请求前停止；质量拒绝后若剩余额度不足则保留预算终态，绝不把拒绝改为接受。

34 项协议矩阵覆盖官方根地址、`/v1`、尾斜杠、443、两个模型，以及 300/900/1200 输出上限；非官方域名、异常路径/端口、query、fragment、userinfo 和非白名单模型不继承适配。另有七项完整机制检查及一项出网保护反向测试，定向 **42 passed、0 skipped**。

冻结导出源码的完整 Python 单元与独立 PostgreSQL 集成测试：**793 passed、0 failed、0 skipped**，179.71 秒；另有一条现有 Starlette/AnyIO 弃用警告。Ruff lint/format 与 `git diff --check` 通过。定向 42 项是上述全量集合的子集，不重复累计。执行命令和 supervisor 终态见 [verification.json](verification.json)，原始输出见 [全量日志](full_frozen-output.txt) 与 [定向日志](focused-output.txt)。所有长检查使用既有 `scripts/dev/run_check.py`；原始记录另存，不覆盖历史文件。

## 隔离与回退

测试使用本轮新建的 PostgreSQL/pgvector，loopback 25459、数据库 `lecturelens_agent_test`，不复用上一轮测试库，更不使用生产库。离线执行器仅传基础环境和该测试 DSN，不传生产模型凭据/代理环境；Python 子进程继承 socket/DNS 保护，允许该数据库与本机高位测试端口，拒绝外网及本项目生产端口。反向测试在真正联网之前拒绝供应商 DNS、外部 IP 和生产 PG 15439。它是 Python 层保护，libpq 使用显式校验的独立测试 DSN，不把它描述为操作系统网络沙箱。

本轮没有切换生产，无需执行生产回退。将来若获准部署：

1. 先记录原 unit/drop-in、只读 release、provider/lock 摘要和不含明文凭据的模型配置身份；通过授权接口停止新增 Run，排空或取消 queued/running/awaiting_approval。不得手改 Run 状态。
2. 只切换 Agent 源码/解释器引用，保留现有 Java、模型、路由和数据库。不得把开发目录或打包测试环境当作生产 release。
3. 出现问题时恢复当前 `bc2e6cc` 加相同 DeepSeek 适配的原 release/启动引用及原配置，通过当次获准的服务管理流程回退。provider 必须匹配上述 `3b70650e…`，不能误退到缺少 non-thinking 的裸 `bc2e6cc`。
4. 保留 PostgreSQL 中的失败、usage、journal、产物和作答；本补丁没有 DDL 差异，不用全库还原丢弃新数据。JSON 扩展不等于在途 checkpoint 可跨版本无缝恢复；必要时按原错误停止并新建经授权 Run，不能重标旧失败。

## 尚未验证与下一步边界

- 真实 DeepSeek 的工具输出、语义复核能力、超时、usage 和价格均未验收；Mock HTTP 成功不证明远端支持或教学质量。
- PR 已知的非方法来源预览缩短、复用既有方法可能忽略更合适新方法的风险保留；长串行检索仍可能在 64,000 内无法完成。质量门没有削弱，不以提高上限掩盖问题。
- 本轮未启动隔离/生产 Java 或浏览器，也未读取生产模型路由。Java 权限边界以未改动的代码及现有确定性授权/版本回归为证，不冒充线上浏览器验收。
- 独立候选留在本地分支与冻结制品，未合并、未部署、未改变 PR #36 原 SHA。真实验收的次数、环境与费用门禁见 [后续验收约束](NEXT_REAL_ACCEPTANCE.md)。

**STOP：真实模型验收与生产部署都需用户另行授权。**
