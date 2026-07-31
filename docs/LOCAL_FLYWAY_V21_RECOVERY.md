# 本机旧 V21 开发库恢复

本说明只适用于曾执行过未提交旧版 V21、且确认从未共享的本机开发数据库。正式环境、服务器数据库和共享测试库不得按本说明执行 `repair`。

当前正式迁移保留 `V21__add_analysis_task_source_language.sql`。应用配置必须保持 Flyway validation 开启，不得通过忽略 checksum、删除 `flyway_schema_history` 或自动执行 `repair` 绕过校验。

本机出现仅 V21 checksum 不一致时：

1. 停止应用，并备份本机数据库，至少单独备份 `flyway_schema_history`。
2. 确认校验结果只有 V21 checksum mismatch，且数据库已经具备当前 V21 的最终结构。
3. 使用与后端依赖一致的 Flyway 版本，对该本机开发库人工执行一次 `repair`。
4. 重新执行 `validate`；只有 validation 成功后才恢复普通启动。
5. 不把 `repair`、`clean` 或关闭 validation 的配置写入 `.env`、启动脚本或应用代码。

如果旧 V21 曾在任何共享数据库执行，不得修改或 repair 已共享的迁移；应恢复已发布 V21 的原始内容，并用新的迁移版本完成后续结构变化。
