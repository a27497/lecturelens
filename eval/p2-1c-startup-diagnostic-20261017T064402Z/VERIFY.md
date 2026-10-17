# 证据、执行与复核

基线 b459020。所有本轮新文件位于此目录；原候选及历史证据保持不变。

## 证据索引

- before.json：冻结身份、104 份保护文件哈希、在线身份、原未提交文件 stat、磁盘门禁。
- environment-delta.json / redis-owner.json / redis-resource.json：本轮新 Redis、owner label、固定镜像身份、无共享卷/持久化、空库及实例 run_id 哈希。
- offline-check.json：没有提交函数、冻结选项全部保留、原 bootstrap / 隔离监听器字节不变、安全过滤及两个 Java selftest PASS；保存**启动时**源码哈希。
- startup-preflight.json / source-gates.json：dev、引用路径存在、磁盘、编译类哈希、schema/version、无待执行任务/outbox、五课身份及 Redis 两轮完整空库复核。
- bootstrap-preflight.json / events.jsonl：原 preflight 退出 0；完整应用也通过最终隔离和原捕获门禁。
- startup-causes.jsonl：实际四层固定类别；不含异常消息、堆栈、原始类名、路径、配置值或正文。SQL 字段本轮不存在。
- startup-result.json / closeout-service.json：FAILED / APPLICATION_START_FAILED、wrapper exit 45、提交 0、无 SIGKILL。
- java-identity.json / unit-created.json / unit-journal-safe.json：本轮身份、唯一 InvocationID 和固定退出消息的 UID/GID/PID/时间投影，不保存其他 journal 内容。
- migration-artifact-comparison.json：冻结 SQL 与旧提取归档的 SHA256 比较，V1–V31 相同、仅新增 V32；不声称读取了数据库历史。
- offline-migrations.json：冻结 Flyway 库的 32 个 checksum / 解析结果，仅离线解析，未连接数据库或启动应用。
- checks.json：离线检查原始 supervisor 终态、日志位置和哈希；本目录对应 *.log 是安全输出副本，均 SUCCEEDED / cleanup.complete=true。
- redis-cleanup.json / resource-cleanup.json / closeout.json：自有资源清理、原 Java 消失、unit 不存在、端口无监听和保护检查。安全私有日志的文件名/SHA256 记录在 resource-cleanup.json，同名 .data 目录保留原文件。

FLYWAY 分类合并了 FlywayException / FlywayValidateException。此粒度不能确认具体迁移版本或子因；没有用未保存的异常消息作推断。

## 实际命令

以下是执行历史，**不能作为重跑启动的授权**。均从项目根目录运行。

```bash
nohup timeout 60s javac -cp '.data/p2-1c-startup-diagnostic-20261017T064402Z/runtime/BOOT-INF/classes:.data/p2-1c-startup-diagnostic-20261017T064402Z/runtime/BOOT-INF/lib/*' -d .data/p2-1c-startup-diagnostic-20261017T064402Z/extra eval/p2-1c-startup-diagnostic-20261017T064402Z/P21Bootstrap.java eval/p2-1c-startup-diagnostic-20261017T064402Z/P21IsolationGate.java eval/p2-1c-startup-diagnostic-20261017T064402Z/P21StartupDiagnostics.java > .data/p2-1c-startup-diagnostic-20261017T064402Z/compile.log 2>&1 < /dev/null
nohup timeout 60s python3 scripts/dev/run_check.py --name p21c-startup-offline-20261017T064402Z --cwd /home/dev/projects/lecturelens --timeout 40 -- python3 -B eval/p2-1c-startup-diagnostic-20261017T064402Z/offline_check.py > .data/p2-1c-startup-diagnostic-20261017T064402Z/offline-launch.log 2>&1 < /dev/null
nohup timeout 60s python3 eval/p2-1c-startup-diagnostic-20261017T064402Z/redis_resource.py create > .data/p2-1c-startup-diagnostic-20261017T064402Z/redis-create.log 2>&1 < /dev/null
nohup timeout 45s sudo -n systemd-run --unit=lecturelens-p21c-worker-20261017 --uid=dev --gid=dev --collect --property=EnvironmentFile=/home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/system-models.env --property=LoadCredentialEncrypted=bailian-asr:/etc/credstore.encrypted/lecturelens-bailian-asr.cred --property=WorkingDirectory=/home/dev/projects/lecturelens --property=UMask=0077 --property=NoNewPrivileges=yes --property=Restart=no --property=KillMode=control-group --property=SendSIGKILL=no --property=TimeoutStopSec=60 --property=RuntimeMaxSec=300 /home/dev/projects/lecturelens/.data/p2-1-pipeline-20261016T073754Z/venv/bin/python3 -B /home/dev/projects/lecturelens/eval/p2-1c-startup-diagnostic-20261017T064402Z/runtime_service.py > .data/p2-1c-startup-diagnostic-20261017T064402Z/systemd-create.log 2>&1 < /dev/null
nohup timeout 60s python3 eval/p2-1c-startup-diagnostic-20261017T064402Z/redis_resource.py cleanup > .data/p2-1c-startup-diagnostic-20261017T064402Z/redis-cleanup.log 2>&1 < /dev/null
```

启动后仅执行离线迁移解析，没有重复启动 Spring / 冻结应用：

```bash
nohup timeout 60s javac -cp '.data/p2-1c-startup-diagnostic-20261017T064402Z/extra:.data/p2-1c-startup-diagnostic-20261017T064402Z/runtime/BOOT-INF/classes:.data/p2-1c-startup-diagnostic-20261017T064402Z/runtime/BOOT-INF/lib/*' -d .data/p2-1c-startup-diagnostic-20261017T064402Z/extra eval/p2-1c-startup-diagnostic-20261017T064402Z/FrozenMigrationCheck.java > .data/p2-1c-startup-diagnostic-20261017T064402Z/migration-check-compile.log 2>&1 < /dev/null
nohup timeout 60s python3 scripts/dev/run_check.py --name p21c-migration-parser-20261017T064402Z --cwd /home/dev/projects/lecturelens --timeout 40 -- python3 -B eval/p2-1c-startup-diagnostic-20261017T064402Z/check_migrations.py > .data/p2-1c-startup-diagnostic-20261017T064402Z/migration-parser-launch.log 2>&1 < /dev/null
```

resource-cleanup.json 中的私有运行目录已删除，不能直接复用。复核以下数字不读取凭据、不连接任何服务：

```python
import json
from pathlib import Path
p = Path('eval/p2-1c-startup-diagnostic-20261017T064402Z')
causes = [json.loads(line) for line in (p/'startup-causes.jsonl').read_text().splitlines()]
assert [c['kind'] for c in causes] == ['DEPENDENCY', 'DEPENDENCY', 'BEAN_CREATION', 'FLYWAY']
assert all(set(c) == {'index','kind'} for c in causes)
r = json.loads((p/'startup-result.json').read_text())
assert r['result'] == 'FAILED' and r['java_exit'] == 45 and r['course_tasks_submitted'] == 0
assert len(r['markers']) == 2
pre = json.loads((p/'bootstrap-preflight.json').read_text())
assert pre['exit_code'] == 0
parser = json.loads((p/'offline-migrations.json').read_text())
assert len(parser['resources']) == 32 and all(v['parser_passed'] for v in parser['resources'])
assert not parser['database_connected'] and not parser['spring_application_started']
comparison = json.loads((p/'migration-artifact-comparison.json').read_text())
assert comparison['changed_existing_versions'] == [] and comparison['new_versions'] == ['V32']
after = json.loads((p/'closeout.json').read_text())
assert after['protected_file_count'] == 104 and after['protected_files_all_unchanged']
assert after['frozen_jar_unchanged'] and after['untracked_stat_unchanged'] and after['live_identity_unchanged']
assert after['owned_runtime_listeners_absent']
d = after['disk']
assert d['usage_percent'] == 100*d['used_bytes']/(d['used_bytes']+d['available_bytes'])
assert d['margin_to_85_bytes'] == .85*(d['used_bytes']+d['available_bytes'])-d['used_bytes']
```

在本目录执行 `sha256sum -c SHA256SUMS` 核对文件。业务代码、原冻结 JAR、原 bootstrap 和原历史证据没有修改；本轮仅诊断，不产生真实课程验收统计。
