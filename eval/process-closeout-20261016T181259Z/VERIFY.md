# 验证与复现

改动：scripts/dev/run_check.py，scripts/dev/tests/{test_run_check.py,process_fixture.py}，docs/LOCAL_CHECK_EXECUTION.md，AGENTS.md 与 .github/workflows/ci.yml 中的本地进程测试步骤。没有 Java、Agent 运行时、前端业务源码、模型配置或冻结验收目录改动。

原始本轮日志位于 `.data/process-closeout-20261016T181259Z/`，不入 Git。最终日志 `process-closeout-identity/output.log`，终态记录 `process-closeout-identity/run.json`；路径/hash、精确 argv、14 项计数与 Ruff 输出在 test-result.json。初轮 tests-01.log 为 11 项，tests-02.log 为 12 项，process-closeout-final/output.log 为 12 项，全部通过；加入取消另起 session 后代、模拟权限拒绝后 14 项全部通过（原记录 test-result-qualified.json）；补充 runner/child start ticks 及取消前身份核验后仍为 14 项全部通过，最终记录 test-result.json，前轮日志保留不覆盖。只报告最终独立数量。

实际最终长命令：

```bash
nohup timeout --kill-after=10s 120s python3 scripts/dev/run_check.py \
  --name process-closeout-identity \
  --output-root .data/process-closeout-20261016T181259Z --timeout 90 -- \
  python3 -m unittest discover -s scripts/dev/tests -p 'test_*.py' -v \
  > .data/process-closeout-20261016T181259Z/tests-identity-launcher.log 2>&1 < /dev/null &
```

复跑须换全新 --name。单独执行等价测试和静态检查：

```bash
python3 -m unittest discover -s scripts/dev/tests -p 'test_*.py' -v
./agent-service/.venv/bin/ruff check scripts/dev
./agent-service/.venv/bin/ruff format --check scripts/dev
git diff --check
```

旧缺陷实际复现命令如下。脚本拒绝覆盖 legacy-reproduction.json；它在本轮私有临时目录加载冻结源码，只替换运行时 ROOT/PUBLIC/PRIVATE 指向临时目录，不编辑冻结文件。三种已确认缺陷是探针的预期观察，不是修复后测试失败。case 日志为 success-descendant.log、cancel-without-record.log、timeout-descendant.log。复跑需复制该探针到新的本轮证据目录并使用新私有目录。

```bash
nohup timeout --kill-after=10s 45s python3 eval/process-closeout-20261016T181259Z/reproduce_legacy.py \
  > .data/process-closeout-20261016T181259Z/legacy-launcher.log 2>&1 < /dev/null &
```

进程/历史信号证据：collect_evidence.py 只读指定 PID 的 stat/status/fd 目标和指定原会话的安全执行标记，不输出完整命令、Environment 或凭据。process-evidence.json 给出实际身份、等待/管道关系、历史 call ID/行号/hash 和受限投影。thread-state.json 是 read_thread 返回的 idle/completed 元数据。collector 拒绝覆盖旧记录，PID 变化后须重新明确核验，不能直接把历史 PID 用于信号操作。

```bash
ps -p 7522,1633403,1634090,1634092 -o pid,ppid,pgid,sid,stat,etimes,wchan:24,comm
systemctl show lecturelens-live-backend.service --property=Id,ActiveState,SubState,MainPID,ExecMainStartTimestampMonotonic
zcat /usr/share/man/man8/sudo.8.gz | rg -n -A 10 -B 6 'suspend|SIGTSTP|SIGSTOP|SIGCHLD'
```

before.json 保存初始 Git、磁盘、冻结清单/JAR hash 和未跟踪文件 inode/size/mtime（不读正文）；closeout.json 与 closeout-final.json 检查冻结清单所有条目/JAR 字节不变、测试 supervisor PID 均退出、旧链身份/state 不变和线上 backend 身份。磁盘使用率公式 used/(used+available)，距 85% 余量为 0.85*(used+available)-used，均从真实 bytes 复算；不把 df 的整数百分比当精确比值。

公开证据与变更源码的 hash 见本目录 SHA256SUMS，原始本轮日志的 hash 在 raw-files.json。只读复核：

```bash
python3 eval/process-closeout-20261016T181259Z/verify.py
sha256sum -c eval/process-closeout-20261016T181259Z/SHA256SUMS
sha256sum -c eval/p2-1c-20261016T155847Z/SHA256SUMS
```

没有服务、数据库、容器或供应商相关检查启动；本轮不重跑业务全量测试或真实模型质量验收。CI 配置已本地纳入测试入口，远端 CI 未运行。
