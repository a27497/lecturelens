# 全文翻译 v2（实验候选，未部署）

Java 媒体准备流程的翻译修复，不属于 Python Study Agent 决策运行时。当前阶段 1–5 已实现，尚未部署或完成真实课程验收。设计及验收记录见 [P2-1](../eval/p2-1-pipeline-20261016T073754Z/DESIGN.md)。

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

旧任务 lease/retry 语义不变；v2.4 支持同任务检查点恢复。失败调用已知 usage 保存在物理调用账本；阶段显示与诊断不再作为额外费用相加。不能用 mock 通过结果宣称十节真实基线已通过。

阶段 2 新任务冻结 `translation-v2.2` 策略；旧 v2.1 策略可继续解析，不套用新切分。静音模式显式选择 ASR，旧任务的嵌入字幕优先策略不变。静音阈值 -35 dB、停顿 600ms、段长最短/目标/最长 15/30/60 秒，最大 256 片；尾段、语音孤岛及文件限制导致的短段标注原因。长静音跳过，全静音明确 NO_SPEECH。切片在 ASR worker 内按需生成、请求结束后清理；并发、重试数、退避和文件上限随策略冻结，整个任务只获取一次 ASR 适配器。

`timing_source` 区分 ASR、SILENCE_SPLIT、AUDIO_CLIP、EMBEDDED_SUBTITLE 和 ESTIMATED。无供应商时间戳时只记录真实音频片区间，不按字数均分；秒显示采用覆盖区间取整，不承诺词级精度。旧字幕行默认 ESTIMATED。全文结果可选 `alignedParagraphs` 保留成员索引、原译文一一对应及时间来源，旧字段保留。

V28 增加时间来源列、段落/成员、切分计划及源指纹发布记录。原子字幕译文仍是唯一翻译结果，段落译文按相同成员拼接；未完整发布、源指纹改变或成员缺失不能返回错误的对齐结果。静音切分的全部 ASR 物理尝试计入单节费用；调用数和成本影响单独列出，不能把增量再加一次。当前只保存计数/计划，实际用量和费用账本在阶段 5 补齐。

阶段 3 新任务冻结 v2.3：按完整消息的 token 估计预算装箱，默认 2048；单项超限在出网前拆小，仍保留原段对应关系。真实请求并发初始 1、最多 4，连续 3 次通过校验后 +1，429/timeout 减半，最低 1。同一拥塞窗口的迟到失败不重复减半，冷却与 Retry-After 有界；其他失败遵守原有界策略。已经运行的健康请求继续完成。等待供应商共享名额后会再检查最新窗口，避免用旧窗口超发。

`PIPELINE_TRANSLATION_AIMD_ENABLED` 默认为 true（外层 v2 仍默认 false）。`PIPELINE_TRANSLATION_INPUT_TOKEN_BUDGET=2048`、`PIPELINE_TRANSLATION_CONCURRENCY_INITIAL=1`、`PIPELINE_TRANSLATION_CONCURRENCY_MAX=4`、`PIPELINE_TRANSLATION_SUCCESS_STREAK=3`、`PIPELINE_TRANSLATION_PROVIDER_MAX_INFLIGHT=4` 随新任务冻结。供应商共享上限在同一进程的多个任务之间生效，不承诺跨实例全局限流。V29 保存窗口状态及有序原始事件；恢复窗口显式从 1 重置，不能把新参数替换到旧快照。

阶段 4 新任务冻结 v2.4；`PIPELINE_TRANSLATION_CHECKPOINT_ENABLED=true`、`PIPELINE_TRANSLATION_MAX_RECOVERIES=3`。外层 v2 仍关闭；启用恢复必须同时声明 `PIPELINE_TRANSLATION_ISOLATED_RUNTIME=true`，且 RocketMQ topic/group 均以 `lecturelens-p21-` 开头，否则启动报错。不能将带 epoch 的新消息发到旧消费者所在 topic。V30 必须先在隔离 schema 迁移，未部署到业务库。

批次的任务/序号/配置版本为唯一键；源、请求、初始计划和截止时间不可变，拆分树持久化。真实调用前登记 STARTED 并预留预算，校验通过后用量与结果同事务提交；已提交批次恢复时不调用供应商。进程丢失的 STARTED 记 UNKNOWN_OUTCOME，保留预算，不伪造 token。外部调用和本地提交间存在不可消除的崩溃窗口，未提交批次可能再次计费。

90 秒执行 lease、15 秒 heartbeat、30 秒恢复扫描保持原默认。恢复增加 epoch，并在同一事务排入 durable outbox；重复/旧 epoch 无法变更当前状态。新 worker 直接读取原执行快照，不重新 freeze 或访问当前配置头；全局/叶批预算、15 分钟翻译 deadline 和原始 30 分钟整任务 deadline 均不重置。旧 worker 迟到只允许补记已发生的用量，不得发布或覆盖；取消/删除永不恢复。

转写已持久化时，从权威字幕行校验指纹恢复，跳过音频提取、ASR 和原文重写。关键帧捕获完成标记和对象身份一致时跳过捕获；OCR/分析仍由既有指纹与 generation fence 管理。旧 epoch 的对象使用独立命名空间，不能覆盖新 worker 的对象。失败 v2 保留恢复所需 Evidence 到原任务期限，过期后经清理 outbox 清理派生对象；源上传不删。任务授权删除同时清理私有检查点，保留删除边界。媒体对象缺失仍由读取/分析路径明确失败，不宣称数据库标记等价于底层对象持久性。

`POST /api/tasks/{taskId}/resume` 携带 `expectedExecutionEpoch`；未登录 401、非 owner 404、不可恢复/并发 epoch 冲突 409。仅失败且仍在原预算、原媒体身份和原期限内的 v2.4 任务可恢复；原 `/retry` 继续创建新任务。最终字幕、全文和段落对齐发布在同一事务再次检查源、owner、epoch 和 deadline。

阶段 5 新任务冻结 v2.5 和 `catalog-20261016` 价格集；旧策略缺少新字段时维持原序列化和行为。V31 的 `model_call_attempt` 是唯一物理调用费用来源，覆盖处理链中的全文翻译、资料、视觉和 ASR（普通浏览器 QA 的独立 operation 不受 worker lease 限制）。每次 HTTP 派发前登记，返回后记录输入/输出/推理/缓存 token、耗时、finish_reason 和安全错误类别；未知值为 NULL，并记录缺失/进程中断原因。STARTED 未完成入账不能发布任务成功；旧 epoch 可补记已发生的用量事实，不能发布译文。

翻译预算/恢复仍由 translation_attempt 管理，并通过 attempt_id 关联物理账本与 V26 诊断。语义校验失败更新同一物理调用的错误子项，既有阶段 ai_call_record 读取累计用量（有未知项时保留未知），包括失败阶段。不能把三张表再相加计费；父批截断和全部子调用则各是真实请求，必须计入。

价格卡在首次适用调用前落库且不可修改；DeepSeek 官方主机 / deepseek-flash 才使用其价格，其他代理或模型不猜价。美元价格按 [官方目录](https://api-docs.deepseek.com/quick_start/pricing/)（2026-10-16）冻结，推理 token 已含于输出；缺缓存细项、高峰/节假日或跨边界不确定时给上下界，缺用量则费用未知。当前百炼北京 qwen-audio-3.1-asr-flash 使用 [官方目录](https://help.aliyun.com/zh/model-studio/model-pricing)（同日）输入 0.8 / 输出 2.7 元每百万 token，按实际 usage 计算；不拿音频时长当 token。其他未核实价卡的 ASR 明确 UNPRICED，不填零。

ASR 的每个物理尝试保留实际切片区间、来源和静音计划哈希。单节费用分别汇总 DeepSeek USD、ASR CNY 与其他已知/未知组成，不擅自换汇；静音片数、重试和费用影响单列，但属于 ASR 总额的一部分。费用是目录价估算，不代表账号折扣/免费额度或最终账单。

资料 HTTP 400 仅在私有账本保存脱敏后最多 4000 字符响应、大小/截断标志，以及请求地址、大小、哈希和安全参数摘要；不存请求全文、头或凭据。没有修改资料生成请求/解析来修复 400。账本和私有响应没有公开 API。供应商响应 model / fingerprint 只保存哈希以识别变化，不能成为未脱敏文本的旁路。

相关验证与候选哈希见 [VERIFY](../eval/p2-1-pipeline-20261016T073754Z/VERIFY.md)。首次授权隔离试次发现 MQ transport payload 丢失 v2/epoch，任务未进入媒体处理即取消；补丁保留这两个字段，旧消息仍省略空字段，48 项相关回归通过。用户另行授权新候选及仅保留本轮 Redis key 原样复用；[P2-1b 独立实测](../eval/p2-1b-pipeline-20261016T122904Z/SUMMARY.md)十次翻译10/10发布、完整链路0/10（资料输入超过现有模型上下文，均400）。第11个独立恢复任务在ASR返回403，未达到中断点、未执行SIGKILL，真实恢复演示未完成。新路径仍未部署；不能把机制测试或翻译覆盖宣称整课教学质量通过。
