# 首选修复与授权清单（尚未执行）

目标仅为冻结候选在 `127.0.0.1:18091` 的健康检查返回 UP。先保留旧 schema 的失败证据；新 schema、权限和 Java 启动均须用户明确批准。

## 执行顺序与前后条件

1. 每阶段检查磁盘：占用 >85% 或距 85% 不足 2 GiB 立即停止。再次核对冻结 JAR SHA256、分支及任务自有资源身份。
2. 通过用户指定的、无需读取 root 密码的既有受控管理员入口，检查新 schema 不存在，再执行下述 CREATE DATABASE；不使用 IF NOT EXISTS 接受既有内容。该入口当前尚未提供/验证，不会从 runtime.json 取 root 密码或自行探测其他身份。
3. 用该受控管理员迁移身份，仅调用冻结 JAR 的 Flyway 11.7.2 与原始 classpath:db/migration，从 V1 到 V32；validate 保持启用。迁移身份必须具有本实例 binlog 触发器创建所需权限及新 schema DDL 权限。使用其**既有权限**，不为普通应用账号新增全局 SUPER，也不 SET GLOBAL trust。旧 P21Bootstrap 的 migrate 分支硬编码旧 schema，不能原样使用；另建本轮薄迁移入口，只改变目标围栏，不改冻结 JAR、SQL 或旧 wrapper。
4. 验证成功迁移恰为 V1–V32、32 个 checksum 匹配、四张 V32 表和两个触发器全部存在。失败只记录固定 Flyway 类别、迁移版本、SQLState 和 vendorCode，不输出异常消息、SQL 参数、配置值或密文。发生失败即停止，不 repair/clean。
5. 管理员向当前已认证应用账号授予新 schema 的运行权限。下述 GRANT 模板逐个展开新 schema 的实际表名，避免数据库名中下划线的通配匹配扩大范围。账号标识仅从原应用连接的 CURRENT_USER() 在受控进程内解析，不输出；不枚举 mysql.user，不更改原有授权。迁移由独立管理员完成，普通应用账号只需读写现有表及 Flyway 历史读取，不授予全局权限。
6. 只在服务器内进行 INSERT INTO ... SELECT ...，从旧隔离 schema `lecturelens_p21_20261016` 复制 v10 所需配置。检查源 current_version=10、目标 current_version=0 且配置目标表为空（V25 自带版本 0 除外），在一致事务内复制四张配置表，设置目标 current_version=10；不返回任何密文字段，不导出 SQL dump，不由 Python/工具取出再写入。列名按目标表元数据显式展开，顺序保持父版本、provider、model、binding 约束。复制后数据库内比较版本/行数/内容相等布尔值，应用入口继续执行原 v10/环境指纹门禁。不改模型绑定。仅健康启动不需要复制课程、媒体或待执行任务。
7. 恢复此前独立 Redis 方案：固定历史镜像、新 owner label/新实例 ID、127.0.0.1:33318、DB 15、无持久卷、禁持久化，完整空库校验。只操作本轮创建且 ID/owner 一致的实例。
8. **应用启动前再次停下确认。** 创建本轮 health-only 适配器，沿用既有受控配置引用，仅由受控应用进程消费配置；Codex 工具不读 .env/Key。冻结 JAR、模型 v10/指纹、独立 Redis、隔离 topic、cache OFF、C/E=false、预算与授权围栏保留，仅将 schema 围栏改为新目标。移除课程提交和媒体验收分支。先检查任务/outbox 为空，然后启动一次 Spring 应用；HTTP 只访问 health。正常启动时 Flyway validate 仍执行；所有迁移应已完成。
9. 保存 health 状态、HTTP 码、检查时间及安全结果 hash；达到 UP 后完成证据并有序收尾临时应用/Redis，不运行课程任务、冒烟或十次验收。保留新 schema 与迁移记录供审查；不自动 DROP DATABASE。

迁移专用 JVM 不启动 Spring/HTTP，但也属于 Java 进程，**启动前同样单独停下确认**；预计一份迁移进程加一次应用进程，至多两次。用户明确批准某次启动后才执行该次；本文件和建库批准不自动授权后续启动。不能为了自检或补日志额外启动 Java。

## 需批准的 SQL 模板

以下只供审批，不是可直接执行的脚本；账户/表名占位符由受控入口在内存中解析并严格引用。

```sql
CREATE DATABASE `lecturelens_p21c_20261017`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;

-- V1–V32 由冻结 Flyway 执行，不手工重写 SQL，不复制失败历史。
-- 完成迁移后，对新 schema 实际表逐表授予应用运行权限：
GRANT SELECT, INSERT, UPDATE, DELETE
  ON `lecturelens_p21c_20261017`.`<migrated_table>`
  TO <current_isolated_account>;

-- 后续仅在库内、一致事务中，显式展开列名：
START TRANSACTION;
INSERT INTO `lecturelens_p21c_20261017`.`system_model_config_version` (<columns>)
  SELECT <columns> FROM `lecturelens_p21_20261016`.`system_model_config_version`
  WHERE version > 0 AND version <= 10 ORDER BY version;
INSERT INTO `lecturelens_p21c_20261017`.`system_model_provider` (<columns>)
  SELECT <columns> FROM `lecturelens_p21_20261016`.`system_model_provider`;
INSERT INTO `lecturelens_p21c_20261017`.`system_model` (<columns>)
  SELECT <columns> FROM `lecturelens_p21_20261016`.`system_model`;
INSERT INTO `lecturelens_p21c_20261017`.`system_model_binding` (<columns>)
  SELECT <columns> FROM `lecturelens_p21_20261016`.`system_model_binding`;
UPDATE `lecturelens_p21c_20261017`.`system_model_config_state`
  SET current_version = 10 WHERE id = 1 AND current_version = 0;
-- 提交前仅检查预期行数、版本及数据库内相等布尔值；不返回数据正文。
COMMIT;
```

源/目标不满足前置条件、管理员入口不能满足既定密码边界或任一操作权限不足时停止；不自动补其他权限、修改全局参数或改用其他方案。新 schema 迁移失败时保留失败状态供审查；不清理历史以制造成功。

## 本次一次列明的授权需求

- 允许创建上述全新 schema，并指定不读取 root 密码的既有管理员执行入口；也可由用户在其受控管理员会话完成准备。
- 允许该入口仅针对新 schema 执行冻结 Flyway 迁移、表级运行授权和上述库内 v10 复制；不得导出密文或写旧 schema。无需向应用账号授予全局 SUPER。
- 允许按上述既有方案重建本轮独立 Redis、准备 health-only 适配器及本轮临时 unit，沿用受控配置引用。
- 迁移 Java、应用 Java **每次实际启动前分别确认**；本轮尚未使用任何启动次数。本次批准建库/准备不能解释为以后自动重试。

第二次修复后启动仍失败、出现新的非 Flyway 环境阻塞、或本任务累计超过一个工作日时，立即终止排障并写 FREEZE.md，分别列出已实现内容、历史机制结果及真实验收未完成原因。磁盘门禁触发也立即停止。当前仅完成只读核查，不以等待授权或已知迁移权限需求触发新的失败结论。
