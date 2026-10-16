# P2-1c 当前结果：本地候选已归档，真实验收未启动

A/B/D/F/G 机制实现已本地提交；C/E 未纳入。阶段 4 的 Java/前端检查与本地打包通过，Python/PostgreSQL 尚未测，完整门禁未完成。

| 范围 | 实测检查结果 |
| --- | --- |
| 阶段 1 | 134 项定向回归、32 项独立 MySQL 检查通过，0 失败/错误/跳过 |
| 阶段 2 | 192 项回归通过；明确开启合并后 7 项复核通过（重复项不累加） |
| 阶段 3 保留路径 | 101 项机制通过，0 失败/错误/跳过 |
| 后端全量 | 1765 项通过，0 失败/错误/跳过 |
| 前端全量 | 119 项通过，0 失败/错误/跳过；类型检查退出 0 |
| Python/PostgreSQL 全量 | 未测：等待独立测试依赖启动许可 |

**C/E 未纳入**：兼容性特性探针 2 项为 1 failure、1 error；完整保留，不改成成功。本候选拒绝开启 streamingTranslation/materialsParallel，不能宣称已实现稳定增量翻译或资料并行。详见 STAGE3.md。

A 使用可冻结的原文模式、小节来源、统一预检和独立超限码；资料预算不扩大。B 的窗口/冷却/尝试次数持久化，D 保留合并前后区间，F 沿用已有 16000/mono 默认并增加观测，G 默认 OFF 且按所有者/配置隔离。真实参数尚待 Java 启动后核验，详见 STAGE2.md、candidate-options.json。

失败均保留：阶段 1 MySQL 首轮 32 项有 1 failure/1 error；阶段 2 首轮 179 项有 4 failures/2 errors；后端首轮全量 1765 项有 1 failure。修复、日志/hash 和重跑记录见 VERIFY/STAGE2/STAGE4，不把重复检查累加为更多独立测试。

本地 JAR 的身份见 candidate-artifact.json。专用 MySQL 已按许可停止删除；Java、PostgreSQL 尚未启动。没有 push/merge/部署，没有读取实际供应商凭据、改在线绑定或发真实模型请求。已有未跟踪 DIAGNOSIS.md 保留。

正式十次提交 0，完整链路成功率、阶段 mean±std、片数/调用/峰值/限流、CER、目录价费用、SIGKILL 恢复及缓存命中演示均**未测**。不能将其写成已执行的 0/10。trials.jsonl 当前为空。

下一步需按 POSTGRES_TEST_PLAN.md 获得独立 PostgreSQL 启动/清理许可，完成 Python 全量；Java 启动/重启仍需单独许可。当前磁盘 df 显示 76%，原始快照见 stage4-checkpoint.json。
