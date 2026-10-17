# 执行、证据与复核

本轮基线 ba2a7e9；准备提交 c8c9714。旧冻结候选及历史证据不覆盖。所有新操作仅涉及本目录及同名 .data 目录、本轮新建 Redis 和指定临时 unit。

## 原始记录

- before.json：原 JAR/选项身份、95 份保护文件 SHA256、在线服务身份、原未提交文件 stat、阶段开始磁盘。
- environment-delta.json、redis-owner.json、redis-resource.json：独立实例差异、固定 image ID、container ID / owner label、无共享持久卷、server run_id 哈希及新库检查。
- instrumentation.json：原 bootstrap 源码相同、冻结参数全部存在、白名单日志过滤、编译类哈希、原 selftest 日志哈希；此文件是**真实启动时**的 instrumentation，不包括之后仅离线编译的诊断 wrapper。
- startup-preflight.json / source-gates.json：启动前磁盘、dev 身份、schema/version、待执行任务/outbox 为 0、五课媒体/字幕哈希/上传所有权及新 Redis 两次完整空库检查。
- bootstrap-preflight.json：原 Java preflight 退出 0，两项门禁 PASS；events.jsonl 还保留完整应用进程的两项 PASS。
- java-identity.json / unit-created.json：本轮 Java PID/start ticks、原 JAR 哈希、dev unit 身份和唯一 InvocationID；不采集进程环境或配置值。
- closeout-service.json：APPLICATION_START_FAILED、Java exit 1、owned_tasks=[]、used_sigkill=false。
- unit-journal-safe.json：按 InvocationID 查 journal，仅保存固定退出消息和 UID/GID/PID/时间；不复制其他 journal 消息。
- trials.jsonl：0 字节。没有提交意图、任务明细或真实供应商 usage 记录。metrics.json 显式标“未测”，不推算成功率/耗时/CER/费用。
- checks.json：两个离线 selftest 的原始 supervisor 记录与日志位置；对应安全输出在本目录 *.log。均 SUCCEEDED、cleanup.complete=true、remaining=[]。
- redis-cleanup.json / resource-cleanup.json / closeout.json：精确 owner 校验后清理新容器；unit 不存在，Java 身份消失；仅删除新私有目录；历史文件/JAR/在线身份检查及磁盘终检。

安全私有日志原始位置为 `.data/p2-1c-independent-redis-20261017T062836Z/*.log`，逐文件 SHA256 位于 resource-cleanup.json。没有保存 Java 原始 stdout/stderr、配置值、凭据或供应商响应正文。

## 实际命令

项目根目录执行；命令仅记录执行历史，**不授权直接重跑启动**。

```bash
nohup timeout 60s python3 eval/p2-1c-independent-redis-20261017T062836Z/redis_resource.py create > .data/p2-1c-independent-redis-20261017T062836Z/redis-create.log 2>&1 < /dev/null
nohup timeout 90s javac -cp '.data/p2-1c-independent-redis-20261017T062836Z/runtime/BOOT-INF/classes:.data/p2-1c-independent-redis-20261017T062836Z/runtime/BOOT-INF/lib/*' -d .data/p2-1c-independent-redis-20261017T062836Z/extra eval/p2-1c-independent-redis-20261017T062836Z/P21Bootstrap.java eval/p2-1c-independent-redis-20261017T062836Z/P21IsolationGate.java > .data/p2-1c-independent-redis-20261017T062836Z/compile.log 2>&1 < /dev/null
nohup timeout 45s sudo -n systemd-run --unit=lecturelens-p21c-worker-20261017 --uid=dev --gid=dev --collect --property=EnvironmentFile=/home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/system-models.env --property=LoadCredentialEncrypted=bailian-asr:/etc/credstore.encrypted/lecturelens-bailian-asr.cred --property=WorkingDirectory=/home/dev/projects/lecturelens --property=UMask=0077 --property=NoNewPrivileges=yes --property=Restart=no --property=KillMode=control-group --property=SendSIGKILL=no --property=TimeoutStopSec=60 --property=RuntimeMaxSec=21600 /home/dev/projects/lecturelens/.data/p2-1-pipeline-20261016T073754Z/venv/bin/python3 -B /home/dev/projects/lecturelens/eval/p2-1c-independent-redis-20261017T062836Z/runtime_service.py > .data/p2-1c-independent-redis-20261017T062836Z/systemd-create.log 2>&1 < /dev/null
nohup timeout 60s python3 eval/p2-1c-independent-redis-20261017T062836Z/redis_resource.py cleanup > .data/p2-1c-independent-redis-20261017T062836Z/redis-cleanup.log 2>&1 < /dev/null
```

原 bootstrap selftest：

```bash
nohup timeout 45s python3 scripts/dev/run_check.py --name p21c-redis-bootstrap-20261017T062836Z --cwd /home/dev/projects/lecturelens --timeout 25 -- java -Dp21.private=/home/dev/projects/lecturelens/.data/p2-1c-independent-redis-20261017T062836Z -cp '.data/p2-1c-independent-redis-20261017T062836Z/extra:.data/p2-1c-independent-redis-20261017T062836Z/runtime/BOOT-INF/classes:.data/p2-1c-independent-redis-20261017T062836Z/runtime/BOOT-INF/lib/*' com.example.courselingo.systemmodel.P21Bootstrap selftest > .data/p2-1c-independent-redis-20261017T062836Z/selftest-launch.log 2>&1 < /dev/null
```

后续提议的 wrapper 自测（真实 unit 退出后；未用于应用启动）：

```bash
nohup timeout 60s javac -cp '.data/p2-1c-independent-redis-20261017T062836Z/extra:.data/p2-1c-independent-redis-20261017T062836Z/runtime/BOOT-INF/classes:.data/p2-1c-independent-redis-20261017T062836Z/runtime/BOOT-INF/lib/*' -d .data/p2-1c-independent-redis-20261017T062836Z/extra eval/p2-1c-independent-redis-20261017T062836Z/P21StartupDiagnostics.java > .data/p2-1c-independent-redis-20261017T062836Z/diagnostics-compile.log 2>&1 < /dev/null
nohup timeout 45s python3 scripts/dev/run_check.py --name p21c-startup-diagnostics-20261017T062836Z --cwd /home/dev/projects/lecturelens --timeout 25 -- java -cp '.data/p2-1c-independent-redis-20261017T062836Z/extra:.data/p2-1c-independent-redis-20261017T062836Z/runtime/BOOT-INF/classes:.data/p2-1c-independent-redis-20261017T062836Z/runtime/BOOT-INF/lib/*' com.example.courselingo.systemmodel.P21StartupDiagnostics selftest-startup-diagnostics > .data/p2-1c-independent-redis-20261017T062836Z/diagnostics-selftest-launch.log 2>&1 < /dev/null
```

## 不出网的数字与哈希复核

```python
import json
from pathlib import Path
p = Path('eval/p2-1c-independent-redis-20261017T062836Z')
assert (p/'trials.jsonl').stat().st_size == 0
source = json.loads((p/'source-gates.json').read_text())
assert source['version'] == 10 and source['media_count'] == 5
assert source['pending_tasks'] == source['pending_outbox'] == 0
assert all(s['dbsize_before'] == s['dbsize_after'] == s['unique_count'] == 0 for s in source['redis']['scans'])
pre = json.loads((p/'bootstrap-preflight.json').read_text())
assert pre['exit_code'] == 0 and len(pre['markers']) == 2
close = json.loads((p/'closeout-service.json').read_text())
assert close['owned_tasks'] == [] and close['java_exit'] == 1 and not close['used_sigkill']
after = json.loads((p/'closeout.json').read_text())
assert after['protected_file_count'] == 95 and after['protected_files_all_unchanged']
assert after['frozen_jar_unchanged'] and after['untracked_stat_unchanged'] and after['live_identity_unchanged']
assert after['owned_runtime_listeners_absent']
d = after['disk']
assert d['usage_percent'] == 100*d['used_bytes']/(d['used_bytes']+d['available_bytes'])
assert d['margin_to_85_bytes'] == .85*(d['used_bytes']+d['available_bytes'])-d['used_bytes']
```

在本目录执行 `sha256sum -c SHA256SUMS`。原阶段 4 全量测试日志仍见旧 STAGE4.md / stage4-gates-verified.json；本轮不重跑，不将其当作真实课程验收。
