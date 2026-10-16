# 本地命令挂起与收尾修复

已修复项目后续本地检查的进程管理入口。未终止/恢复任何既有进程，未改业务功能、在线服务或模型绑定，未读取凭据内容，没有供应商调用。P2-1c 凭据门禁仍保留，正式十次没有重启。

## 本次旧链的形成与影响

当前链为 `Codex 7522 → bash 1633403 → sudo 1634090 → Python 1634092`。bash 在 do_wait，sudo stopped，Python 是尚未被父进程回收的 zombie，原始 wait status 为 0。进程身份/start ticks 与初次检查一致。bash 的两个输出管道仍由 Codex 持有读端，旧 shell 不能自然结束并关闭它们。

原会话“运行隔离 Java 基线与恢复验证”的日志记录：12:24:58 UTC 开始无 nohup/外层 timeout 的 sudo 测量执行，返回 session 20654；12:26:24 的取消操作明确选择了 PID 1634092，依次向 Python 发 SIGSTOP、SIGINT、SIGCONT，没有向 sudo 发恢复信号。当前 sudo 停止、Python 已退出的状态与该操作链一致。根因是暂停 sudo 下的命令后，只在叶子 Python 上完成取消，没有保证 sudo/shell 包装层收尾。安全投影和源码行号见 process-evidence.json，不复制原始命令或配置。

**证据限制**：没有当时 sudo 的停止信号/发送者审计，不能断言其停止信号编号；sudo 因下属命令停止而进入 job-control 停止状态是依据现状和历史信号序列的推断。本机 sudo 手册说明其转发/监控 job-control 信号及 SIGSTOP 限制。没有读取 /proc cmdline、environ 或内存来补足缺口。

这不是 Codex 全局死锁的证据：原会话后续完成多个 turn，现为 idle，当前会话和命令执行正常。已确认旧 shell/管道链没有收尾，尚无法从只读信息确认 Codex 内部是否仍把旧 session 20654 注册为待完成或它曾造成哪段 UI 等待；不将其扩展为所有卡顿的唯一原因。[OpenAI Docs](https://learn.chatgpt.com/docs/app-server) 将命令执行、超时、终止和线程中断分别列为协议操作，工具 yield/session 返回不等于完整收尾。

P2-1c 阶段 5 的受控凭据缺失是安全停止；历史 ASR 403 与线上翻译 OUTPUT_INVALID 属于独立业务/权限问题，本轮不修复或复测它们。资源快照在 before.json/process-evidence.json，不支持把本次残留归因于磁盘耗尽。

## 项目内已确认的缺陷及修复

在临时目录执行未修改的冻结 run_check.py，实际复现 3 个缺口：成功退出后留下后代；SIGTERM 取消后留下进程且没有终态记录；超时后因直接子进程先退出而跳过强制回收，留下忽略 TERM 的后代。探针只操作自己创建的非特权进程，结束后全部 kill/wait 回收，见 legacy-reproduction.json。

新增 `scripts/dev/run_check.py` 作为后续检查入口，AGENTS.md 明确使用，CI 加入其测试。它关闭 stdin、用普通文件隔离输出、冻结环境白名单，统一处理成功/失败/取消/超时；用 Linux subreaper、后代身份及 pidfd 管理本次新建进程，覆盖另起 session 的子孙，TERM/KILL/回收都有期限。终态原子记录保留子进程原始返回码、触发原因、信号和日志 hash；清理失败显式返回 125，不能报成功。机制依据见 [Linux subreaper 文档](https://man7.org/linux/man-pages/man2/PR_SET_CHILD_SUBREAPER.2const.html)。没有修改冻结脚本或应用运行时。

## 验证与边界

最终 **14 项通过，0 失败/错误/跳过**。覆盖正常/失败/信号退出、启动错误、超时、忽略 TERM、stopped 子进程、父先退、另起 session、三种取消信号、拒绝覆盖旧记录，以及模拟权限不足时有界失败。权限拒绝只在新测试解释器内模拟；其故意遗留的合成进程由测试父进程回收，未使用 sudo。所有创建的 fixture 最终均验证不存在，无新增异常等待链。Ruff 检查/格式检查及 git diff --check 通过；运行记录和 hash 见 test-result.json。多轮 11/12/14 项是逐步增加覆盖的重复检查，不累加为独立用例数。

冻结候选和历史证据、既有未跟踪 DIAGNOSIS.md、live backend 身份保留检查见 closeout.json/closeout-final.json。磁盘 df 显示 76%，通过门禁。只提交本地，不 push/merge/部署。

旧 bash/sudo/zombie 链仍保留。清理它需要对这条明确身份的既有链另行授权；本轮未向它发送任何信号，不建议直接恢复过期开发命令。新包装器不能接管旧链，也不能保证处理包装器本身被 SIGKILL、内核不可中断等待或更高权限后代；这些情况显式保留未完成/失败记录，不能声称已修好所有 Codex 内部问题。
