# 冻结候选启动诊断：Flyway 初始化阻断

**唯一一次受控启动失败；已确认 Spring 依赖初始化因 Flyway 异常中断，尚未确认更细的迁移/校验子因。** 未健康就绪、未提交课程任务、未重试启动或执行验收。原 bootstrap、最终隔离门禁、版本 10 和指纹校验均通过。

## 实测异常与证据边界

`startup-causes.jsonl` 仅保存固定类别，实际异常链为：

```
DEPENDENCY → DEPENDENCY → BEAN_CREATION → FLYWAY
```

没有捕获 SQL 类别，因而没有 SQLState / vendorCode。原应用异常被 wrapper 捕获后按设计退出 45；这不是新的数据库错误码。`startup-result.json` 与 `closeout-service.json` 记录 FAILED / APPLICATION_START_FAILED、Java exit 45、课程任务提交 0、owned_tasks=[]、used_sigkill=false。退出记录时间为 2026-10-17T06:45:52.465807+00:00。

可以支持的结论是 **Flyway 这一启动依赖阻断了 Spring 容器完成初始化**，影响本轮隔离应用的 readiness，未进入 ASR 或课程处理。不能仅凭这个类别认定具体版本失败、校验和不匹配或权限错误。现有分类把 FlywayException 与 FlywayValidateException 合并为 FLYWAY，未保留两者的区分；异常消息/堆栈没有保存，也不会事后补取。

## 额外只读与离线核实

- 同范围新 Redis 创建、实例身份、两轮空库遍历及 dev 服务内的再次检查均通过；没有访问原 Redis 数据。
- 隔离数据库连接、schema、模型版本 10、无待执行任务/outbox、五课媒体/字幕身份通过。原 Java preflight 退出 0，完整应用中的最终隔离与原捕获门禁也打印 PASS。
- 冻结候选含 32 份迁移；V1–V31 的字节与 P2-1b 旧提取归档一致，新增 V32。**归档比较不是数据库已应用历史的比较。**
- 使用冻结 classpath 自带 Flyway 11.7.2 / MySQLParser 离线解析全部 32 份迁移，32/32 通过，并计算该库的迁移 checksum。没有 datasource、数据库连接、Spring 应用启动或 DDL 执行。这只验证本地解析，不验证数据库对象、权限或 Flyway 历史。
- 没有读取当前隔离库的 flyway_schema_history / 对象状态，具体子因仍为 UNKNOWN。不能据此修改迁移、repair、清理 schema 或放宽验证。

## 实施和验证

本轮仅新增独立诊断目录。保留原 P21Bootstrap 和已批准的最终隔离监听器原字节；冻结 JAR SHA256 仍为 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`。

诊断入口移除了任务提交、令牌和 trial 函数，HTTP 仅检查健康端点；达到 UP 或异常终态即收尾。wrapper 副本只补充固定异常类别，不读取/输出异常消息或堆栈；原校验、模型版本/指纹、schema/topic/消费组、Redis DB 15、cache OFF、C/E=false 和冻结预算保持不变。

离线边界/日志过滤检查、原 bootstrap selftest、wrapper selftest 均通过；两个 supervisor 检查（包含离线迁移解析）均 SUCCEEDED 且后代回收完整。没有重跑无关全量测试，未进行真实供应商质量验证。冒烟、正式十次、CER、费用、恢复和缓存演示仍未测。

## 最小下一步与修复边界

最小下一步是**不启动 Java/unit 的隔离 MySQL 只读迁移元数据核对**，将当前已应用版本/checksum/success 和 V32 对象存在性与本轮冻结资源结果比较。当前证据不足以制定可执行的修复 DDL，不能用猜测性修改或再次启动替代这一步。

所需最小授权见 MYSQL_METADATA_PLAN.md：一次 dev 短时进程仅在内存消费现有 MySQL 连接字段，强制既定隔离 schema，只读迁移历史及固定对象元数据，不读业务内容或任何凭据密文，不启动服务，不做修复。不申请 root、提权或供应商调用；当前身份权限不足即停止。

此新增凭据消费位置不在已授权 unit 内，当前许可不能转用；本轮已停止。元数据证实具体差异后，再提出仅针对该隔离 schema 的精确修复及所需写授权；本轮未执行 flyway repair/clean、DDL、模型调整或任何重启。

## 收尾

临时 unit 已自动移除，原 Java 身份消失；本轮 Redis 经 container ID/owner label 核验后停止并删除。仅删除本轮 runtime/extra/tmp/workspace，保留安全证据。原 Redis、在线服务及受保护容器未作修改。

104 份保护证据与冻结 JAR 哈希前后一致；原未提交文件 stat 和在线 backend PID/start 时间相同；本轮端口无监听。磁盘终检占用 75.91028033843766%，距 85% 为 14,077,922,508.8 bytes。未 push、merge 或部署。
