# 隔离真实验收：原候选协议失败，替代候选恢复受阻

2026-10-16 后续执行：磁盘门槛已满足，用户已授权隔离启动、单次 SIGKILL/重启和结束停止。隔离 worker 已启动后停止；首个 NORMAL 在 MQ 传输中丢失 v2/epoch 字段，被消费者拒绝，随后取消。已保存真实 `trials.jsonl`，原候选剩余 9 次及 RECOVERY 未提交，物理供应商调用为 0。不能将部分队列写成完整 10 次结果。缺陷、原候选归档和停止证据见 protocol-defect.json、redis15-stop.json、runtime-closeout.json。

用户已选择修复后另冻新候选、执行独立 10+1，原失败单独保留。重启前 Redis DB 15 非空（仅本轮取消任务的进度 key），先按用户硬约束停止；随后用户明确授权保留该本轮 key 原样复用 DB 15，不清空、不换库。新候选见 ../p2-1b-pipeline-20261016T122904Z/，启动检查仍拒绝任何其他已有 key。原 DESIGN.md 保持冻结。

替代候选最终完成十次正常试次（翻译10/10发布、完整链路0/10，资料均上下文超限400）；第11个独立恢复任务在ASR返回403，未达到barrier、未SIGKILL，恢复演示未完成。本轮进程已停止，结果/失败/未完成项均在新候选 SUMMARY.md/VERIFY.md，未追加试次或改写失败。

## 拟操作的确切边界

- 新隔离 Java worker，仅监听 `127.0.0.1:18091`（本次只读检查未占用）；新 schema `lecturelens_p21_20261016`，专属 Redis DB/命名空间（启动前只查选定空间为空，不 FLUSH），MQ topic `lecturelens-p21-20261016T073754Z` 和相同前缀的独立 producer/consumer group。不用任何现有 topic/group。
- 源媒体仅引用 baseline-asr-20261015/assets.lock.json 的现有 5 节课程及原 SHA256，复用 STORED 上传引用，不重新上传或复制视频。新任务 UUID 对应的 artifacts/keyframes 对象前缀列入本轮专属清单；读取的原上传对象不删除。写入隔离 schema 的课程/结果不得回写生产或 Python Agent 表。
- 系统 v10 只通过数据库内部的受控 INSERT/SELECT 复制到隔离 schema，不导出配置 JSON、密钥或密文到工具/报告。服务从已有受保护部署引用获得主密钥，按版本解密；不读取 `/proc/*/environ`，不使用旧 start-direct.py 的环境复制办法。
- 启动前必须解决并验证环境 capture 边界：SystemModelRegistry.initialize 会比较部署环境指纹，环境不一致会产生新版本。隔离启动必须保留既有安全环境引用，或使用仅限验收的冻结启动器读取已复制 v10 的安全捕获身份；不能用空环境启动后默认产生 v11、不能冒充 v10。具体启动器经检查与 mock 验证后才可运行；做不到则停止。
- `PIPELINE_TRANSLATION_V2_ENABLED=true`、`PIPELINE_TRANSLATION_CHECKPOINT_ENABLED=true`、`PIPELINE_TRANSLATION_ISOLATED_RUNTIME=true`；其余冻结参数依设计默认。只为隔离工作区设置 java.io.tmpdir 与 runner workspace。候选 JAR/source identity 由 candidate-artifact.json 和阶段文件清单冻结。
- 不重启现有 Java、agent-service、llama、ASR、RocketMQ、MinIO 或任何受保护容器。共享的模型服务接受本轮有界请求，可能增加瞬时 CPU/队列负载与真实费用；没有额外模型探测。

本轮进程/端口/schema/topic 范围与单次故障注入已获用户确认；该授权不撤销 Redis 非空停止或磁盘超过 85% 停止条件。启动身份/指纹与 barrier mock 通过后才可运行。

## 测量与失败规则

1. 只读检查当前 v10 的全文路由：DATABASE / deepseek-flash，其他功能的安全路由投影哈希保持一致；不改绑定、不触碰凭据。隔离首次任务也必须冻结系统 v10、policy v2.5 与相同代码/策略哈希。
2. 原 5 课按 assets.lock.json 顺序每课两次，串行创建 10 个 NORMAL 试次；每次从首次提交起最多 1800 秒，翻译 900 秒 deadline 不因恢复重置。期间至少每 10 秒监测精确磁盘比例；超过 85% 停止新任务和隔离测量，保留失败记录，不清理旧证据。
3. 第 11 个 RECOVERY 试次独立报告；至少 2 个批次已提交、约一半计划完成且还有未完成批次时，在验收 barrier 阻止后续派发，再核对专属 PID、start_ticks、cwd、候选 hash 后中断这一 Java worker。恢复同候选，不另建 task、不变更绑定。不得通过暂停整个线上 JVM 或杀 Python 来代替。
4. 中断前后导出同一 task 的 batch/result_hash/attempt_count、attempt、lease epoch、outbox 和 ASR 调用清单。已提交完成批次无新增物理调用，已持久化 ASR 不重跑；未知网络窗口明确 UNKNOWN_OUTCOME。最终译文完整覆盖且严格校验后发布。
5. 资料 HTTP 400 保留私有脱敏响应（最多 4000 字符、长度/截断标记）和请求地址、大小、哈希、安全 options 摘要；不保存全文请求，不修复资料生成行为。

## 导出与费用口径

`evidence-queries.sql` 仅用于新隔离 schema，只导出指定安全字段；不运行 SELECT *，不导出 config_json、resolved_config_json 或任何凭据字段。原文/响应摘录留在私有 .data 下，公开证据只有计数和哈希。

trials.jsonl 每条记录 NORMAL/RECOVERY、课程源 hash、task ID、系统/策略版本、终态、各阶段耗时（未进入为 null）、翻译分段数、拆批/重试数、ASR 片数/物理尝试、token 与费用已知/未知计数。scheduler 按 event_seq 导出原始窗口曲线。10 次正常试次统计成功率、各阶段均值/样本标准差（ddof=1，注明观察样本数）；恢复演示另列，不混入均值。

费用唯一源为 model_call_attempt，包含截断父批、重试及失败；translation_attempt / ai_call_record / V26 diagnostic 是关联与显示，不重复相加。USD DeepSeek 和 CNY ASR 分列，无可信汇率不合并。缺实际 token/未知请求保留未知，已知和仅为下界；高峰/节假日/缓存不确定给区间。静音 ASR 调用、重试、费用是 ASR 总费用的组成，另与旧 180s 切片基线作差分；不能再次加到总额，也不能将差分全部归因于切分而忽略识别输出和输入变化。

完成真实试次后追加 SUMMARY.md/VERIFY.md、原始记录位置及 SHA256SUMS，保留旧基线失败结论。当前不报告时延或费用改善。
