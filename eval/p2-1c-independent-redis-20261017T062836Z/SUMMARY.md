# P2-1c 独立 Redis：隔离与指纹通过，应用初始化失败

**历史 Redis 占用已通过全新实例绕开，原隔离及 bootstrap 门禁实际通过；完整 Java 应用随后退出 1，尚未进入真实课程验收。** 本轮没有提交冒烟或正式任务，没有补跑或替换试次。正式成功率为“未测”，不能写成 0/10。

## 实际完成

1. 使用已有 Redis 镜像的固定 image ID 创建本轮专用容器。以 dev 的 UID/GID 运行，绑定独立回环端口，DB 保持 15，受保护模式开启、只读根文件系统、无 capabilities、不持久化；/data 为本轮 tmpfs，没有共享持久卷或历史目录。网络命名空间采用 host，以便 Redis 本身仅绑定回环地址；这不共享 Redis 数据、进程或消费状态。完整差异与镜像身份见 environment-delta.json / redis-resource.json。
2. 创建后两次完整空库检查通过；unit 内再次核对 Redis server run_id 的 SHA256，再做两次完整空库遍历，均为 0。**没有连接原 Redis 实例或读取其任何数据。** 新实例严格要求空库，没有扩大旧单 key 白名单。
3. 原冻结 JAR SHA256 为 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`，源提交 dcc4dda753afd89fafcc2375eaf3cd942dba4b02。仅从该 JAR 提取 classpath；未混入后续翻译修复。原 P21Bootstrap 源码完全相同，额外隔离监听器只加强 Redis 地址检查。
4. 指定临时 unit 实际以 dev（UID 1002 / GID 1003）运行，直接引用已批准 EnvironmentFile / 加密 credential，运行配置仅在服务进程内消费。未输出/复制密钥或运行配置值。
5. 隔离 schema、版本 10、无待执行任务/待发 outbox、五份媒体/参考字幕哈希及所有权检查通过。原 Java preflight 退出 0：最终隔离门禁和 version=10 / fingerprint_equal 均通过。完整应用进程再次打印同样两项 PASS。

cache OFF、C/E=false、模型绑定、MySQL schema、MQ topic/消费组、课程数据和冻结预算保持原方案。唯一环境差异是独立 Redis 实例；运行 catalog 检查尚未到达，不把 preflight 通过冒充为应用就绪。

## 停止点与证据缺口

2026-10-17T06:31:07.901160+00:00，适配器保存 `APPLICATION_START_FAILED`、Java exit=1、owned_tasks=[]，随后退出。unit InvocationID 为 `6abbe89b165d4efe8576d043c2caf971`；安全 journal 投影证实 dev 进程的固定退出码消息。

最后通过的是完整 Java 进程中的最终配置隔离与原 bootstrap 指纹校验；未到 health readiness、运行 catalog、任务提交或 ASR。**本轮剩余阻塞是 Java 应用初始化失败，具体原因 UNKNOWN。** 不能归因为 Redis、模型指纹、权限、数据库或 MQ，也没有观察到 ASR 403。

现有输出投影丢弃了非白名单的启动异常；logback 仅控制台且使用 %nopex，没有原始启动日志文件。退出后无法恢复根因。这是本轮诊断缺口，未以重启重试补查。新 P21StartupDiagnostics.java 仅离线编译/自测，未接入本次真实启动；后续诊断及授权需求见 NEXT_START_DIAGNOSTICS.md。

## 真实验收结果

| 项目 | 本轮 |
| --- | --- |
| 冒烟提交 | 0，未测 |
| 正式提交 / 计划 | 0 / 10；完整链路成功率未测 |
| 每课片数、调用数、峰值并发、限流/降并发 | 未测 |
| ASR 实际 token、目录价估算 | 未测（无课程试次台账）；不填写 ¥0 |
| CER / 与 P1-3 的 4.169% 比较 | 未测 |
| SIGKILL 恢复 / 缓存命中演示 | 未测；本轮不执行，cache 始终 OFF |

| 阶段，秒 | P2-1b 历史 mean±sample std | 本轮 |
| --- | --- | --- |
| 抽取 | 9.439±1.543 | 未测 |
| ASR | 172.145±41.116 | 未测 |
| 翻译 | 29.428±7.308 | 未测 |
| 资料生成 | 成功样本无 | 未测 |
| 提交到终态 | 213.832±44.533 | 未测 |

上述基线来自原 DESIGN / 历史记录，不是本轮重跑结果。没有可计算的加速比。未来 ASR 费用继续仅使用真实台账 `(input_tokens*0.8 + output_tokens*2.7)/1_000_000`，标注“目录价估算”；无 usage 不猜测费用。

## 验证与清理

新增 instrumentation 的冻结参数/安全过滤检查、原 bootstrap selftest、后续异常类别包装器离线 selftest 均通过；不重复已完成全量回归，不将这些机制检查称为真实模型验收。

临时 unit 自动移除，原 Java 身份消失，无 SIGKILL。独立 Redis 核验 container ID 与本轮 owner label 后停止/删除；没有持久卷。只删除本轮 runtime/extra/tmp/workspace，保留安全证据与日志。18091 和本轮 Redis 端口无监听；在线 backend PID/start 时间前后相同；95 份历史证据、冻结 JAR 哈希及原未提交文件 stat 均未变。终检磁盘占用 75.8192295604121%，距 85% 为 14,218,939,596.8 bytes。

本地准备提交 c8c9714；本轮结果另行本地提交。不 push、merge 或部署。下一步需要依照用户原“重启前先停下”的边界，批准一次仅启动诊断（不提交任务），并重新创建同范围独立 Redis；不需要新增凭据来源或扩大预算。
