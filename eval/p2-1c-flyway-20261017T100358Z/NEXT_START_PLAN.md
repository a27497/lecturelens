# 第二次应用启动前的待批准修复

状态：仅方案，未执行。原 `lecturelens_p21c_20261017` 的 V13 失败历史、对象、container ID 和绑定数据目录全部保留；不 repair/clean，不删除或改写迁移历史，不修改冻结 SQL/checksum/JAR。

建议在**同一个本轮自有独立 MySQL** 中创建全新空 schema `lecturelens_p21c_20261017_r2`，明确默认排序规则。新名字需要用户批准；没有在旧演示实例上执行此方案的权限。

```sql
CREATE DATABASE `lecturelens_p21c_20261017_r2`
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
GRANT ALL PRIVILEGES ON `lecturelens_p21c_20261017_r2`.*
  TO 'p21c_app'@'%';
```

这两条只由已核实 container ID/owner/image 的独立容器内空密码 root socket 执行，不读取任何 root 密码；不读取/修改旧实例。先验证新名字不存在，执行后核对默认 charset/collation 和表数为零。已有应用账号密码继续只在私有受控路径内消费，不输出。

第二次运行另建新的证据/私有运行目录，不覆盖本轮源码、compiled class、日志、permit-consumed 或失败记录。复用现有独立 MySQL 的精确 ID/镜像/数据挂载；新旧 schema 共存。重建一份新 owner label 的独立 Redis，按原方案校验空库。

隔离适配器唯一数据库目标改为新 schema，并在启动前与实际 Flyway datasource 围栏中验证 `utf8mb4_unicode_ci`。**仅再启动一个应用 JVM**，继续由应用自身 Flyway migrate V1–V32；validate 保持启用，禁止 baseline/repair/clean。迁移后才执行此前已批准的旧隔离账号只读导出 → stdin 管道直传 → 新库导入；没有明文 SQL 文件、输出行内容或工具层供应商 Key 读取。导入只输出版本、行数和内容 hash 相等布尔值。

配置直传完成后继续 v10/环境指纹门禁及 health。只保存 health 的 HTTP 码、UP 状态、时间和响应 hash，不提交课程任务、不跑冒烟/十次；结束时有序收尾 Java/Redis，保留 MySQL 数据。若这次启动仍失败，或出现新的非 Flyway 环境阻塞，立即写 FREEZE.md 并停止排障。

需要用户明确批准：上述新 schema/授权，以及**本任务第二次应用 Java 启动一次**。先前批准的首次启动次数已消耗，不能自动复用。
