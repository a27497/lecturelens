# 资料生成上下文预检（实验实现，未部署）

课程准备的 `LEARNING_PACKAGE` 请求经过统一的上下文守卫，适用于全文、字幕段落、视觉时间线和质量修复。短输入直接生成；长输入按段落/句子边界分块，超长单段按完整 Unicode 字符拆分，所有证据按顺序进入 map。中间笔记经有界分层 reduce 后生成既有学习资料结构，不直接作为发布产物。

每次调用前估算全部消息，包括系统指令、视觉信息和追加的质量修复要求。当前使用 UTF-8 字节数加聊天模板余量的保守估算，适用于当前 byte-BPE 模型；这是预检估算，不是精确 tokenizer 或供应商计费用量。输入估算必须同时满足：

```
input <= floor(contextLimit * 0.70)
input + maxTokens + contextReserve <= contextLimit
```

超限先拆分或继续归并，不发送已知超限请求。固定指令/最小块无可用空间、笔记无效或截断、归并不收敛、预算耗尽时明确失败；不会静默丢弃尾部证据。模型输出的笔记是有损摘要，完整输入覆盖不等于语义质量已通过。

默认限制：

| 配置 | 默认值 |
| --- | --- |
| `LEARNING_PACKAGE_CONTEXT_LIMIT` | 8192 |
| `LEARNING_PACKAGE_CONTEXT_RESERVE` | 256 |
| `LEARNING_PACKAGE_MAP_MAX_TOKENS` | 512 |
| `LEARNING_PACKAGE_MAX_MODEL_REQUESTS` | 64 |
| `LEARNING_PACKAGE_MAX_REDUCE_LEVELS` | 6 |
| `LEARNING_PACKAGE_GENERATION_TIMEOUT` | 900s |

map 和 reduce 使用512输出token；最终请求仍使用提示工厂的4096。默认最终输入估算上限是3840，map输入估算上限5734。每次请求设置单次尝试并禁用隐式 JSON→纯文本重发，因此 map、reduce、首次生成及质量修复共同受64次派发上限约束；质量修复复用相同证据已生成的 map 笔记，但所有修复消息仍重新预检。各物理调用继续进入原有用量账本，资料阶段的汇总用量包括 map、reduce 和质量修复；缺失用量保留 NULL。

单次 HTTP 超时还受整次生成剩余时间约束。每次调用前重查任务权属、取消、来源 revision、generation、执行事件、租约与任务截止时间，调用仍使用原冻结模型版本。最终发布保留原 generation fence 和质量校验。中间笔记仅在本次生成内存中复用，没有新增持久化恢复点；运行时崩溃后的资料生成不能据此声称 map 零重跑。翻译批次的持久化恢复路径保持原有协议。

## 选配 DeepSeek

系统模型管理已有独立 `LEARNING_PACKAGE` 功能绑定，可选择有 TEXT_CHAT/JSON_OUTPUT 能力的 DeepSeek 模型；无绑定时继续使用捕获的 ENV 默认模型。新任务冻结新绑定，已冻结任务继续原版本，不自动改为其他模型或供应商。见[系统模型管理](SYSTEM_MODEL_MANAGEMENT.md)。

上下文限制应与实际模型/服务端配置一致；模型管理的 `maxTokens` 是输出参数，不代表上下文长度。可在服务配置中设置按模型名的上下文覆盖，例如以下仅示范保守32768上限，并非声明某一供应商最新规格：

```yaml
courselingo:
  learning-package:
    context-limit: 8192
    model-context-limits:
      deepseek-flash: 32768
```

本次不修改在线模型绑定、服务端上下文或供应商账户。候选测试及真实验收状态见 [P2-1c VERIFY](../eval/p2-1c-pipeline-20261016T133927Z/VERIFY.md)。课程准备属于确定性处理流程，不构成 Study Agent 模型自主决策能力证明。

## 后续 P2-1c 实施

后续候选提供显式 `sourceOnly` 资料命令：只读取原文段落和独立视觉观察，不查询全文译文或翻译段，首次生成和质量修复共用此路径。默认命令保持原模式；原文模式仍执行相同权属、执行版本和发布围栏。map 请求附带原文段号、时间范围与内容 hash，按可容纳的完整段落优先切分，超长段继续切分，不扩大原有上下文/调用/时间预算。

不可继续切分的本地上下文超限，以及供应商明确拒绝上下文，返回 `LEARNING_PACKAGE_CONTEXT_LIMIT_EXCEEDED`，以 `LOCAL_PREFLIGHT` / `PROVIDER` 区分来源；预算、超时和格式失败不归入此码。资料保存后记录 `learning_package_outcome`，区分 `MODEL`、`REPAIRED` 和 `DETERMINISTIC_FALLBACK`，不能把退化结果隐去后声称模型质量通过。

这部分尚未启用到真实运行时；本轮测试、独立数据库与真实验收状态见[实施记录](../eval/p2-1c-20261016T155847Z/VERIFY.md)。

确定性 Pipeline 新任务可用 `PIPELINE_MATERIALS_SOURCE_ONLY=true` 冻结原文资料模式；资料步骤重新校验任务的冻结模型引用。`PIPELINE_STREAMING_TRANSLATION`、`PIPELINE_MATERIALS_PARALLEL` 保持 false，本候选明确拒绝开启未合格的重叠执行路径。兼容性验收失败及 C/E 未纳入说明见[阶段 3](../eval/p2-1c-20261016T155847Z/STAGE3.md)。
