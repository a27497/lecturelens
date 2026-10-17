# P2-1b 验证与复现

本轮为用户明确授权的替代候选独立 10+1。原 P2-1 的 MQ 传输失败及取消试次完整保留在 [原记录](../p2-1-pipeline-20261016T073754Z/VERIFY.md)，不混入本候选、不改写原失败。

## 冻结身份与授权范围

候选 JAR SHA256：`fa21a575d09789b9899faba71ec861216d3c741b6919a0f3add50c532242efb7`。归档路径及源码基点/补丁 SHA256 在 candidate-artifact.json，补丁在 candidate.patch。与原 JAR 相比只有 MQ payload 的一个嵌套 class 改变，其他候选 class 和所有依赖相同，见 class-diff.json。系统 v10、策略 translation-v2.5、同五节媒体及 SHA256 不变。恢复与正常试次使用同一归档和 helper；instrumentation-artifact.json 单独冻结 helper 身份，不伪称 helper 属于原 JAR。

仅运行隔离 Java `127.0.0.1:18091`，沿用本轮 schema `lecturelens_p21_20261016`、专属 topic/group 和 Redis DB 15。原失败 task 的唯一 progress key 非空时先停止并报告；用户明确授权保留该 key 原样复用，见 redis-reuse-authorization.json。启动门禁只接受空库或这一个确切的已授权 key，不读取值，不删 key、不换库。其他已有 key 仍触发停止。每个新任务 UUID 与原失败 task 不同。

系统配置只由现有受保护部署引用注入子进程，主密钥/供应商凭据不出进程内存；不读 `/proc/*/environ`。启动前和实际启动均以 frozen class 的 capture 验证 v10 指纹完全相同，拒绝版本/指纹差异，未创造 v11。只通过数据库内部 INSERT/SELECT 复制原配置到隔离 schema（原轮准备完成），不导出 config_json/密文/密钥。隔离 Java 禁用 Python Study/index 同步。没有 docker exec、受保护容器重启或部署操作。共享存储、MQ 与模型服务只接受有界协议请求。

磁盘门禁按 `100*used/(used+available)`，启动需要距 85% 至少 2 GiB；主流程每次请求/任务检查，独立监控每 2 秒检查，超过 85% 停止派发并结束本轮进程组。正常任务串行，翻译内部 AIMD；每任务首次提交起 1800 秒、翻译首次进入起 900 秒，不因恢复重置。正式 10 次不补跑、不剔除失败。

## 机制与真实调用分开

MQ wire 回归先失败（5 项中 1 失败），补丁后 producer/consumer/message/runner/creation 相关 **48 项全部通过，0 跳过**；离线 JAR 打包成功。命令、计数及原始日志哈希在 [runtime-checks.json](../p2-1-pipeline-20261016T073754Z/runtime-checks.json)。这验证消息保留 fencing 字段与旧字段省略，不证明真实模型效果。代码未修改 Python Agent/runtime 或数据库租约/恢复算法；此前阶段的独立 MySQL 机制检查另见原 VERIFY，不重复相加。

helper 的 selftest 验证版本/指纹拒绝、至少 2 批且过半尚未全部完成的 barrier 门槛、阻塞时零 provider 派发和解除后一次派发；真实恢复仍须由原始 task/批次/attempt/ASR 比对证明。selftest 和 preflight 私有日志保留。新旧源 MinIO 对象 SHA256 的只读流式验证在 [media-identity-preflight.json](../p2-1-pipeline-20261016T073754Z/media-identity-preflight.json)，没有下载新的媒体副本或重新上传。

## 统计与费用

measurement-protocol.json 固定五课各两次、NORMAL 分母 10，RECOVERY 单列。trials.jsonl 保留提交与终态事件；runtime-evidence/ 为每个 task 的安全 DB 投影、原始 scheduler event_seq 及阶段起止/耗时。阶段完成与失败分别统计，未进入为 NA，样本标准差 ddof=1，n<2 时为 NA。恢复设计要求前后安全投影及逐批比对；本次 ASR 提前失败，只有失败后的 recovery-after.json，没有 before/barrier/plan 比对，不用新建 task 或重绑定模型伪造恢复。

唯一调用事实来源是 model_call_attempt，包含失败、截断父批、重试/子批。translation_attempt 只用于恢复/预算关联，ai_call_record 和 diagnostic 不再次计费。当前 ASR workspace 地址不匹配冻结运行时精确主机价卡，账本 UNPRICED 原样保留；报告另以实际 prompt/completion usage × 同名北京模型公开目录价给参考估算，不能冒充该 workspace 的实际账单。DeepSeek 使用账本原费用上下界；美元和人民币不合并，未知用量不填零。价格来源/复核日期见 pricing-recheck.json 和 [原价卡](../p2-1-pipeline-20261016T073754Z/pricing-20261016.json)。

资料 HTTP 400 的请求地址、大小、hash、安全参数摘要及最多 4000 字符脱敏响应仅留私有 errors/，不会因失败改动资料生成参数或评分。公开文件只保留计数/hash/状态；课程原文、供应商响应及原始完整运行日志不进 Git。抽样语义核查另记 private 样本和公开摘要，不将覆盖/语言通过宣称教学质量。

## 复算与封存

完成后运行以下只读复算，不触发新任务或模型调用：

```bash
cd /home/dev/projects/lecturelens
python3 eval/p2-1b-pipeline-20261016T122904Z/summarize_runtime.py
python3 eval/p2-1b-pipeline-20261016T122904Z/validate_evidence.py
sha256sum -c eval/p2-1b-pipeline-20261016T122904Z/SHA256SUMS
sha256sum -c eval/p2-1-pipeline-20261016T073754Z/SHA256SUMS
```

私有记录目录 `.data/p2-1b-pipeline-20261016T122904Z/`，来源冻结 JAR、逐进程 start_ticks/cwd/hash、完整 worker.log、API 错误与 400 摘录保留。公开索引只包含路径/哈希，原始记录以 RAW_SHA256SUMS 核验。实际关闭状态、故障注入次数、保护服务身份与生产配置前后比对见下方。最终本地提交，不 push、不部署。

## 实际结果与未完成项

正常 **10/10 已提交并终止**，翻译覆盖/对齐发布 **10/10**，完整链路成功 **0/10**。资料生成的十次 HTTP400 均为 exceed_context_size_error：输入 11727–17073 tokens，大于现有本地模型上下文 8192，原请求 max_tokens=4096。私有脱敏响应均完整（未截断），公开只保留 materials-errors.json 中的计数、错误类型及 hash；未改资料生成逻辑、参数或模型。

正常转写 884 次、翻译 527 次物理请求。经济学两次各有一个出网前预算拆分父节点（attempt_count=0），各生成两个子批，正常物理重试为 0；费用只加实际子批请求。进度更新中曾误称无拆分，汇总核查后已明确纠正，不修改实际账本/批次树。ASR 账本区间并发峰值 2，翻译窗口从 1 增长到 4、在途峰值 4，未观察到实际 429/超时收缩；收缩机制仍以原阶段 mock 检查为依据，不冒充真实供应商压力测试。

独立 RECOVERY `task_bca24366edcd4e09b38f38b213817485`：共 71 次 ASR 请求，69 次 HTTP200，第70片 HTTP403/AUTHENTICATION，另一在途请求在失败清理时中断、NETWORK_OUTCOME_UNKNOWN。403 不重试；ASR 未完成并未保存完整 source checkpoint，翻译调用/批次均为 0。403 响应长 178 字符但运行时只为400保留私有正文，因此403正文未采集，具体权限/密钥/余额原因不能判断。69次已知用量的公开目录价参考为 0.0424279 CNY，另两次用量/费用未知，不填零。恢复终态 FAILED，159.300 秒，未触发 barrier，**SIGKILL 0 次、未重启**。没有“已完成批次不重跑”的真实证明，恢复验收未完成。

只读 plan 观察器因恢复未到达 translation_plan/barrier 退出 1，失败日志 `.data/p2-1b-pipeline-20261016T122904Z/recovery-plan-observer.log` 保留；不把观察器失败当作机制测试通过。正常 driver 退出 0 只表示执行/导出结束，不代表任务或恢复通过。恢复失败后未追加任务或模型探测。

30 对首/中/末译文由 Codex 对照源转写检查，未发现明显含义冲突；概率课两次均出现“集体穷尽”的生硬术语，2 次观察保留，不改成完美质量结论。原文/译文样本仅在 private quality-samples/，公开为 hash、计数和检查意见。没有专家评分或整课语义正确率声明。

磁盘采样 3030 次，峰值 **75.11144384614904%**，从未超过85%；最终隔离 worker 已退出，18091 无监听，所有本轮测量/观察进程已退出。线上 Java MainPID/启动时间与系统 v10/config SHA256 前后相同。容器只进行 `ps/inspect` 元数据读取，无 exec、启动、停止、重启或删除命令。运行期间另一个 `samescale-code-snapshot-test-20261016` 容器从清单消失，后续按原 ID 只读 inspect 返回不存在；原因/操作者未验证，不能宣称所有外部容器状态前后一致。其余共同容器 ID/启动时间相等，详见 container-identity-reconciliation.json。未操作受保护容器，未 push、未部署。

`validate_evidence.py` 对真实 11 个 task 的唯一性/顺序、v10/v2.5、源译文覆盖、批次/调用边界、ASR 切片数、用量加和、Decimal 费用重算、候选/helper hash、实际403失败、关闭状态与磁盘门槛做一致性检查。evidence-integrity.json 为 PASS，同时明确 `normal_full_chain_acceptance=FAILED_0_OF_10`、`recovery_acceptance=NOT_DEMONSTRATED_ASR_403`；它不是质量/恢复验收通过。正常 ASR 目录价参考合计 **0.5022330 CNY**，翻译已知目录价估算 **0.063459192000 USD**；恢复试次另列，不能重复计费或换汇合并。
