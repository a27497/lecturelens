# P2-1c Flyway 只读核查

状态：核查完成，修复与 Java 启动等待用户授权。本任务基点 `4be8593fbec5ea87ec900aff4714ff7432692b63`，分支 `codex/p14-system-model-management`。冻结候选仍为 `dcc4dda753afd89fafcc2375eaf3cd942dba4b02`，JAR SHA256 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`。

## 实测结果

2026-10-17T09:38:30Z，以 dev 身份、既有非 root 应用账号连接强制指定的 `lecturelens_p21_20261016`。事务为 READ ONLY；未连接配置中的原业务 schema，未执行写入、DDL、GRANT、repair、clean 或 Java 启动。

| 核查项 | 结果 |
| --- | --- |
| DATABASE() 与固定隔离目标匹配 | true |
| V1–V31 | 31 条成功；全部 checksum 与冻结 Flyway 离线结果一致 |
| V32 | installed_rank=32，success=false，checksum=-749564353，与冻结结果一致 |
| asr_scheduler_state | 存在 |
| asr_chunk_checkpoint / asr_scheduler_event / asr_result_cache | 均不存在 |
| asr_state_immutable_input / asr_chunk_immutable_input | 当前账号元数据均不可见；该账号具有 TRIGGER 权限 |
| 全局 GRANT 权限名 | USAGE |
| @@log_bin | 1 |
| @@log_bin_trust_function_creators | 0 |

当前 schema GRANT 权限名：ALTER、ALTER ROUTINE、CREATE、CREATE ROUTINE、CREATE TEMPORARY TABLES、CREATE VIEW、DELETE、DROP、EVENT、EXECUTE、INDEX、INSERT、LOCK TABLES、REFERENCES、SELECT、SHOW VIEW、TRIGGER、UPDATE。没有输出账号、Host、连接配置或完整 GRANT 语句。明细见 `mysql-metadata.json`。

## 根因与证据边界

**已确定：旧隔离 schema 有 V32 失败历史及部分落地对象；不是 V1–V31 checksum 漂移。** 这解释了其不适合作为后续正常迁移的起点；本轮不修改该历史或残留对象。

**具体 SQL 失败子因仍未确定；首个触发器创建权限不足是高度吻合的假设。** 从冻结 JAR 单独读取并核对 V32 SQL 的 SHA256 后，语句顺序为第一张表、首个触发器、其余三张表、第二个触发器。现状恰停在第一张表之后。binlog=1、trust=0、schema TRIGGER 存在且没有全局 SUPER，与 MySQL 对触发器创建的额外权限要求相符。原启动未保存 SQLState/vendorCode，不能将推断写为实际收到 1419，也不能仅凭对象状态排除其他 SQL 错误。

MySQL 官方依据：[Stored Program Binary Logging](https://dev.mysql.com/doc/refman/8.0/en/stored-programs-logging.html)。该文档描述 binlog 下存储程序及触发器的额外创建权限；它不能代替本实例未捕获的错误记录。

## 修复方向

首选仍为全新空 schema `lecturelens_p21c_20261017`，使用冻结 JAR 内 Flyway/SQL 从 V1 迁移到 V32，再执行库内受控 INSERT/SELECT 复制系统模型配置 v10。**仅新建 schema 并补 schema 级权限，不足以排除触发器权限阻塞。** 因此首选流程需要一个不读取 root 密码的受控管理员迁移入口；应用运行账号不新增全局 SUPER，不改服务器全局 trust 参数。

具体顺序、SQL 模板、管理员入口缺口、权限与启动边界见 `REPAIR_PLAN.md`。当前账号没有全局建库/转授权能力；本轮没有试探写权限或寻找管理员密码。未证明首选方案不可行，暂不提出其他修复路线。

## 本轮检查与验收边界

- 合成配置选择器自检通过；只反序列化获准的三个 MySQL 字段，其他值仅作语法跳过，不解码、保留或输出。没有整体加载 runtime 配置、读取 .env、/proc/*/environ、供应商 Key、root 密码或业务密文。
- 首次命令使用系统 Python，在 main 的首条 import pymysql 处失败，尚未读取 runtime 配置或连接数据库。保留 FAILED 记录。改用既有 venv 后唯一数据库诊断成功，两个 supervisor 均完成后代回收。这是诊断命令解释器选择错误，现有依赖可用，没有发现新的服务环境阻塞。
- 本轮没有修改应用代码或重跑应用全量测试。历史机制结果为后端 1765、前端 119、Python/独立 PostgreSQL 727 全部通过，原始失败继续保留，见 `../p2-1c-20261016T155847Z/STAGE4.md`。C/E 特性探针失败且未纳入冻结候选。
- 本任务 Java 启动 0，课程任务 0，供应商调用 0；health 尚未验证，真实课程验收未完成。未触发本任务止损条件，未生成 FREEZE.md；等待授权不记为成功或止损。
- 历史 `redis-cleanup.json` 明确上一独立 Redis 已停止并删除。方案复用其镜像/隔离配置，在获批后创建本轮自有实例，不复用已删除的 container ID，也不接触共享 Redis。
- 原未跟踪的 `eval/baseline-deepseek-20261015T185735Z/DIAGNOSIS.md` 保留；本轮仅新增此目录，未 push、merge 或部署。
