# 47de0cc 独立 MySQL 验收

**通过：47 项，0 failures、0 errors、0 skipped。** MySQL 实际版本为 8.4.11；运行完整 Flyway 迁移后的独立随机 schema。本轮新增验收测试，未发现需要修改生产实现的缺陷。

| 测试类 | 项数 | 关键范围 |
| --- | ---: | --- |
| LegacyTranslationMySqlTest（新增） | 7 | 截断恢复、正常/无效输出、真实 mapper/事务/诊断/任务状态、重复投递 |
| SystemModelRuntimeMySqlTest | 21 | 数据库模型路由、快照、结构化输出与 HTTP 错误协议 |
| PipelineUsageLedgerMySqlTest | 7 | 失败调用 usage、物理调用台账、不重复计费、未知用量边界 |
| TranslationCheckpointMySqlTest | 7 | 原有恢复/幂等与新增 3 项持久预算、深度耗尽检查 |
| PipelineResumeMySqlTest | 5 | 恢复、旧代次、取消/删除等状态边界 |

## 关键实测

- `HTTP 200 + 空 content + length` 的父调用被记录为 OUTPUT_TRUNCATED，usage 为 903/3073/3976；随后 3 个成功子调用各为 2/3/5，任务成功。MySQL 阶段汇总与诊断 SQL 聚合均为 **909/3082/3991**（prompt/completion/total），batch_count=4、retry_count=3，最终只保存 1 份分段行和 1 份全文结果。
- 空输出、非法 JSON、非对象 JSON 各只调用 1 次，任务与调用记录均失败，错误仍为 OUTPUT_INVALID，HTTP 200 与固定 check 保留；没有部分结果。
- legacy 深度上限设为 1 的合成测试在 2 次截断后失败，诊断保留 total tokens=7952，无部分产物。调用数/深度/token 的 V2 持久预算耗尽后重新打开 session，均不增加调用或改写失败尝试，也不能发布。
- MySQL trigger 注入最终全文写入失败，分段和全文的删除/替换及 content revision 一同回滚，既有合成产物保持原值；诊断独立保留，任务/调用记录进入失败，数据库错误未被误归为 OUTPUT_INVALID。
- 成功/失败终态重复投递原消息，不新增模型调用，不改写原调用历史；已有 checkpoint 用例证明截断父节点与已完成子节点不会被重跑。

legacy 整体失败时，阶段摘要的 usage 仍可能为空；已知的逐调用 usage 保存在 translation_call_diagnostic。本次不补造摘要用量。V2 的物理调用台账单独验收，诊断与阶段摘要不会被重复累加收费。这是两条路径的记录边界，不能混同。

## 证据与清理

- `translation-mysql-02-check.json`：最终 47 项计数、JUnit/日志哈希和清理状态；[VERIFY.md](VERIFY.md) 提供命令、源码范围和私有原始记录位置。
- 首次运行 `translation-mysql-01` 因新测试跨包调用 package-private setter 编译失败，没有执行测试；完整日志保留。修正为测试专用 SyntheticTranscriptStep，生产接口未改。第二次最终通过。
- 专属容器 `lecturelens-translation-mysql-20261016T185217Z` 经 ID、镜像、创建时间、标签、端口和挂载复核后停止删除；所有随机 fixture schema 已删除，端口 33318 已释放。没有清理其他数据库或容器。
- 两次 Maven 检查均已收尾，runner/子进程消失；历史证据、47de0cc 验证记录、P2-1c 冻结 JAR 及在线服务身份保持一致。原有未提交 DIAGNOSIS.md 未读正文、未修改、未提交。详见 before.json / closeout.json。

本轮仅验证数据库与执行协议。供应商响应全部合成，真实供应商行为、真实课程质量及线上修复效果未测；其余 10 次历史故障仍因缺少细分证据保持未知。未运行 P2-1c 正式验收，未修改生产配置/数据库/服务，未部署、push 或 merge。
