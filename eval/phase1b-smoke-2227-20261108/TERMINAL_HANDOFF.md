当前交接状态：PHASE1_B_EXECUTION=BLOCKED，PHASE1_B_QUALITY=NOT_RUN，REAL_REQUESTS=0，LOCAL_COST_USD=0.000000000，SUPPLIER_BILLING=UNKNOWN。这是实际执行前状态，不是 v19 教学失败。旧 REPORT.md 保留此前凭据缺失的历史检查；本文记录用户已在独立 SSH shell 输入并 export 后的后续准备。

用户终端的 export 仅被其子进程继承，不能改变 Codex 工具进程的环境。两种 shell 的工具检查均只得到 AGENT_LLM_API_KEY 不存在，没有读取值。`terminal_run.sh` 因此由用户在刚才的同一 SSH shell 执行；不需重新输入密钥，不复制密钥到另一个环境。命令只含路径和交付消息中的最终 clean HEAD：

```bash
bash /home/dev/.codex/worktrees/phase1b-tutor-diagnostic-20261108/lecturelens/eval/phase1b-smoke-2227-20261108/terminal_run.sh FINAL_CLEAN_HEAD_FROM_DELIVERY
```

只执行一次，保留 SSH 连接等待 SMOKE_EXIT；出错、超时、连接中断或结果不明均不重跑。原授权仍在 2026-11-08 19:00 UTC 终止。没有新的授权、续期、模型替换或本地预算提高。

`terminal_once.py` 只支持原固定 Run ID 和原声明，先检查变量存在性、两个工作树身份、原 review plan、价格回执、新数据库容器归属与 SQL durability，再将最多 15 分钟且不越过原期限的完整 grant／风险回执一次性物化到 `.data/smoke-2227/terminal-once-receipts/`。独占目录和原 private_file 防止重复签发；部分失败也不重签。原 risk_once 至少 185 秒余量、原外层 admission 和 native live_admission 仍完整执行，最终交接未修改的 frozen CLI。凭据值仅由获准的原 provider 使用；外层只检查成员存在，原生 exec 继承实际用户进程环境。Docker 检查子进程使用固定最小环境，格式不包含容器 Env。

`terminal_run.sh` 以 noclobber 保存 `.data/smoke-2227/terminal-handoff/live-terminal.log` 和 `live-terminal.exit`，umask 077，不覆盖此前日志。Python 的一次性回执、外层 started、原 native claim 与固定真实输出目录仍保留。日志中不会打印环境或密钥。用户命令返回后，可从这些文件和原 runner `.data/v19-smoke-20261108-2227-once/` 检查实际退出码、原始响应、ledger、usage 与状态。没有真实输出时，不导出伪造的实际回答，也不继承旧 Mock 结果。

新建数据库仅用于本次运行：

| 项目 | 实际值 |
| --- | --- |
| 容器 | `lecturelens-v19-smoke2227-20261108` |
| ID | `22130884d07072e29b3aad4c74228ff9700add0ec27cce2102c2bb9d4736f661` |
| 固定镜像 ID | `sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f` |
| 入口 | `127.0.0.1:25841`，仅 loopback |
| 持久卷 | `lecturelens-v19-smoke2227-20261108-data`，新建，保留 |
| 数据库／用户 | `lecturelens_agent_acceptance`／`tutor_scale`，公开合成测试密码 |
| 配置 | restart=no、fsync=on、synchronous_commit=on；全新用户表 0 |

创建前核实端口空闲、容器名／卷名不存在；创建后核实 run_id label、镜像、精确端口绑定、可写持久卷、实际 current_database/current_user 和配置。公开绑定记录是 TERMINAL_DATABASE.json，私有原始元数据及 SQL 证据在 `.data/smoke-2227/terminal-handoff/`。只连接该新库，没有连接业务数据库、重启原服务或删除数据。交接时该新容器保持运行，真实试验结束后只停止这个新容器并保留卷和 live schema；不清理或复用旧实例。

官方公开资料已再次核实，冻结 `deepseek-flash`、非思考 required tools 和 4096 tokens 仍兼容。峰值输入／输出每百万 US$0.30／1.20，原本地账本 300／1200 nano-USD/token 仍覆盖；见 [官方价格](https://api-docs.deepseek.com/quick_start/pricing/) 和 [Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)。TERMINAL_PRICE_RECEIPT.json 记录实际核查时间及保存原文的 hash，不冒充账户硬限或供应商实际扣款，也不会自动刷新时间。没有账户／余额 API 或付费请求。

验证记录：

| 检查 | 退出码与证据 |
| --- | --- |
| 新终端机制回归 | 10 passed、0 skipped、退出 0；缺少凭据、准备 SHA 改变、价格过期、数据库失败、授权过期、完整范围绑定、重复签发、native 拒绝后的禁止续签、数据库归属／loopback／持久化及 Docker 最小环境。全部使用合成凭据映射、Mock native handoff 和 socket fence；没有实际发送。 |
| 短检查原始记录 | `.data/smoke-2227/terminal-handoff/terminal-tests-final.log`、SHORT_CHECKS.json；约 1.37 秒、15 秒 timeout、TMPDIR=/dev/shm、禁用写 bytecode。 |
| 缺少实际变量时 shell 停止 | 退出 2，无 live log／有效回执／claim；missing-key-shell.log。 |
| 实际数据库归属与只读 SQL | 退出 0，fsync 与同步提交开启；database-container-created.json、database-sql-preflight.json。 |
| Ruff／format／bash -n／diff --check | 最终各 0；初次 Ruff 风格错误已修复。 |
| 原通用长检查监督器尝试 | 退出 88 DISK_GATE，保留 `.data/dev-checks/smoke2227-terminal-tests/run.json`，未声称该命令通过。创建新数据库后磁盘余量距离该监督器保留阈值差约 23 MB，实际可用约 40.96 GB。没有关闭、修改或重试该监督器门禁，也没有删除已有资产；仅对新增约 1 秒离线单元检查使用有界内存临时目录检查。 |
| 前次外层回归 | 105 项退出 0 为原 2ad54608 交付证据，本次没有冒充重新执行完整套件。 |

交付时实际 grant、风险短期回执、外层 started、native claim、固定真实输出、live 日志均尚未创建。用户执行这个命令才可能发送；届时必须只沿原路径一次执行，之后按原工具导出真实确定性结果和完整外部 AI 评审包。AI 评审保持 NOT_RUN（取得真实答案后但尚未独立评审则 UNRESOLVED），HUMAN_NOT_RUN、expert_verified=false，不宣称专家验证。Phase 0 GitHub CI=PENDING；本次仍为独立 CLI 诊断，没有产品整合、push、PR、合并、部署、full16 或 Phase 2。
