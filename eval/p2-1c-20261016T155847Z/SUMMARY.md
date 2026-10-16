# P2-1c 当前结果：本地候选已归档，真实验收未启动

A/B/D/F/G 机制实现已本地提交；C/E 未纳入。阶段 4 的 Java、前端、Python/PostgreSQL 全量回归与本地打包通过，正式课程验收尚未启动。

| 范围 | 实测检查结果 |
| --- | --- |
| 阶段 1 | 134 项定向回归、32 项独立 MySQL 检查通过，0 失败/错误/跳过 |
| 阶段 2 | 192 项回归通过；明确开启合并后 7 项复核通过（重复项不累加） |
| 阶段 3 保留路径 | 101 项机制通过，0 失败/错误/跳过 |
| 后端全量 | 1765 项通过，0 失败/错误/跳过 |
| 前端全量 | 119 项通过，0 失败/错误/跳过；类型检查退出 0 |
| Python/PostgreSQL 全量 | 727 项通过，0 失败/错误/跳过；专用 PostgreSQL 已清理 |

**C/E 未纳入**：兼容性特性探针 2 项为 1 failure、1 error；完整保留，不改成成功。本候选拒绝开启 streamingTranslation/materialsParallel，不能宣称已实现稳定增量翻译或资料并行。详见 STAGE3.md。

A 使用可冻结的原文模式、小节来源、统一预检和独立超限码；资料预算不扩大。B 的窗口/冷却/尝试次数持久化，D 保留合并前后区间，F 沿用已有 16000/mono 默认并增加观测，G 默认 OFF 且按所有者/配置隔离。真实参数尚待 Java 启动后核验，详见 STAGE2.md、candidate-options.json。

失败均保留：阶段 1 MySQL 首轮 32 项有 1 failure/1 error；阶段 2 首轮 179 项有 4 failures/2 errors；后端首轮全量 1765 项有 1 failure。Python 首轮 727 项有 1 failure（计划库名被既有白名单拒绝），同一容器内改用允许的测试库后 727 项全部通过；未放宽校验。修复、日志/hash 和重跑记录见 VERIFY/STAGE2/STAGE4，不把重复检查累加为更多独立测试。

本地 JAR 的身份见 candidate-artifact.json。专用 MySQL 和 PostgreSQL 均已按各自许可停止删除；Java 尚未启动。没有 push/merge/部署，没有读取实际供应商凭据、改在线绑定或发真实模型请求。已有未跟踪 DIAGNOSIS.md 保留。

正式十次提交 0，完整链路成功率、阶段 mean±std、片数/调用/峰值/限流、CER、目录价费用、SIGKILL 恢复及缓存命中演示均**未测**。不能将其写成已执行的 0/10。trials.jsonl 当前为空。

全量门禁及候选字节一致性见 stage4-gates-verified.json。用户已授权指定临时 unit 的受控启动、冒烟及满足 ASR 条件后的正式十次；检查 99-system-models.conf 未检出任何 LoadCredential*/SetCredential* 项，无法按许可引用系统模型凭据，因而尚未创建/启动 unit。没有确认明文密钥或读取其他配置。需要补充受控凭据指令/路径，详见 STAGE5_PREFLIGHT.md。当前磁盘 df 显示 76%，本轮快照见 stage5-startup-preflight.json。
