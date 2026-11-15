# 本轮命令、结果与哈希

从 `/home/dev/projects/lecturelens` 执行。以下为实际历史，不授权再次启动 Java。工具不读取 .env、/proc/*/environ 或密钥内容。私有 `.data` 内的数据库文件、运行配置、凭据和编译依赖不纳入 Git。

## 依赖与编译

```bash
nohup timeout --kill-after=10s 200s python3 scripts/dev/run_check.py --name p21c-independent-dependencies-20261017T100358Z --cwd /home/dev/projects/lecturelens --timeout 170 -- python3 -B eval/p2-1c-flyway-20261017T100358Z/resources.py prepare > /tmp/p21c-independent-dependencies-20261017T100358Z.log 2>&1 < /dev/null &

nohup timeout --kill-after=10s 80s python3 scripts/dev/run_check.py --name p21c-health-compile-20261017T100358Z --cwd /home/dev/projects/lecturelens --timeout 60 -- javac -cp '.data/p2-1c-flyway-20261017T100358Z/runtime/BOOT-INF/classes:.data/p2-1c-flyway-20261017T100358Z/runtime/BOOT-INF/lib/*' -d .data/p2-1c-flyway-20261017T100358Z/extra eval/p2-1c-flyway-20261017T100358Z/P21HealthBootstrap.java > /tmp/p21c-health-compile-20261017T100358Z.log 2>&1 < /dev/null &
```

编译前用内联 Python 校验冻结 JAR hash，只提取 BOOT-INF/*。随后增加 Flyway 实际数据源围栏，以同一编译命令执行第二次检查，name 改为 `p21c-health-compile-final-20261017T100358Z`、输出 `/tmp/p21c-health-compile-final-20261017T100358Z.log`。两次源码/字节码以启动前记录为最终身份，不把首次编译当作最终源码的验证。

Python AST 的内联合成检查验证日志正文排除、严格 SQL 类别解析、迁移 marker、行 hash 分帧、单个应用 spawn 和无任务端点。`offline-check.json` 记录检查范围；没有额外启动 Java 自检。

`startup-preflight.json` 记录最终源码/extra class SHA256、冻结 JAR SHA256、所有提取文件与 ZIP 原字节逐一相等、启动计数 0 及磁盘门禁。配置引用仅用 stat/test 检查存在性：普通 dev 无权 stat 加密 credential 的父目录，改用已获准 sudo 仅 test -f 后通过，未读取内容；没有构成服务启动阻塞。

## 唯一应用启动

```bash
nohup timeout --kill-after=10s 45s sudo -n systemd-run --unit=lecturelens-p21c-health-20261017t100358z --uid=dev --gid=dev --collect --property=EnvironmentFile=/home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/system-models.env --property=LoadCredentialEncrypted=bailian-asr:/etc/credstore.encrypted/lecturelens-bailian-asr.cred --property=WorkingDirectory=/home/dev/projects/lecturelens --property=UMask=0077 --property=NoNewPrivileges=yes --property=Restart=no --property=KillMode=control-group --property=SendSIGKILL=no --property=TimeoutStopSec=60 --property=RuntimeMaxSec=300 /home/dev/projects/lecturelens/.data/p2-1-pipeline-20261016T073754Z/venv/bin/python3 -B /home/dev/projects/lecturelens/eval/p2-1c-flyway-20261017T100358Z/runtime_service.py > /tmp/p21c-health-unit-20261017T100358Z.log 2>&1 < /dev/null &
```

unit-created.json 保存选定 systemctl show 属性；没有读取环境属性、EnvironmentFile 内容或原始应用 journal。应用 stdout/stderr 仅经过固定 marker/SQLState/vendorCode 白名单保留，其他行不落盘。start-permit-consumed.json 拒绝重复启动。未使用 Java preflight/selftest/migration-only 进程，只有一次应用启动。

## 失败核查与收尾

失败后以已有新库应用账号执行短时只读事务；内联 Python 通过本目录 runtime_service.target/query，仅读取：

```sql
SET SESSION TRANSACTION READ ONLY;
START TRANSACTION READ ONLY;
SELECT version,checksum,success FROM flyway_schema_history ORDER BY installed_rank;
SELECT default_character_set_name,default_collation_name
  FROM information_schema.schemata WHERE schema_name=DATABASE();
SELECT table_name,table_collation FROM information_schema.tables
  WHERE table_schema=DATABASE() ORDER BY table_name;
SELECT table_name,column_name,column_type,character_set_name,collation_name
  FROM information_schema.columns
  WHERE table_schema=DATABASE() ORDER BY table_name,ordinal_position;
SELECT @@log_bin;
ROLLBACK;
```

结果是 `failed-migration-metadata.json`。另从冻结 JAR 只读 V13/V10 SQL，对照元数据形成 `collation-diagnosis.json`；未执行 SQL 重现、修复或 Flyway 重跑。

```bash
nohup timeout --kill-after=10s 70s python3 scripts/dev/run_check.py --name p21c-independent-redis-closeout-20261017T100358Z --cwd /home/dev/projects/lecturelens --timeout 50 -- python3 -B eval/p2-1c-flyway-20261017T100358Z/resources.py stop-redis > /tmp/p21c-independent-redis-closeout-20261017T100358Z.log 2>&1 < /dev/null &
```

## 结果索引

- dependencies/compile-initial/compile-final/redis-closeout 的 `*-run.json` 和 `*-output.txt`：原 supervisor 终态/安全输出副本，全部 SUCCEEDED，cleanup.complete=true，日志 SHA256 与原记录一致。
- mysql-owner / mysql-resource：精确容器 ID、固定镜像、owner、发布端口、限额和持久数据挂载；没有 Config.Env。
- redis-owner / redis-resource / redis-cleanup：新实例身份、两次空库扫描、删除结果。
- events / startup-causes：隔离门禁 PASS，实际 Flyway→SQL 链，HY000/3780。没有异常消息或堆栈。
- startup-result / closeout-service：FAILED/NOT_REACHED、应用启动 1、Java exit 45、未 SIGKILL、任务 0、配置复制未开始。
- closeout：Java 身份消失、unit not-found、18091 无监听、MySQL 挂载仍在且容器运行、冻结 JAR hash、磁盘门禁、第二次授权待定。

本目录所有文件 hash 在 `SHA256SUMS`；在本目录执行 `sha256sum -c SHA256SUMS`。manifest 不包含自身。没有 health.json，因为 health 未达到 UP；没有 FREEZE.md，因为尚未满足本任务止损条件。

本次元数据和适配器边界检查不替代历史应用机制测试，也不建立真实模型任务质量结论。原始失败继续保留，第二次启动须用户另行批准。
