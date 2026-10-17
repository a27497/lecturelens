# P2-1c 冻结结论：第二次启动未达健康，停止排障

状态：**冻结，未达到 health UP，不再排障或启动 Java。** 2026-10-17T10:45:17Z 的第二次运行 closeout-service.json 为 JAVA_TERM_INCOMPLETE，Java exit 尚为 null；健康成功记录和配置直传校验成功记录均不存在。本任务已使用两次应用启动，达到用户指定止损条件。

## 已实现与保留

- 冻结候选仍为 dcc4dda，原 JAR SHA256 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`；未改 JAR、SQL/checksum 或关闭 Flyway validate，未 repair/clean 任何已有 schema。
- 仅在本轮独立 MySQL 创建 `lecturelens_p21c_20261017_r2` 并授权既有新应用账号；显式 utf8mb4_unicode_ci、初始表数 0、binlog 关闭均通过。第一轮失败 schema 和绑定数据保留，没有向旧演示实例执行 DDL、GRANT 或写操作。
- Redis 按独立固定镜像/新 owner 方案重建，启动前两次空库扫描通过。
- 已实现单 JVM 启动适配器：应用实际 Flyway initializer → 配置管道导入/行 hash 校验等待 → v10/环境指纹门禁 → health；源端仅既有非 root 账号只读事务，密文行只经进程内存与 stdin 管道传输，不生成 SQL 文件或输出行内容。该整条路径**未完成成功验收**。
- 应用实际发出 FINAL_ISOLATION_GATE_PASS 与 MIGRATIONS_COMPLETE 标记。不能将迁移标记等同于 v10 导入、指纹门禁或健康成功。

## 本轮机制检查

新适配器 Python AST/日志过滤、严格 SQL 类别白名单、行 hash 分帧、排序规则先于迁移、单个应用 spawn、无任务端点、无 repair/clean 检查通过；冻结 classpath 编译退出 0，提取文件逐字节一致。新库准备与编译 supervisor 均 SUCCEEDED、后代回收完整。

历史冻结候选机制结果为后端 1765、前端 119、Python/独立 PostgreSQL 727 通过，历史首轮失败保留；C/E 特性探针失败且未纳入，见 `../p2-1c-20261016T155847Z/STAGE4.md`。本轮没有重跑这些测试，也没有用确定性/静态检查宣称真实模型质量通过。

## 真实验收未完成及原因

第一次独立库启动在 V13 因默认排序规则不匹配失败；本次 r2 已显式修正该准备问题。第二次进程发出迁移完成标记后，未形成 config-copy.json、CAPTURE_GATE_PASS 或 health.json；收尾在等待 Java TERM 45 秒后记录 JAVA_TERM_INCOMPLETE。finally 中该类别覆盖了原始错误类别，现有安全记录不足以确定配置直传/后续初始化最先失败的子因，**根因未确定**。

按用户明确止损要求，不追加数据库查询、异常消息/堆栈提取、修复试验或重启来追查。仅执行本轮身份核验与资源收尾，最终状态另见 closeout.json。没有提交课程任务、冒烟或正式十次；没有 CER、速度、费用、恢复、缓存演示或真实模型任务质量结论。

工具未读取 .env、/proc/*/environ、供应商 API Key 或既有 root 密码。受控应用只沿用既有服务配置/credential 引用。所有失败记录、两个独立 schema 和 MySQL 绑定数据保留；不 push、merge 或部署。
