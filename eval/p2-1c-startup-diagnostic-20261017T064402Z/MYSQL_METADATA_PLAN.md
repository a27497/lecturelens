# 下一步最小授权：隔离迁移元数据只读核对

状态：方案，**未执行**。本轮唯一启动已结束；不申请再次启动 Java 或临时 unit。

所需授权：一次以 dev 身份运行的短时诊断进程，仅在内存选择性消费现有 runtime.json 的 MYSQL_JDBC_URL / MYSQL_USERNAME / MYSQL_PASSWORD。不得读取 root 密码、其他业务配置、模型凭据或密文，不输出连接配置值。

连接沿既有目标，连接前将 schema 强制为既定隔离 schema；拒绝 root、内嵌凭据、其他身份/目标回退。建立只读会话后先 SELECT DATABASE() 校验，仅输出匹配布尔值。任何认证、权限、目标或磁盘异常立即停止，不增加权限。

只读查询白名单：

1. 当前 DATABASE() 的匹配状态。
2. flyway_schema_history 的 installed_rank / version / checksum / success；不取 description、script 路径、installed_by 或任何业务字段。
3. information_schema.tables 中固定四个 V32 表的存在性：asr_scheduler_state、asr_chunk_checkpoint、asr_scheduler_event、asr_result_cache。
4. information_schema.triggers 中固定两个 V32 触发器的存在性：asr_state_immutable_input、asr_chunk_immutable_input；不取触发器正文、DEFINER 或其他 schema 内容。

输出只保留版本、计数/布尔、checksum 匹配和固定诊断类别；与 offline-migrations.json 的实际 Flyway checksum 比较。无任何 INSERT/UPDATE/DELETE、DDL、GRANT、repair、clean、供应商请求或 Java 启动。

这一步才能区分当前迁移历史/对象是否与冻结候选一致；若仍无法确定具体失败原因，如实报告，不执行修复。不得把 V32 是唯一新增文件当成 V32 已失败的证明。

精确修复需以核对结果为依据，另行给出作用对象、前后条件、备份/恢复和写授权；不通过修改 checksum、关闭 validate、修改冻结 JAR 或重置历史使启动通过。
