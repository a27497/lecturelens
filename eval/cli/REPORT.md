# LectureLens CLI 本地验收

基线 `86725f488cc91f08f06fd2c0366ae2a4f3f1979c`，实现 `d3d0abf69a6c14ec071988e582e764ac73d7ddea`。[CLI 使用及管理员设置](../../docs/EVAL_CLI.md)覆盖命令、输入与权限。真实生成与付费评审请求均为 **0**。

| 审计到的重复能力 | 统一方式 |
| --- | --- |
| 参数入口、唯一运行目录、状态、退出码、报告与评审文件交接 | uv 安装的 `ll eval` 与实验适配器 |
| 后台进程、超时、取消、后代清理、环境过滤 | 离线复用 `scripts/dev/run_check.py`，受控真实模式由 systemd 监管 |
| 课程准备、冻结验证、Java 网关与 Mock HTTP | 复用冻结 E3 harness，移除 CLI 对其他 worktree 的 Python/JAR 路径依赖 |
| 费用、授权位置、未知发送停止、重启恢复与数据库外标记 | 复用 E3 PostgreSQL 门禁及外部标记，首次可用收据的上限为 USD 3.19488，阶段仍为 USD 10 和 16 次生成 |
| 独立 AI 评审输入、未决停止 | 导入两份与私有包摘要绑定的结果，使用原评审规则 |

当前主机为 systemd 255。开发账号具备免密 sudo、Docker 和 LXD 权限。在此主机存放持久真实密钥不满足隔离要求。模板只供管理员在独立受控执行机安装。探针仅加载合成数据，验证了只读凭据挂载、服务 UID ACL 与 root 组元数据。当前主机真实入口拒绝码为 `2`。管理员部署后的端到端真实启动与外部独立评审仍待验证；开发集复测保留既有 E3 同阶段流程。

## 退出码与证据

| 本地记录 | 退出码 | 结果 |
| --- | ---: | --- |
| `cli-uv-sync`、`cli-static-final` | 0 / 0 | uv 离线安装、lock 校验、wheel 中的 `ll` 入口、Ruff、冻结清单、评审包测试与 unit 样例语法 |
| `cli-python-final` | 0 | 58 项 CLI/E3 测试，含真实隔离 PostgreSQL、授权/凭据负例和不可覆盖评审导入 |
| `cli-supervisor-ram` | 0 | 原监督器 14 项测试，字节相同的测试副本 |
| `cli-systemd-acl` | 0 | 合成凭据临时探针，运行后回收 |
| `integration-preflight` | 0 | 4 课程，9 FULL、1 EXPECTED_GAP，0 模型请求 |
| `committed-e3` | 0 | 固定提交下的跨服务 Mock HTTP、一次模拟结算、双向 wire 哈希、CLI 报告与清理 |
| `cli-live-denied`、`disk-gate` | 2 / 88 | 本机真实入口拒绝，默认监督器保留磁盘门禁 |
| `integration-run`、`cli-systemd-synthetic` | 1 / 1 | 初次导入路径和 ACL 模式假设失败，修正后复验 |
| `cli-supervisor-regression` | 1 | 原测试在满载根文件系统收到子进程磁盘拒绝 `88`，RAM 复验通过 |

原始监督器记录位于 `.data/ll-cli-checks/`。CLI 新运行记录位于 `.data/ll-eval/e3/`。冻结 E1/E2/E3 runner、数据与报告继续保留原路径。已提交的改动位于 CLI、适配器与配置样例层，跨服务检查使用原 Java 网关。
