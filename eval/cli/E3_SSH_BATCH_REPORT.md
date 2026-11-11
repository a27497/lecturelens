# E3 开发机 SSH 批量准备验收

基线 `6e42cdde15b230ae54abae8a048aed4792564fa5`。批量实现 `f9853b64e5c0c8af90ed7e115bc44a0aab8fc433`，发送前 checkout SHA 复核为 `1c792ae8bfe7a1c9335978fc2e96cfa589660449`。

- 显式 `--live --dev-ssh --batch` 要求前台 OpenSSH 登录 TTY，操作者确认阶段后才隐藏输入。密钥由匿名管道交给 worker，且不经 argv、环境、Git 或日志。父进程和 worker 通过退出清理及父死亡信号缩短密钥驻留。此路径对同机 root 或特权 Codex 没有强隔离。systemd 默认入口继续使用原授权方式。
- 按原 10 个位置顺序收集，前一位置出现执行、协议、权威证据或未结算费用问题立即停止。每个成功位置保存原始请求、响应、usage、账本和独立评审包，质量状态为 `QUALITY_PENDING`。失败位置保留执行诊断，教学质量为 `UNRESOLVED`。尚未观察的位置为 `NOT_RUN`。
- 原阶段上限仍为 USD 10、首次最多 10 次、至多一次开发复测最多 6 次、总计最多 16 次，截止 2026-11-12 23:59 Asia/Taipei。供应商账单硬限未经验证。当前用户费用授权已给出，真实执行收据和阶段锚点尚未创建。真实生成请求与实际结算、未结算责任均为 0。

## 退出码

| 记录 | 退出码 | 结果 |
| --- | ---: | --- |
| `ssh-batch-offline` | 0 | 首次离线批量成功，10 个 Mock HTTP 回合均待评审 |
| `ssh-batch-final` | 0 | 固定批量提交完成 10 次 Mock HTTP 和 10 份评审包，20 个 wire 哈希匹配 |
| `ssh-batch-python` | 0 | 245 项 Python 回归与真实隔离 PostgreSQL |
| `ssh-batch-frozen-check` | 0 | 67 项专项回归、Ruff、离线 wheel 和冻结身份 |
| `ssh-batch-admission-final` | 0 | 18 项，含最新真实入口与 checkout 切换负例 |
| `ssh-batch-no-tty` / `ssh-batch-disk-final` | 2 / 88 | 预期拒绝。非 SSH TTY 拒绝，原磁盘门禁触发 |
| `ssh-batch-static` | 0 | Ruff、离线构建、锁和冻结清单 |
| `ssh-batch-specific` | 1 | 首次测试夹具解析错会话 ID，已修正，原结果保留 |

最终根分区使用率为 87.91%。通过原门禁还需增加至少 9,683,538,740 字节的可用空间，约 9.0 GiB。真实入口在提示输入密钥和创建锚点之前阻塞。

离线监督器记录位于 `.data/e3-ssh-batch-checks/`。批量记录位于 `.data/ll-eval/e3/ssh-batch-final/`。离线验证使用与原监督器字节相同的测试副本，真实 SSH 入口直接使用工作树文件系统的原磁盘检查。真实 SSH 密钥输入和真实教学均未运行。

唯一真实启动命令及隐藏输入步骤见 [CLI 使用说明](../../docs/EVAL_CLI.md)。运行时打印 `LL_RUN_ID`，可用 `ll eval report e3 --run-id RUN_ID` 查阅结果和私有证据目录。
