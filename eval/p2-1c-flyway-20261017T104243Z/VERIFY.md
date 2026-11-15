# 第二次启动的命令与证据

最终状态：FAILED/FROZEN，health 未达到 UP。本目录为独立新记录，前两轮证据保持原样。以下均为实际执行历史，**不得据此重跑 Java 或继续排障**。

## 新库准备、边界检查与编译

从 `/home/dev/projects/lecturelens`：

```bash
nohup timeout --kill-after=10s 90s python3 scripts/dev/run_check.py --name p21c-r2-dependencies-20261017T104243Z --cwd /home/dev/projects/lecturelens --timeout 65 -- /home/dev/projects/lecturelens/.data/p2-1-pipeline-20261016T073754Z/venv/bin/python3 -B eval/p2-1c-flyway-20261017T104243Z/resources.py prepare > /tmp/p21c-r2-dependencies-20261017T104243Z.log 2>&1 < /dev/null &

nohup timeout --kill-after=10s 80s python3 scripts/dev/run_check.py --name p21c-r2-compile-20261017T104243Z --cwd /home/dev/projects/lecturelens --timeout 60 -- javac -cp '.data/p2-1c-flyway-20261017T104243Z/runtime/BOOT-INF/classes:.data/p2-1c-flyway-20261017T104243Z/runtime/BOOT-INF/lib/*' -d .data/p2-1c-flyway-20261017T104243Z/extra eval/p2-1c-flyway-20261017T104243Z/P21HealthBootstrap.java > /tmp/p21c-r2-compile-20261017T104243Z.log 2>&1 < /dev/null &
```

准备脚本只通过经 ID/image/owner/挂载核验的独立容器 socket 执行新库 CREATE/GRANT；读取第一次失败 schema 的固定迁移历史作前后相等比较。不使用 root 密码，不对原演示实例执行任何写操作。脚本中完整 SQL、资源参数和前置条件供审查。

冻结 JAR 提取及边界检查使用内联 Python：校验原 JAR hash，仅提取 BOOT-INF/*；AST 编译 Python、从 AST 提取 sanitized_stream/row_hash 作合成输入检查。验证正文丢弃、严格 SQL 类别、迁移 marker、分帧 hash、排序规则位于 migrate 前、单个应用 spawn、无任务端点、无 repair/clean。范围记录在 offline-check.json；不额外启动 Java 自检。

startup-preflight.json 记录执行时源码/extra class hash、逐个提取文件与原 ZIP 的相等检查、磁盘门禁、原未跟踪文件 stat 和本任务启动计数。编译为机制检查，不是应用健康/模型质量通过。

## 第二次、也是最后一次应用启动

```bash
nohup timeout --kill-after=10s 45s sudo -n systemd-run --unit=lecturelens-p21c-health-20261017t104243z --uid=dev --gid=dev --collect --property=EnvironmentFile=/home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/system-models.env --property=LoadCredentialEncrypted=bailian-asr:/etc/credstore.encrypted/lecturelens-bailian-asr.cred --property=WorkingDirectory=/home/dev/projects/lecturelens --property=UMask=0077 --property=NoNewPrivileges=yes --property=Restart=no --property=KillMode=control-group --property=SendSIGKILL=no --property=TimeoutStopSec=60 --property=RuntimeMaxSec=300 /home/dev/projects/lecturelens/.data/p2-1-pipeline-20261016T073754Z/venv/bin/python3 -B /home/dev/projects/lecturelens/eval/p2-1c-flyway-20261017T104243Z/runtime_service.py > /tmp/p21c-r2-health-unit-20261017T104243Z.log 2>&1 < /dev/null &
```

服务管理器引用已有配置，不由工具读取 EnvironmentFile 或 credential 内容。启动器只把固定 marker/类别/SQLState/vendorCode 写入证据，原始应用 stdout/stderr 不落盘。既有 source_readonly 只选择性消费获准的 MySQL 连接字段，源端 READ ONLY，SQL 行只经内存/stdin 管道。此次没有产生配置校验成功文件，不宣称完整管道已成功。

unit-created.json 为选定 systemctl show 属性；java-identity.json 为 PID/start ticks/UID，不读取进程参数或 environ。start-permit-consumed.json 为批准的第 2 次启动，拒绝同一目录重用。

## 止损和收尾

在 closeout-service.json 出现 JAVA_TERM_INCOMPLETE 后立即写 FREEZE.md，不追加数据库查询或故障排查。随后只检查同一 Java 的 PID/start-ticks、该临时 unit 的 LoadState/MainPID，以及本轮 MySQL 的固定身份/挂载；等待 Java 自行退出，没有另发 SIGKILL。

```bash
nohup timeout --kill-after=10s 70s python3 scripts/dev/run_check.py --name p21c-r2-redis-closeout-20261017T104243Z --cwd /home/dev/projects/lecturelens --timeout 50 -- python3 -B eval/p2-1c-flyway-20261017T104243Z/resources.py stop-redis > /tmp/p21c-r2-redis-closeout-20261017T104243Z.log 2>&1 < /dev/null &
```

三个新 supervisor 均读取 run.json 确认 SUCCEEDED、cleanup.complete=true 后才收录；安全输出的 SHA256 与原 run.json 一致。

## 文件索引与 hash

- `dependencies-run.json` / `dependencies-output.txt`、`compile-run.json` / `compile-output.txt`、`redis-closeout-run.json` / `redis-closeout-output.txt`：机制检查原始终态与安全输出副本。
- `failed-schema-before.json` / `mysql-resource.json`：仅独立 MySQL 中第一轮失败历史、准备前后相等、新空库排序规则/表数/binlog 和固定资源身份。
- `redis-owner.json` / `redis-resource.json` / `redis-cleanup.json`：新实例 ID/owner、空库扫描与清理。
- `events.jsonl`：最终隔离门禁和 MIGRATIONS_COMPLETE 两个 marker；没有捕获指纹或 health 成功。
- `closeout-service.json`：原始 JAVA_TERM_INCOMPLETE/exit null；`startup-result.json`：本任务第二次失败、health 未完成、初始错误子因 UNKNOWN；不修改原始记录来补造退出码。
- `closeout.json`：Java 身份消失、unit 移除、18091 无监听、未 SIGKILL、MySQL 容器/数据保留、原未提交文件 stat 不变、冻结 JAR hash 和最终磁盘检查。
- `FREEZE.md` / `FINDINGS.md`：按止损冻结，明确已实现、机制检查与真实验收未完成边界。

本目录所有文件 SHA256 在 `SHA256SUMS`，在本目录执行 `sha256sum -c SHA256SUMS`。manifest 不包含自身。没有 health.json 或配置正文导出文件；没有把失败记录标为成功。MySQL 数据位于原第一轮 `.data/p2-1c-flyway-20261017T100358Z/mysql-data`，不纳入 Git，也不清理。
