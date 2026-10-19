# Study Agent 发布审批与崩溃恢复

实验能力，默认关闭，未部署。已有课程所有者可以在浏览器勾选“发布前由我审批”；`START` / `START_FEEDBACK` 的 `approval_required: true` 冻结到该 Run。Java 以认证身份核对课程所有权、未删除状态、当前 revision 与索引就绪状态；Python 再核对 Session/Run 范围。当前没有跨账号管理员角色或代审权限，不允许以客户端传入的 owner_id 代审他人的课程。

模型照常选择检索、补读、生成和复核工具。通过复核的候选先写入 `study_approval`，不会写入已发布的练习/反馈表。独立 LangGraph `approval` 节点使用 `interrupt`，Run 进入 `awaiting_approval`，Session 仍占用唯一活动 Run 槽位；worker 不轮询或自动批准等待中的 Run。刷新浏览器和进程重启保持等待状态。等待期间暂停执行 deadline，保存剩余秒数；取消、课程版本和删除围栏继续有效，不重置调用/token 预算或读取重试上限。

`DECIDE_APPROVAL` 需要明确 Session、Run、幂等 request_key 和决定：

- `approve`：继续执行，重新经过 Java CHECK、worker token、取消与 deadline 检查，再发布。
- `edit`：`approval_edit` 是 1–4,000 字符的非空人工文字。练习替换发布说明；反馈增加单独标明的人工修改建议。答案、评分点、题目、Evidence ID 与引用不能由此接口替换。发布内容标为人工编辑，不称为模型复核过的新文字。
- `reject`：恢复发布节点后进入 `failed / APPROVAL_REJECTED`，不创建练习或反馈产物。作答及此前已发布的产物不受影响。

决定一次写入后不可覆盖。重试同一 request_key、决定和文字返回原状态；不同决定/文字产生 `APPROVAL_DECISION_CONFLICT`。决定与重新入队同一事务提交。审批草稿、等待、决定、发布/拒绝均有公开 Trace；草稿正文、私有答案和人工修改正文不进入公开事件流。批准后的发布事务以 Run 为唯一键，创建产物与发布事件原子提交。

## checkpoint 与调用日志

`PostgresSaver` 的节点 checkpoint 和外部调用不是一个原子事务。仅靠 checkpoint 无法保证崩溃后不再次扣预算或调用模型。本次补充：

- 模型请求用节点、turn、call_id、调用顺序、用途和协议重试阶段生成稳定重放键。同一决策节点重放时复原预留前的预算提示和由预算决定的反馈工具列表。提示中的实时剩余预算不参与重放键；独立输入指纹忽略这个易变提示，但检查其余输入和 schema，不匹配则以 `MODEL_INPUT_CHANGED` 失败。预算、调用日志与 `model_started` 原子预留；响应或失败观察与完成事件原子保存。节点重放复用已提交观察并写 `model_replayed`，不再次扣费或发请求；复用前后仍重新检查 Java 授权与取消围栏。
- 预留已提交而响应未落库时，无法判断远端是否已经执行。恢复以 `MODEL_OUTCOME_UNKNOWN / checkpoint_recovery` 明确失败，不重发该模型调用，不假报成功。这也覆盖预留后、实际请求前崩溃的保守失败。没有远端幂等协议时不能宣称模型请求自动恢复的 exactly-once。
- 逻辑工具预算以 call_id 持久化预留，checkpoint 重放不重复扣。新物理只读重试仍按 P0-1 的持久预算扣费；不完整的读取预留仍受最多三次的持久尝试上限约束。每次重启不重置上限。
- 工具结果和产物保持原有事务幂等键。审批草稿、决定、模型日志、逻辑预算预留通过 Run 的外键随课程删除清理；框架 checkpoint 的删除仍在 Session 执行锁内，并可在清理进程崩溃后再次执行。

迁移为追加字段/表并更新唯一活动 Run 索引。已有 Run 默认无需审批；旧产物和公开 API 字段兼容。已有私有 Trace 中的匹配模型观察可以导入重放；旧模型记录没有完成观察或无法定位模型预留时仍保守失败，已扣预算不会重置。导入的历史单次预算 token 没有独立记录，记为不可得（原 Run 的累计预留不变），不能据日志的零占位推算费用。新日志保存私有模型输出，权限和保留期与现有私有 Trace 相同；不得把真实学习者原文或 provider 凭据放进公开评测记录。

## 验证与复现

[审批与逐点 SIGKILL 报告](../eval/approval-recovery-20261014/README.md)。`scripts/eval/check-study-crash-matrix.py` 运行真实子进程、PostgreSQL 与 PostgresSaver；确定性模型/Java桩用于验证执行机制，不能证明真实模型的教学质量或网络服务幂等性。

```bash
AGENT_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:PORT/lecturelens_agent_test' \
  agent-service/.venv/bin/python scripts/eval/check-study-crash-matrix.py \
  --trials 1 --output eval/approval-recovery-NEW/matrix
```

必须使用独立临时测试实例，不能指向服务数据库。输出目录必须不存在；原始失败试验保留。`--trials` 控制每个位置样本数，`--smoke` 仅运行小集合。报告里的恢复耗时包含新 Python 进程启动、数据库重连、checkpoint 恢复以及审批决定之后的发布，不是纯节点执行延迟，也不包含人为等待审批的时间。
