# 本地开发检查的进程收尾

Linux 上的新开发、测试命令使用 `scripts/dev/run_check.py`。它只管理自己创建的命令及后代，不接管既有进程，不授予服务启动/重启或供应商调用权限。冻结的验收脚本、候选及原始记录保持原样；新的检查记录另存。

从项目根目录执行，例如后端测试（数据库需事先按任务授权准备）：

```bash
nohup timeout --kill-after=10s 660s python3 scripts/dev/run_check.py \
  --name backend-check-UNIQUE --cwd backend --timeout 600 -- \
  ./mvnw -o -B test > /tmp/lecturelens-backend-check-UNIQUE.log 2>&1 < /dev/null &
```

内层期限留出 TERM 宽限与 KILL/回收时间，再设置更长的外层 `timeout --kill-after`。Codex 工具返回 running/session ID 或到达 yield 时间，只表示命令尚未结束；读取新包装器的 `.data/dev-checks/<name>/run.json` 和 `output.log` 判断进度。相同名称拒绝覆盖，日志和记录权限为 0600。

包装器关闭子进程 stdin、将输出重定向到普通文件，隔离子进程 session。它将自己设为 subreaper，接管因父进程退出而遗留的后代，并在收尾时 `wait` 回收。新 session 的后代也通过祖先关系纳入管理；用 PID/start ticks 与 pidfd 锁定身份，不按名称扫描杀进程。机制依据见 [Linux subreaper 文档](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html)。

取消前先确认记录仍为 RUNNING，且 `/proc/<runner_pid>/stat` 的 start ticks 与记录的 **runner_start_ticks** 一致，再向该 runner_pid 发送 SIGTERM 或 SIGINT并等待终态记录；禁止仅凭旧 PID 操作。不得对 sudo 下的 Python 单独先 STOP 再 CONT，也不要以 `pkill -f` 或全局进程清理代替任务身份核验。这里只描述本次创建的检查进程；处理已有残留进程仍按用户授权边界执行。

成功、失败、取消、超时和磁盘门禁共用收尾路径：向仍存活的后代发 TERM，宽限期后 KILL，两个等待阶段都有期限，最后回收退出状态。若出现权限不足、不可中断等待或清理异常，返回 `CLEANUP_INCOMPLETE` 和剩余身份，不把它写成成功。

| 终态 | 包装器退出码 | 诊断 |
| --- | --- | --- |
| SUCCEEDED | 0 | 命令返回 0，后代回收完成 |
| FAILED | 命令退出码；信号退出映射为 128+信号号 | child_returncode 保留原始值，包括负信号号 |
| TIMED_OUT | 124 | 保留实际子进程退出码，不能用它替代超时结果 |
| CANCELLED | 128+取消信号号 | cancel_signal 记录最先收到的取消信号 |
| DISK_GATE | 88 | 占用超过 85% 或距 85% 不足 2 GiB |
| SPAWN_ERROR | 找不到程序为 127，其余为 125 | 记录异常类别/errno，不复制异常正文 |
| CLEANUP_INCOMPLETE / SUPERVISOR_ERROR | 125 | 保留原终止原因及可用清理信息 |

记录以原子替换方式从 STARTING/RUNNING 转为终态。记录包括时间、命令 argv 的 hash、进程身份、信号、后代回收、日志 hash；不复制完整参数。子进程环境只传基础工具变量和显式测试数据库变量，不读取部署文件或转发供应商环境。勿把凭据放进命令参数或被检查程序的输出。

包装器不是 root 服务管理器，不能保证终止更高权限进程或内核不可中断任务。包装器本身被 SIGKILL、机器断电等情况无法执行 finally；遗留的 RUNNING 记录不代表成功。服务仍应使用其获准的服务管理入口；本地包装器不绕过任何凭据、403 或资源门禁。

针对性回归：

```bash
python3 -m unittest discover -s scripts/dev/tests -p 'test_*.py' -v
```

测试仅创建并清理自己的合成进程，不使用 sudo、网络、数据库、容器或真实模型。
