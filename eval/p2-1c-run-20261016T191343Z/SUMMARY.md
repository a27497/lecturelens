# P2-1c 受控启动：Redis DB 15 门禁停止

**本轮未进入真实课程验收。** 已按授权创建指定临时 unit；其受控 Python 进程以 dev（UID 1002）运行并只在内存消费已批准配置。它在无供应商调用的启动预检中返回 `REDIS15_UNEXPECTED_KEYS`，随后退出并由 systemd 自动移除。没有启动冻结 Java 应用，没有提交冒烟或正式任务。

| 项目 | 实际状态 |
| --- | --- |
| SMOKE / NORMAL 已提交 | 0 / 0，正式计划 10 |
| 完整链路成功率 | 未测（未完成正式十次） |
| 抽取 / ASR / 翻译 / 资料 / 提交到终态耗时 | 均未测 |
| ASR 真实调用 | 0 |
| 供应商费用、目录价估算 | 未测；未发起本轮模型请求，不声称已核对供应商账单 |
| CER、缓存命中、并发 8、SIGKILL 恢复 | 均未测/未演示 |

## 实际停止原因与证据边界

Redis 检查沿用既有规则：DB 15 必须为空，或只有 `eval/p2-1b-pipeline-20261016T122904Z/redis-reuse-authorization.json` 指定的单个历史 key；不读取值、不删除 key。当前状态没有通过这个检查。

失败时没有记录 DBSIZE/SCAN 的结果，因此**不能断定当前具体键数、键名、归属或冲突操作者**；单次 SCAN 返回与旧严格预期不符也可能触发同一固定错误码。不得据此把 Redis 清空、切换数据库或扩大旧单 key 的许可范围。

原始固定错误码在 closeout-service.json；unit-journal-safe.json 验证同一 InvocationID 的消息及 UID=1002（dev），没有输出环境值。第一次日志投影误把 dev UID 假设为 1000，断言失败后改为 passwd 账号元数据查找，没有重启 unit。

bootstrap-preflight.json、runtime-ready.json、java-identity.json 均未生成：原 bootstrap 指纹和新增的最终 Spring 隔离门禁尚未执行，不能把离线自检或历史记录当作本轮真实门禁通过。

## 已完成的准备

- 从原冻结 JAR 提取完整且未修改的候选类/依赖；JAR SHA-256 仍为 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`，没有使用后续翻译修复 JAR。
- 独立 dev-unit 适配器只在内存加载 runtime.json 与 systemd ASR credential，system-models.env 只由 systemd 读取；不转发 MYSQL_ROOT_PASSWORD，不使用 root 数据库连接。
- 设计了 Spring 初始化前的最终配置门禁，检查 schema、Redis DB、topic/消费组、工作区、临时目录、关闭 Study/index 同步、全部 candidate-options 开关和预算。它在原 bootstrap 指纹校验之前运行，校验失败不初始化业务 bean。
- 原 bootstrap selftest 实跑通过；新增日志过滤和命令作用域的合成自检通过。它们仅验证仪器机制，不代表真实 ASR/模型或课程质量。
- 解释器与 CER/DB/HTTP/存储依赖均复用既有只读环境，没有安装依赖或修改旧环境。CER 仅计划在 unit 内按原 P1-3 的函数口径计算，不导出转写/参考正文。

## 清理与未改变范围

临时 unit 已 not-found / inactive，18091 无监听；本轮没有 Java worker、任务、Redis key、业务行或派生存储对象需要回收。已删除本轮提取的运行目录、编译类、tmp/workspace；保留源码、固定状态、日志哈希与冻结原 JAR。未删除任何旧 Redis key、数据行或存储对象，没有操作受保护容器。

在线后端 PID/启动时间和 JAR、冻结候选、历史证据及原有未提交文件保持一致。没有修改 live unit、环境文件或模型绑定，没有 SIGKILL、重启、push、merge、部署。

一次定位 CER 帮助函数的检索范围误含 JSON 证据，返回了正文片段；已立即收窄到明确代码文件，未把该片段再导出或写入本轮文件，事件只记元数据于 privacy-incident.json。不能据此宣称本轮所有信息处理约束均无偏差。

## 下一步

先在受控 unit 内只读诊断 Redis DB 15 的 DBSIZE、完整 SCAN、TYPE 和 TTL，仍禁止 GET/值读取；保存键名/数量/类型/TTL 的安全投影，确认是实际占用还是旧单次 SCAN 预期不适用。当前 unit 已退出，未擅自再建或重启来补查。

若存在未获准的 key，需由所有者确认归属及处理方式；本轮没有清理未知 key 或更换 DB 的授权。门禁恢复后仍须按原边界获准重启该临时 unit，再走最终配置、原指纹、冒烟与 ASR/403 门禁，不能直接跳到正式十次。

复现与清理原始记录见 [VERIFY.md](VERIFY.md)、closeout.json、SHA256SUMS。trials.jsonl 保持为空，未把预检失败记作课程失败，也未制造成功试次。
