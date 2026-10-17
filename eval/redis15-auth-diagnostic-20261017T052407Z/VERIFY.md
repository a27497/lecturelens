# 安全证据与复核

基线提交：53fd50a。本轮只新增此诊断目录，不改业务实现、冻结候选及历史证据。

## 实际执行

从项目根目录以 dev 执行，真实认证进程仅运行一次：

```bash
nohup timeout 75s python3 scripts/dev/run_check.py --name redis15-auth-live-20261017T052407Z --cwd /home/dev/projects/lecturelens --timeout 55 -- python3 -B eval/redis15-auth-diagnostic-20261017T052407Z/diagnose.py > eval/redis15-auth-diagnostic-20261017T052407Z/diagnostic-launch.log 2>&1 < /dev/null
```

此命令是已执行记录，**不是再次执行的许可**。运行配置只由该短时进程中的选择性流式投影读取；仅提取 REDIS_HOST、REDIS_PORT、REDIS_PASSWORD，其余值跳过解码/存储。不访问其他业务配置，不使用其他身份或目标。核心转储关闭，异常仅固定码，无 traceback 或配置值。

命令计数来自 `redis-metadata.json`：AUTH=1、SELECT=1（固定 DB 15）、DBSIZE=6、SCAN=3、TYPE=36、TTL=36。未用 INFO，因历史没有实例 run_id 可比，且连接配置与固定实际对端已匹配。未发送值读取或数据修改命令。

## 结果文件

- `redis-metadata.json`：三轮完整遍历、去重、集合比较、每轮逐键 TYPE/TTL、安全 HMAC 标识及授权匹配；时间均来自实际采样。它不是原子快照。
- `provenance.json`：离线核对归档文件名及内部 task[0].id，不访问 Redis/运行配置；归档记录 SHA256 可与既有文件离线复核。
- `key-inventory.json`：合并前述记录得到完整安全集合及逐键三轮 TTL；不是新增测量。
- `before.json` / `after.json`：磁盘实测、保护文件哈希、在线服务身份、原有未提交文件 stat 及临时 unit/端口安全状态。
- `checks.json`：每次新检查的原始终态记录/日志位置、安全终态投影和日志 SHA256；*.log 是对应安全输出的副本。所有 cleanup.complete=true、remaining=[]。

逐键 key 标识为进程内随机密钥的 HMAC-SHA256，故能在本轮三次扫描及离线证据间关联，无法跨进程复算。归档路径仅保留组名与文件哈希，避免在本证据中输出可还原原始 key 的任务 ID 文件名。

## 离线验证

首次合成检查 6/6 通过，真实诊断 SUCCEEDED。首次归属投影 FAILED/ARCHIVE_TASK_SHAPE（原记录 task 是 SQL 数组）；日志 `provenance_initial.log` 保留。修正仅限本轮离线诊断工具，第二次投影 SUCCEEDED。最终 7/7 合成检查通过，原始日志见 checks.json，未重跑无关全量测试。

最终合成检查命令：

```bash
nohup timeout 35s python3 scripts/dev/run_check.py --name redis15-auth-offline-v2-20261017T052407Z --cwd /home/dev/projects/lecturelens --timeout 15 -- python3 -B eval/redis15-auth-diagnostic-20261017T052407Z/test_diagnose.py > eval/redis15-auth-diagnostic-20261017T052407Z/offline-v2-launch.log 2>&1 < /dev/null
```

离线归属投影命令（不再次读取凭据/连接 Redis）：

```bash
nohup timeout 35s python3 scripts/dev/run_check.py --name redis15-provenance-v2-20261017T052407Z --cwd /home/dev/projects/lecturelens --timeout 15 -- python3 -B eval/redis15-auth-diagnostic-20261017T052407Z/provenance.py > eval/redis15-auth-diagnostic-20261017T052407Z/provenance-v2-launch.log 2>&1 < /dev/null
```

结果文件使用独占创建，原始证据和 supervisor 名称不得覆盖复用。今后离线重放应使用新的证据目录及检查名称；不得为重放本命令而重新认证。

## 数字的离线复核

```python
import collections, json
from pathlib import Path
p = Path('eval/redis15-auth-diagnostic-20261017T052407Z')
r = json.loads((p/'redis-metadata.json').read_text())
assert len(r['scans']) == 3
for s in r['scans']:
    assert s['complete'] and s['dbsize_before'] == s['dbsize_after'] == s['unique_count'] == 12
    assert s['duplicates'] == 0 and s['pages'] == 1
    assert len({k['id'] for k in s['keys']}) == 12
    assert sum(k['authorized_history_match'] for k in s['keys']) == 1
    assert all(k['type'] == 'string' and k['ttl_seconds'] > 0 for k in s['keys'])
    print(min(k['ttl_seconds'] for k in s['keys']), max(k['ttl_seconds'] for k in s['keys']))
sets = [{k['id'] for k in s['keys']} for s in r['scans']]
assert sets[0] == sets[1] == sets[2]
proof = json.loads((p/'provenance.json').read_text())
assert len(proof['entries']) == 12
assert all(k['ownership'] == 'ARCHIVED_ISOLATED_TASK_IDENTIFIER_CONFIRMED' for k in proof['entries'])
print(collections.Counter(e['group'] for k in proof['entries'] for e in k['evidence']))
```

历史门禁精确分支未测；未将本轮 12 个键称为旧时快照。Redis value、账号/写入进程归属与真实供应商行为未测。

文件哈希复核：在此目录执行 `sha256sum -c SHA256SUMS`。
