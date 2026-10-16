# 全文翻译 v2（实验候选，未部署）

Java 媒体准备流程的翻译修复，不属于 Python Study Agent 决策运行时。当前阶段 1–3 已实现；批次恢复和完整费用账本按后续阶段交付。设计及验收记录见 [P2-1](../eval/p2-1-pipeline-20261016T073754Z/DESIGN.md)。

默认 `PIPELINE_TRANSLATION_V2_ENABLED=false`。开启时仅新任务在创建事务内生成 `pipeline_policy_snapshot`，固定系统执行快照、翻译策略、模板哈希和从任务创建起 30 分钟的截止时间。关闭开关不会改变已冻结任务。策略只包含安全参数；凭据仍从既有系统版本按版本号解密，不保存到执行策略中。

阶段 1 的 v2 全文调用在官方 DeepSeek `deepseek-flash` 路由中显式发送 `thinking={"type":"disabled"}`，保留 `response_format=json_object`。参数依据 [DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/) 和 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/)（2026-10-16 查阅）。其他功能与旧路径保持现有请求行为。

输入规划目前使用 `UTF8_CONSERVATIVE_V1`：消息 UTF-8 字节数、角色/封装余量及 1.10 安全系数，**是保守估算，不是官方 tokenizer 或实际 token 用量**。没有引入未经核实的 tokenizer/本地模型依赖。输出上限按输入估计动态计算，默认 `clamp(2 × input + 128, 512, 8192)`，并遵守冻结模型路由上限及保守上下文限制。费用不得用该估计计算。

请求先解析实际 usage 与 finish_reason，再检查 content。`length` 优先归为 TRUNCATED，自动缩小批次，不能把空正文当正常结果。空输出/格式/语言有一次内容纠正机会；429、超时、网络及 5xx 做有界退避；401/403、模型不存在和确定性 4xx 立即失败。v2 底层 HTTP 层每次只发一个请求，不叠加旧重试或 TEXT fallback。严格索引、数量、覆盖及语言校验保留。

每叶批最多 3 次物理调用、拆分深度最多 6、整任务最多 256 次调用和 200000 token 规划预算；未知实际用量保留预留预算，不能计作零消耗。全文预算 15 分钟、单请求 120 秒，且均受任务剩余时间限制。文本子片合并回原字幕段，保留原时间区间，不制造更细时间戳。

可配置环境变量：

| 变量 | 默认 |
| --- | ---: |
| `PIPELINE_TRANSLATION_OUTPUT_MIN` / `PIPELINE_TRANSLATION_OUTPUT_MAX` | 512 / 8192 |
| `PIPELINE_TRANSLATION_OUTPUT_RATIO` | 2.0 |
| `PIPELINE_TRANSLATION_CONTEXT_LIMIT` | 32768 |
| `PIPELINE_TRANSLATION_SPLIT_MAX_DEPTH` | 6 |
| `PIPELINE_TRANSLATION_LEAF_MAX_ATTEMPTS` | 3 |
| `PIPELINE_TRANSLATION_MAX_CALLS` | 256 |
| `PIPELINE_TRANSLATION_TOKEN_BUDGET` | 200000 |

启用时校验参数范围；非法配置明确失败。Flyway V27 为增量迁移，不修改 V22–V26。部署前必须迁移新表；不应只替换 JAR 后连接未迁移的数据库。本轮没有部署或启用线上配置，系统模型绑定保持原值，LangChain4j 继续默认关闭。

当前尚不提供崩溃后同任务恢复，旧任务 lease/retry 语义不变；失败调用的已有私有诊断保留已知基本 usage，但阶段汇总尚不能作为完整费用账本。不能用 mock 通过结果宣称十节真实基线已通过。

阶段 2 新任务冻结 `translation-v2.2` 策略；旧 v2.1 策略可继续解析，不套用新切分。静音模式显式选择 ASR，旧任务的嵌入字幕优先策略不变。静音阈值 -35 dB、停顿 600ms、段长最短/目标/最长 15/30/60 秒，最大 256 片；尾段、语音孤岛及文件限制导致的短段标注原因。长静音跳过，全静音明确 NO_SPEECH。切片在 ASR worker 内按需生成、请求结束后清理；并发、重试数、退避和文件上限随策略冻结，整个任务只获取一次 ASR 适配器。

`timing_source` 区分 ASR、SILENCE_SPLIT、AUDIO_CLIP、EMBEDDED_SUBTITLE 和 ESTIMATED。无供应商时间戳时只记录真实音频片区间，不按字数均分；秒显示采用覆盖区间取整，不承诺词级精度。旧字幕行默认 ESTIMATED。全文结果可选 `alignedParagraphs` 保留成员索引、原译文一一对应及时间来源，旧字段保留。

V28 增加时间来源列、段落/成员、切分计划及源指纹发布记录。原子字幕译文仍是唯一翻译结果，段落译文按相同成员拼接；未完整发布、源指纹改变或成员缺失不能返回错误的对齐结果。静音切分的全部 ASR 物理尝试计入单节费用；调用数和成本影响单独列出，不能把增量再加一次。当前只保存计数/计划，实际用量和费用账本在阶段 5 补齐。

阶段 3 新任务冻结 v2.3：按完整消息的 token 估计预算装箱，默认 2048；单项超限在出网前拆小，仍保留原段对应关系。真实请求并发初始 1、最多 4，连续 3 次通过校验后 +1，429/timeout 减半，最低 1。同一拥塞窗口的迟到失败不重复减半，冷却与 Retry-After 有界；其他失败遵守原有界策略。已经运行的健康请求继续完成。等待供应商共享名额后会再检查最新窗口，避免用旧窗口超发。

`PIPELINE_TRANSLATION_AIMD_ENABLED` 默认为 true（外层 v2 仍默认 false）。`PIPELINE_TRANSLATION_INPUT_TOKEN_BUDGET=2048`、`PIPELINE_TRANSLATION_CONCURRENCY_INITIAL=1`、`PIPELINE_TRANSLATION_CONCURRENCY_MAX=4`、`PIPELINE_TRANSLATION_SUCCESS_STREAK=3`、`PIPELINE_TRANSLATION_PROVIDER_MAX_INFLIGHT=4` 随新任务冻结。供应商共享上限在同一进程的多个任务之间生效，不承诺跨实例全局限流。V29 保存窗口状态及有序原始事件；恢复窗口显式从 1 重置，不能把新参数替换到旧快照。
