# 复现顺序与独立 PostgreSQL

从仓库根目录执行，使用已安装依赖的 `agent-service/.venv`。只允许专用测试实例上的 `lecturelens_agent_test`，不能指向服务数据库。连接串由环境提供，不写入报告或 Git。新批次目录必须不存在，已有结果不能覆盖。

## 只读复算已保存记录

无需数据库、Java、浏览器或模型凭据：

```bash
agent-service/.venv/bin/python eval/approval-recovery-20261014/verify.py
```

此命令从原 JSONL/JUnit 计算，逐点核对原 summary 和 RESULTS；遇到不一致退出非零。不会重新评分、改标注或写旧文件。数字和口径见 [VERIFY](VERIFY.md)。

## 最小机制抽样复跑

先准备专用 PostgreSQL（包含 pgvector 扩展支持），设置 `AGENT_TEST_DATABASE_URL`。串行执行，测试不要与恢复计时并行：

```bash
export AGENT_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:PORT/lecturelens_agent_test'
APPROVAL_BATCH="eval/approval-recovery-NEW-$(date -u +%Y%m%dT%H%M%SZ)"
agent-service/.venv/bin/python scripts/eval/check-study-crash-matrix.py \
  --smoke --trials 1 --output "$APPROVAL_BATCH/matrix-smoke"
agent-service/.venv/bin/python scripts/eval/check-study-approval-recovery.py \
  --trials 1 --output "$APPROVAL_BATCH/approval-sample"
```

**必须先矩阵、后审批，使用同一专用测试库。** 矩阵脚本初始化 VectorStore、StudyStore/PostgresSaver 以及评测专用 `eval_remote_call`。审批脚本复用矩阵驱动的 worker、快照与不变量检查；它不会自行迁移基础 Agent/checkpoint schema。旧审批脚本依赖前者建审计表；补充后的脚本会 `CREATE TABLE IF NOT EXISTS eval_remote_call`，缺少 `study_run` 或 `checkpoints` 时在创建输出目录前明确报错，给出矩阵 smoke 命令。该表只记录合成评测的远端调用，不属于生产存储格式。

`--smoke` 只是固定子集，不是 523 点全覆盖。审批 `--trials 1` 是 18 个组合各一次（18 次），不能替代原 18×3 的 54 次证据。等待边界覆盖练习/反馈的批准、修改、拒绝六种组合。

## 完整重跑

在全新目录，去掉矩阵的 `--smoke`，保留矩阵 `--trials 1`；然后审批 `--trials 3`。当前轨迹发现的注入点数可能随代码改变；必须以新原始记录为准，不能沿用旧 523/577。每个新 worker 的源码身份由矩阵 manifest 检查。旧冻结驱动、运行时身份见 `matrix-final/identities.jsonl`，本次审批评测脚本的表初始化补丁不追溯替换旧身份。

## 审批测试和静态检查

评测完成后在专用测试库执行：

```bash
agent-service/.venv/bin/pytest agent-service/tests/test_study_approval.py -q
agent-service/.venv/bin/ruff check agent-service scripts/eval/check-study-approval-recovery.py \
  scripts/eval/check-study-crash-matrix.py eval/approval-recovery-20261014/verify.py
agent-service/.venv/bin/ruff format --check agent-service \
  scripts/eval/check-study-approval-recovery.py scripts/eval/check-study-crash-matrix.py \
  eval/approval-recovery-20261014/verify.py
```

确定性模型和 Java Authority 桩验证执行机制；不声明真实付费模型质量或远端 exactly-once。真实浏览器原证据另列，不通过本抽样命令重拍。
