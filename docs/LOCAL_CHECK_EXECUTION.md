# 本地检查隔离与日志

长检查使用 `python3 scripts/dev/run_check.py --name NAME --timeout 1200 -- COMMAND ...`。
stdout/stderr 写入 `.data/p7/checks/NAME.log`，退出码、命令与耗时写入同名 JSON。
名称应唯一，保留失败记录。超时或 Ctrl-C 终止该检查的进程组，不影响其他项目。
不要将真实凭据放在命令参数或日志中；本地示例仅含 disposable 测试口令。

P7 数据库为新的 `lecturelens-p7-flashcards-20261027` Compose 项目，配置见
[`eval/p7-flashcards/compose.yaml`](../eval/p7-flashcards/compose.yaml)。先用 `ss -ltn`
确认端口未使用，仅绑定 `127.0.0.1:25701`；全量测试使用其中的 `lecturelens_agent_test`，
浏览器使用 `lecturelens_p7_test`。旧成本围栏测试要求前一个精确库名；它仍是独立新容器中的测试库。
Node 使用 `export PATH=/opt/node/bin:$PATH`。源码、构建与日志留在当前 worktree，
不使用其他 worktree 的服务、配置、容器或数据库。

命令与最终数字见 [P7 检查记录](../eval/p7-flashcards/REPORT.md)。
