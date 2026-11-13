# 第二次应用启动：失败冻结，health 未完成

**本任务到此冻结，不再排障。** 已按用户批准执行第二次应用启动，health 未达到 UP；`FREEZE.md` 是最终结论。没有提交课程任务、冒烟或十次，也没有改变冻结候选或线上配置。

## 核查与执行结果

- 只复用本轮独立 MySQL 的原 container ID `cf44344fee2cd04c285dbeef6d016d10708e75872f91021c5ece7a4880085e98`，固定本地 MySQL 8.4 image、owner label、127.0.0.1:33319、1 GiB/1 CPU、`--skip-log-bin` 和原数据挂载均核对通过。没有新建第二个 MySQL 容器或触及旧演示实例的写权限。
- 在该独立实例新建 `lecturelens_p21c_20261017_r2`，显式 utf8mb4/utf8mb4_unicode_ci，授予本轮已有应用账号权限。应用账号实测新库表数为零、binlog=0、默认排序规则正确。第一次失败 schema 的迁移历史在准备前后逐字节相同，见 `failed-schema-before.json` 和 `mysql-resource.json`。
- 重建本轮新 owner 的独立 Redis：固定镜像、127.0.0.1:33318、DB 15、无持久化，两次完整空库检查通过。结束后仅停止删除该确切实例。
- 本轮起点 `47759ac27dd9e5d1ba47b952cadb7d14684d8cad`。冻结源仍为 dcc4dda，JAR SHA256 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`。从冻结 JAR 提取的文件全部逐字节匹配；本轮只修改独立 eval 适配器的 schema/排序规则围栏、资源身份和本次 unit 路径。
- Java 仅启动一次，本任务累计两次。应用发出 `P21_FINAL_ISOLATION_GATE_PASS`，然后发出 `P21_MIGRATIONS_COMPLETE`。该标记位于应用实际 Flyway migrate 返回且 applied 数量为 32 之后；没有将它当作配置直传、指纹或健康成功证据。

## 失败与根因边界

未生成 config-copy.json、migration-result.json 或 health.json，也未出现 CAPTURE_GATE_PASS。受控启动器在 2026-10-17T10:45:17Z 保存 `JAVA_TERM_INCOMPLETE`、java_exit=null：Java 在 45 秒 TERM 等待期内未退出。该收尾类别覆盖了最初失败类别，**最初失败子因及配置直传是否提交均未确定**。

没有追加数据库查询、提取原始日志/异常消息、复现实验或重启来追查。只有既有 marker、终态文件和身份/资源收尾检查作为证据。不把上轮 V13 排序规则问题重新标成第二次根因，也不据缺少成功记录认定配置行完全没有读取或目标完全没有写入。

Java 随后自行退出，临时 unit not-found，18091 无监听；未使用 SIGKILL。保留最初 closeout-service.json 的 null 退出状态，后续消失身份另记 closeout.json，不伪造最终退出码。独立 MySQL 仍运行，第一次失败 schema、r2 schema 及绑定数据目录保留。这里只验证数据生命周期与挂载保留，没有验证 SIGKILL 恢复。

## 检查与真实验收

Python AST/边界合成检查通过，冻结 classpath 编译退出 0（仅 deprecated API 提示）；依赖准备、编译及 Redis 收尾三个 supervisor 均 SUCCEEDED、cleanup.complete=true。未重跑应用全量机制测试；历史后端 1765、前端 119、Python/独立 PostgreSQL 727 的结果及失败继续保留，与本次启动失败分开报告。

health、配置直传/内容 hash 校验、真实模型任务质量均未完成。无 CER、速度、费用、恢复或缓存演示结论。详见 `FREEZE.md`、`VERIFY.md` 和 SHA256SUMS。

工具没有读取 .env、/proc/*/environ、供应商 API Key 或既有 root 密码；受控应用只消费既有配置/credential 引用。旧演示实例没有 DDL/GRANT/写操作；已有未跟踪 DIAGNOSIS.md 的 stat 未变。未 push、merge 或部署。
