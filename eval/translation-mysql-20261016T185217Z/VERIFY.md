# MySQL 验收复现与证据

验收对象：`47de0cc` 的生产实现。临时数据库使用本地已存在的固定镜像，实际版本、容器 ID、创建时间、端口、标签、挂载和资源限额见 `mysql-created.json`、`mysql-ready.json`，清理身份与随机 schema 检查见 `mysql-cleanup.json`。

## 运行

从 `/home/dev/projects/lecturelens` 执行。本轮先核对磁盘和独立资源身份，不读取部署环境、供应商凭据或课程文本。

```bash
nohup timeout --kill-after=10s 140s \
  python3 eval/translation-mysql-20261016T185217Z/mysql_resource.py create \
  > .data/translation-mysql-20261016T185217Z/mysql-create.log 2>&1 < /dev/null &
```

脚本在容器名、端口或证据路径已存在时拒绝创建，不会接管或替换已有资源；本轮结束后也不能原名覆盖重跑。重跑时应使用新的时间戳、名称、标签和空闲端口，保留每次身份记录。

数据库就绪后实际测试命令（01 与 02 使用同一 test selector，精确命令另存 commands.json）：

```bash
SYSTEM_MODEL_TEST_JDBC_URL='jdbc:mysql://127.0.0.1:33318/lecturelens_translation_test?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC' \
SYSTEM_MODEL_TEST_MYSQL_USER=root SYSTEM_MODEL_TEST_MYSQL_PASSWORD='' \
nohup timeout --kill-after=10s 660s python3 scripts/dev/run_check.py \
  --name translation-mysql-02 --output-root .data/translation-mysql-20261016T185217Z \
  --cwd backend --timeout 600 -- ./mvnw -o -B \
  '-Dtest=LegacyTranslationMySqlTest,SystemModelRuntimeMySqlTest,PipelineUsageLedgerMySqlTest,TranslationCheckpointMySqlTest,PipelineResumeMySqlTest' \
  test > .data/translation-mysql-20261016T185217Z/mysql-02-launcher.log 2>&1 < /dev/null &
```

等待包装器终态，立即按该次开始时间归档新鲜 Surefire XML，避免后续测试覆盖原报告：

```bash
python3 eval/translation-mysql-20261016T185217Z/archive_check.py translation-mysql-02
```

完整 Maven 日志：`.data/translation-mysql-20261016T185217Z/<运行名>/output.log`；退出状态、磁盘门禁与进程清理：同目录 `run.json`。新鲜测试报告：`.data/translation-mysql-20261016T185217Z/<运行名>-reports/TEST-*.xml`。公开的 `<运行名>-check.json` 保存各类测试计数、退出状态、清理结果及私有记录哈希。编译失败不会被记为测试通过；01 的失败日志保留。

## 验证范围

`LegacyTranslationMySqlTest` 使用真实 MySQL、完整 Flyway 迁移、MyBatis mapper、Spring 事务代理、系统模型快照/配置存储、翻译服务、翻译步骤、调用记录步骤及任务 runner/state service。

供应商传输是直接返回合成 JSON 的函数，环境模型 fallback 会抛出 AssertionError；不发网络请求。ASR 由 `SyntheticTranscriptStep` 注入合成文本，其他媒体/资料步骤为空边界；Redis claim、进度缓存及外层调度器使用替身。此测试证明翻译数据库与任务状态协议，不能称为真实课程全链路验收。

覆盖内容：

- 正常 stop 对象成功发布；空 content/length 优先归为 TRUNCATED 并通过现有有限拆分恢复。
- MySQL 中保留失败父调用的 HTTP 200、length、OUTPUT_TRUNCATED、usage 和配置版本；成功汇总包含失败父调用及成功子调用，不把诊断再叠加为第二份费用。
- 空输出、非法 JSON、非对象 JSON 均失败，不盲重试、不发布部分结果；任务与调用记录保持失败。
- legacy 深度耗尽后停止；诊断保留每次失败的已知 usage。整体失败的 legacy 阶段摘要没有补造 usage，其已知失败调用事实仍在诊断表中；V2 则由物理调用台账累计，不能混算两者。
- MySQL trigger 注入最终全文写入失败，验证分段/全文替换和 content revision 同时回滚，旧产物不丢失；诊断独立提交，调用记录及任务进入失败，并保持数据库错误与输出错误的区分。
- 对成功/失败终态重复投递原消息，不新增模型调用、不改写调用历史。

`TranslationCheckpointMySqlTest` 新增持久调用预算、深度、未知 usage 的 token 保留额耗尽用例；重新打开 session 不增加调用或改写失败尝试。原有用例检查截断父/已完成子节点不重跑、源版本/取消栅栏及完成批次复用。

`PipelineUsageLedgerMySqlTest` 验证失败父调用和子调用都计入物理台账、汇总不重复收费、已知 usage 回填、未知 usage 不伪造。`PipelineResumeMySqlTest` 验证恢复/删除/取消及旧执行代次隔离。`SystemModelRuntimeMySqlTest` 覆盖实际 MySQL 系统模型路由、快照、无效输出与传输错误分类；未连接生产配置。

各次实测计数、最终范围与剩余边界见 SUMMARY.md；JUnit 与源码中的断言是调用数和 usage 数字的复现依据。没有重复运行上一轮与本轮无关的 311 项回归。

## 清理与保护

测试终态且报告归档后，只清理 `mysql-created.json` 中的确切 ID；脚本重新比较镜像、创建时间、标签、端口、挂载和资源限额，身份变化即停。

```bash
nohup timeout --kill-after=10s 100s \
  python3 eval/translation-mysql-20261016T185217Z/mysql_resource.py cleanup \
  > .data/translation-mysql-20261016T185217Z/mysql-cleanup.log 2>&1 < /dev/null &
```

`before.json` / `closeout.json` 比较历史证据哈希、P2-1c 冻结候选、在线服务身份及原有未提交文件元数据。该未提交 DIAGNOSIS.md 正文不读取、不提交。最终源码/证据/私有日志及报告的哈希在 SHA256SUMS 中，从仓库根目录校验：

```bash
sha256sum --check --quiet eval/translation-mysql-20261016T185217Z/SHA256SUMS
git diff --check
```

本轮不做真实供应商质量/行为判断，不对其余十次未知历史故障追加推定归因；不修改在线服务、数据库、模型绑定或 P2-1c 冻结候选。
