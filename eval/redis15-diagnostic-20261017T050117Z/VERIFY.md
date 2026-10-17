# 证据与复核

- 基线 HEAD：b36af06；所有本轮新增文件仅位于本目录，不改业务代码或冻结证据。
- `before.json` / `after.json`：保护文件 SHA256、在线服务 PID/start 时间、临时 unit 不存在、磁盘门禁。后者记录全部保护文件匹配及在线身份未变。
- `redis-metadata.json`：真实只读尝试，2026-10-17T05:01:50.410347+00:00 至 05:01:50.413234+00:00；仅发送一次 SELECT 15，收到固定分类 REDIS_NOAUTH。空 scans 表示未测，不表示空库。
- `scan_metadata.py`：本轮新建、无凭据路径的元数据采集器。只允许 SELECT 15 / DBSIZE / SCAN / TYPE / TTL；不加载运行凭据；错误仅输出固定码。连接关闭后不留后台进程。
- `check_gate_offline.py`：只从原脚本 AST 提取 redis_gate，不导入或执行原适配器其他代码，使用合成 RESP。读取旧授权 key 仅为内存比较，不输出原始 key。
- `offline-gate-results.json`：7 个合成场景的实际结果；`offline-terminal.json` 保存 supervisor 终态安全投影。
- 原始检查日志：`.data/dev-checks/redis15-offline-20261017T050117Z/output.log`；原始进程终态：同目录 `run.json`。本目录的 probe.log/offline-runner.log 为安全命令输出。

历史依据（只做必要字段投影）：

1. `.data/p2-1-pipeline-20261016T073754Z/redis15-deployment-preflight.json`
2. `.data/p2-1b-pipeline-20261016T122904Z/redis15-deployment-preflight.json`
3. `eval/p2-1b-pipeline-20261016T122904Z/redis-reuse-authorization.json`
4. `eval/p2-1c-run-20261016T191343Z/runtime_service.py:145` 与 `closeout-service.json`

本轮执行命令（项目根目录；输出文件使用独占创建，禁止覆盖原证据）：

```bash
nohup timeout 55s python3 eval/redis15-diagnostic-20261017T050117Z/scan_metadata.py > eval/redis15-diagnostic-20261017T050117Z/probe.log 2>&1
nohup timeout 35s python3 scripts/dev/run_check.py --name redis15-offline-20261017T050117Z --cwd /home/dev/projects/lecturelens --timeout 15 -- python3 eval/redis15-diagnostic-20261017T050117Z/check_gate_offline.py > eval/redis15-diagnostic-20261017T050117Z/offline-runner.log 2>&1 < /dev/null
```

不应直接重跑真实探针：已到认证授权边界。离线复核与真实键集合、供应商行为及 P2-1c 验收无关，不运行其他回归或服务栈。若今后重新进行离线复核，应复制到独立的新证据目录并使用新的 supervisor 名称，保留原始结果。

哈希复核（在本目录执行）：`sha256sum -c SHA256SUMS`。
