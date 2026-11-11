# Java DeepSeek 请求与输出协议

本文描述当前源码，不代表部署或真实模型验收。[部署身份](DEPLOYMENT.md#study-agent-候选部署与回滚)和运行 JAR 应独立核对。

## 请求参数

`OpenAiCompatibleRequestOptionsAdapter` 对以下明确列出的模型 ID 设置 `thinking: {type: "disabled"}`：

- `deepseek-flash`
- `deepseek-v4-pro`
- `deepseek-v4-flash`
- `deepseek-v4-flash-vision-exp`

依据 2026-10-19 的[官方思考模式](https://api-docs.deepseek.com/guides/thinking_mode/)与[官方模型和兼容别名](https://api-docs.deepseek.com/)。`deepseek-flash` 当前由 DeepSeek-V4.1-Flash-1017 提供；后两个旧 ID 是官方接受的兼容别名，不表示已退役模型仍在提供服务。产品版本名称不是 API ID；未对 `DeepSeek-V4.1-Flash-1017`、任意包含 deepseek 的字符串、未知代理命名或其他历史 ID 猜测参数支持。

| Java 入口 | 参数与结果处理 |
| --- | --- |
| 普通 OpenAI-compatible 文本 Provider，JSON / TEXT | 公共参数适配器；正文映射前拒绝 `length` |
| 系统模型 DATABASE 路由 | 公共适配器；QA、章节、字幕翻译、学习资料等共用 `SystemModelChatClient` |
| 系统模型 ENV 路由 | 委托普通文本 Provider，沿用快照、参数上限及安全错误边界 |
| 旧对齐翻译 / 全文翻译 V2 | 同一公共参数适配器，继续使用各自解码与有界恢复策略 |
| 普通及系统视觉 Provider | 系统视觉委托公共视觉请求构建器，输出截断返回失败结果 |
| 管理员显式连通性探测 | 公共适配器；固定 32 token、单次请求，不将截断 JSON 当成探测成功 |
| 可选 LangChain4j Provider | 通过 SDK customParameters 使用同一 DeepSeek 策略；保留其他供应商在此客户端的原参数 |

现有直接请求路径的 Qwen3 `enable_thinking=false` 与 Qwen3-VL 排除规则不变。没有改变模型、路由、max_tokens、超时、并发或调用预算。关闭思考不保证输出一定能在原预算内完成。

## 输出与失败边界

HTTP 成功后，`finish_reason=length` 优先于空正文检查和正文 JSON 解析。空正文、部分 JSON、可解析的完整 JSON 均不能覆盖供应商声明的截断。失败使用既有 `TranslationFailure` 的 `TRUNCATED / OUTPUT_TRUNCATED` 契约，保留可用的 HTTP 状态、usage 和白名单 finish_reason；异常不携带响应正文、请求头、凭据或原始异常 cause。

DeepSeek 的普通空输出保留为 `EMPTY_OUTPUT`，与截断区分。视觉失败结果及探测结果新增可选 `outputDiagnostics`，仅包含受限原因、HTTP 状态、usage、finish_reason。其他供应商原有普通空输出行为保持不变。SDK 成功对象未暴露原始 HTTP 状态时使用 null，不推测为 200。reasoning token 仅在响应或 SDK 明确提供时保留；缺失时为 null，不能把全部 completion_tokens 归因为思考。

视觉 Provider 只将截断和空输出转换为可返回的失败结果；记账不完整、取消和快照失效等控制异常仍按原路径向上传播，不能降级吞掉。

| 路径 | 截断后的处理 |
| --- | --- |
| 普通文本 / 系统 Provider | 终止当前物理请求，不触发 HTTP 重试或 structured-output 格式回退；上层仍受已有策略约束 |
| QA / 学习资料 | 既有服务层处理安全失败，不保存这次截断正文为成功产物 |
| 章节 | DATABASE 路由不增加 TEXT 恢复；其他路由原有的一次有界 TEXT 恢复、内容修复及确定性回退保持原条件和预算；被截断的候选本身不可发布 |
| 旧对齐翻译 | 既有受限拆分 / 深度检查继续适用，只发布完整校验后的产物 |
| 全文翻译 V2 | 既有冻结策略控制拆分、调用和 token 预算，不在 Provider 内新增重试 |
| 视觉 / 连通性探测 | 返回失败及安全元数据，不额外重试此输出，不发布截断正文 |

没有改变既有私有诊断存储策略；私有脱敏响应片段不属于公开错误信息，也不是可恢复的批次 checkpoint。

## 重试和恢复是不同操作

`TaskCommandServiceImpl.retry` 会使用原上传记录和语言创建新 task，不复制旧 task 的模型快照、ASR 或翻译批次。新 task 在创建时冻结当前系统配置；只有当前配置恰好仍为旧版本时，版本数字才会相同。

当前源码另有独立 `/tasks/{taskId}/resume` 路径：原 task 必须已经使用支持恢复的冻结策略、protocol v2、有效 source checkpoint，并通过所有权、来源、epoch、租约、截止时间及剩余预算检查。符合条件时可恢复原 ASR 来源，跳过已成功的翻译批次并保持原快照。普通 retry 不等价于 resume。

新源码的 ASR 分块 checkpoint / 可选缓存还受同用户、音频 hash、配置 identity、TTL、源 task 未删除等条件约束。历史部署没有生成这些记录时，更新代码不会自动补出旧 checkpoint 或缓存；不能仅凭仍存在字幕行就保证恢复可用。

## 离线验证范围

[JavaDeepSeekProtocolTest](../backend/src/test/java/com/example/courselingo/systemmodel/JavaDeepSeekProtocolTest.java) 经过实际请求构建及响应处理：普通 JSON/TEXT、系统 DATABASE/ENV、两种翻译、普通/系统视觉、探测和真实 SDK 到本机假 HTTP 端点。覆盖正常输出、三类截断正文、附带 reasoning 明细的截断、普通空正文、官方别名及非 DeepSeek 参数回归。即使可用尝试数为 3，截断也仅产生一次 Provider 请求。

配套回归覆盖 QA、章节、视觉、翻译恢复、调用错误分类和任务重试。测试使用合成响应，不代表生产数据库、部署兼容性或真实模型内容质量通过。
