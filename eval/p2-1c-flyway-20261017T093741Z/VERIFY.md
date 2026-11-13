# 命令与证据

本轮只读核查，Java 启动 0。所有命令从 `/home/dev/projects/lecturelens` 执行。实际修复/启动等待 `REPAIR_PLAN.md` 中的授权；下列历史命令不授权重新查询或启动服务。

```bash
pwd
git status --short
git branch --show-current
git rev-parse HEAD
df -B1 /home/dev/projects/lecturelens
python3 -B eval/p2-1c-flyway-20261017T093741Z/mysql_metadata.py selftest

# 首轮：解释器缺少 pymysql，在连接/读取配置前退出；保留 FAILED。
nohup timeout --kill-after=10s 80s python3 scripts/dev/run_check.py --name p21c-flyway-metadata-20261017T093741Z --cwd /home/dev/projects/lecturelens --timeout 60 -- python3 -B eval/p2-1c-flyway-20261017T093741Z/mysql_metadata.py > /tmp/p21c-flyway-metadata-20261017T093741Z.log 2>&1 < /dev/null &

# 复核本地模块存在性后，使用已有虚拟环境；没有安装依赖或改服务环境。
nohup timeout --kill-after=10s 80s python3 scripts/dev/run_check.py --name p21c-flyway-metadata-venv-20261017T093741Z --cwd /home/dev/projects/lecturelens --timeout 60 -- /home/dev/projects/lecturelens/.data/p2-1-pipeline-20261016T073754Z/venv/bin/python3 -B eval/p2-1c-flyway-20261017T093741Z/mysql_metadata.py > /tmp/p21c-flyway-metadata-venv-20261017T093741Z.log 2>&1 < /dev/null &
```

逐一读取新 supervisor 的 run.json 和 output.log，确认终态及 cleanup.complete=true 后才收录安全副本。本轮没有进程需要取消，没有向既有进程或容器发信号。

## 结果文件

- `mysql-metadata.json`：唯一成功的数据库只读核查；每个已应用版本/checksum/success、与冻结 checksum 的比较、固定对象存在性、权限名、binlog 两项变量。没有业务正文/凭据。
- `initial-python-run.json` / `initial-python-output.log`：首轮 FAILED，0.104 秒，退出 1；安全输出仅 MYSQL_METADATA_STOP。离线模块检查确认系统解释器没有 pymysql，既有 venv 有该模块。
- `metadata-run.json` / `metadata-output.log`：SUCCEEDED，0.662 秒，退出 0；安全输出 MYSQL_METADATA_READONLY_PASS。
- `frozen-v32-order.json`：仅从冻结 JAR 读取指定 V32 SQL，核对候选记录中的 SHA256，记录六条 CREATE 的类型/对象顺序。没有修改、解包或重建冻结 JAR。
- `checkpoint.json`：候选/基点、执行诊断源码 hash、等待授权状态、启动/写入/任务计数及磁盘快照。
- `FINDINGS.md` / `REPAIR_PLAN.md`：已确定现象、尚未确定子因与待批准首选方案。

所有本目录结果文件的 SHA256 见 `SHA256SUMS`，在本目录运行 `sha256sum -c SHA256SUMS`。manifest 自身不纳入自身摘要。冻结 JAR hash 见 checkpoint 和 mysql-metadata 两份记录，均与原候选一致。

## 独立复算（无数据库、服务或凭据读取）

```python
import json
from pathlib import Path
p = Path('eval/p2-1c-flyway-20261017T093741Z')
r = json.loads((p/'mysql-metadata.json').read_text())
assert r['database_matches'] and r['authenticated_account_nonroot']
assert r['read_only_transaction'] and not r['writes_executed']
assert not r['spring_application_started'] and r['supplier_calls'] == 0
assert len(r['history']) == 32
assert all(x['success'] and x['frozen_checksum_matches'] for x in r['history'][:31])
assert r['history'][31]['version'] == '32'
assert not r['history'][31]['success'] and r['history'][31]['frozen_checksum_matches']
assert sum(r['v32_tables'].values()) == 1
assert not any(r['v32_triggers_visible'].values())
assert r['log_bin'] and not r['log_bin_trust_function_creators']
for name in ('initial-python-run.json', 'metadata-run.json'):
    assert json.loads((p/name).read_text())['cleanup']['complete']
```

本轮仅新增诊断与文档，没有重跑冻结候选的应用机制测试；历史 1765/119/727 通过结果与本次元数据核查分别报告。没有健康、课程任务或模型质量成功结论。未触发止损；暂不生成 FREEZE.md。
