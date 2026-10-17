# 独立 MySQL：第一次应用启动失败，等待第二次启动授权

本轮按追加授权改用独立 MySQL；旧方案中对 `lecturelens-demo-l2-mysql-1` 建库/授权的路径已拒绝并作废，未执行。**应用启动一次，未达到 health UP；实际阻断在 V13，尚未执行到 V32。** 未提交课程任务、未跑冒烟或十次，配置导出/导入也未开始。

冻结候选仍为 `dcc4dda753afd89fafcc2375eaf3cd942dba4b02`，JAR SHA256 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`。本轮起点为本地诊断提交 `9b9928e`，其基点仍为用户指定的 `4be8593`。没有改 JAR、迁移 SQL/checksum、validate 或原有 schema；未 push、merge 或部署。

## 已创建资源

- 新 MySQL：`lecturelens-p21c-runtime-mysql-20261017`，本地固定镜像 `sha256:3466ba4a4828aa8d46fb7c3bc16b67b781c98413cf4ea0fac6feaa6e881faa26`，`--pull=never`、`--skip-log-bin`，仅发布 `127.0.0.1:33319:3306`，1 GiB/1 CPU。
- 新库 `lecturelens_p21c_20261017` 及新应用账号 `p21c_app`。随机应用密码仅在本轮私有 0600 文件中供应用使用；没有读取既有 root 密码。容器内空密码 root 仅通过本轮容器 socket 执行新账号/新库准备。
- MySQL 绑定数据目录 `/home/dev/projects/lecturelens/.data/p2-1c-flyway-20261017T100358Z/mysql-data`；保留运行中的自有 MySQL、容器和数据，未删除目录，数据不依赖 Java 生命周期。本轮没有注入 SIGKILL，不能声称已验证强杀恢复。
- Redis 按历史独立方案新建：固定本地镜像、127.0.0.1:33318、DB 15、无持久卷/持久化；两次完整空库检查通过。应用退出后已按 container ID、image、owner label 核验停止删除，仅清理本轮 Redis。

## 本次启动与根因

2026-10-17T10:07:46Z 应用通过最终隔离门禁。Spring Boot 的实际 Flyway initializer 使用冻结 JAR 中原始 SQL 迁移；应用数据源和 Flyway 实际数据源都围栏到新 MySQL/新库，binlog 实测关闭。随后抛出 Flyway → SQL 异常：SQLState `HY000`、vendorCode `3780`，Java 退出 45；不是 V32 的原权限问题。

失败后仅在新独立库查询迁移历史和结构元数据，结果为 V1–V12 成功、V13 失败，已记录 checksum 均匹配冻结结果。新 schema 默认 `utf8mb4_0900_ai_ci`；已建 `analysis_task.id` 为 `varchar(64)` / `utf8mb4_unicode_ci`。冻结 V13 创建 `video_keyframe_analysis` 时未指定表排序规则，因此其 `task_id` 按新 schema 默认规则解释；该列外键引用 `analysis_task.id`，两者排序规则不兼容。V13 是单条 CREATE TABLE，表未建成。

**根因为独立库准备遗漏了显式的 `utf8mb4_unicode_ci` 默认排序规则。** `MYSQL_DATABASE` 自动建库继承了 MySQL 8.4 的默认规则，未沿用原建库计划中的显式规则。错误码 3780 的含义为外键引用列不兼容，见 [MySQL 8.4 错误参考](https://dev.mysql.com/doc/mysql-errors/8.4/en/server-error-reference.html)。具体列名未从原始异常消息取出，而是由冻结 V13 SQL及实测列/库元数据定位；未输出原始消息或堆栈。

本轮代码中的单 JVM 顺序为：应用 Flyway migrate → 等待配置直传校验 → 原 v10/环境指纹约束检查 → 后续初始化 → health。当前停在 migrate，所以没有连接旧 MySQL 导出配置，没有读取业务配置行，没有向旧 MySQL 执行 DDL、GRANT 或写操作。服务管理器沿用已获准的配置/credential 引用；工具没有读取 .env、/proc/*/environ、供应商 API Key 或既有 root 密码。

## 验证与限制

- Python AST/日志过滤/哈希边界检查通过：丢弃非白名单消息与附加正文、识别迁移 marker、带长度分帧的行 hash、迁移先于导入等待、单个应用 spawn、无任务端点。没有将这些合成检查当作管道已完成或模型质量证据。
- 使用冻结 classpath 编译两次（第二次增加 Flyway 实际数据源围栏），均退出 0；仅有 deprecated API 提示。提取文件全部逐字节校验匹配冻结 JAR。没有启动额外的 Java 自检或独立迁移 JVM。
- 本轮没有重跑应用机制全量测试。历史后端 1765、前端 119、Python/独立 PostgreSQL 727 通过及历史失败保留，见 `../p2-1c-20261016T155847Z/STAGE4.md`；C/E 探针未通过且不属于冻结候选。
- 四个新 supervisor 检查均 SUCCEEDED、后代回收完整；临时 unit 自动移除，Java PID/start-ticks 身份消失，18091 已无监听。
- health 未完成、配置直传未实测、真实课程验收未完成。没有供应商请求或课程任务的执行路径被触发，未生成任何质量/速度成功结论。

目前是本任务第一次应用启动失败，且仍属于 Flyway 阻断，累计远未达到一个工作日；未触发既定止损，暂不生成 FREEZE.md。第二次启动若仍失败即冻结，不再继续排障。第二次启动及保留失败 schema 的新空库方案见 `NEXT_START_PLAN.md`，等待用户批准。
