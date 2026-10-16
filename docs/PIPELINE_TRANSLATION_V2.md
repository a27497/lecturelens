# 全文翻译 v2（实验候选，未部署）

Java 媒体准备流程的翻译修复，不属于 Python Study Agent 决策运行时。当前仅阶段 1 已实现；静音切分、AIMD、批次恢复和完整费用账本按后续阶段交付。设计及验收记录见 [P2-1](../eval/p2-1-pipeline-20261016T073754Z/DESIGN.md)。

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

阶段 1 尚不提供崩溃后同任务恢复，旧任务 lease/retry 语义不变；失败调用的已有私有诊断保留已知基本 usage，但阶段汇总尚不能作为完整费用账本。不能用阶段 1 的 mock 通过结果宣称十节真实基线已通过。
