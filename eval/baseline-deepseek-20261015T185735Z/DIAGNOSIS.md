# P1-3c：DeepSeek 翻译 OUTPUT_INVALID 只读诊断

诊断日期：2026-10-15 UTC。基于 P1-3b 冻结证据及当前 MySQL 的限定列只读查询；数据库核对时间为 `2026-10-15T19:38:11Z`。未改业务代码、配置或绑定，未调用模型、未重启、未提交。只新增本文件；原 SHA256SUMS / RAW_SHA256SUMS 不改写。

## 1. 能确认到哪一层

**10 次任务都在系统模型客户端层以 OUTPUT_INVALID 终止，未进入该失败批次的翻译 schema、数量、长度或语言校验。现有证据无法再区分这 10 次各自是空 content、外层 JSON 解析、内层 JSON 解析、非 object，还是其他被合并的客户端异常。** 不应把它们统计成“JSON 解析失败 10 次”。

证据链：

- 私有原始日志：`/home/dev/projects/lecturelens/.data/baseline-deepseek-20261015T185735Z/logs/<task_id>.json`。每个终止批次都有 `system_model_call_completed outcome=FAILED category=OUTPUT_INVALID configVersion=10`，随后为 `llm_aligned_batch_translation_failed`；没有对应的 completed 事件。
- 已提交日志投影：`events/`；原始日志比投影多出 inputCharCount、promptChars、outputLength 等字段，批次比较必须使用原始日志。
- `database-call-diagnostics.json` 中 10 条 TRANSLATION 记录均 FAILED、error_code=OUTPUT_INVALID、retryable=0；本次实时 SELECT 逐列与留档一致。model 和三项 token 列均为 NULL；这表示失败记录丢了模型与用量，不代表实际未调用模型。模型由 `snapshots/` 与绑定前置证据确认。
- 十份执行快照均冻结 v10、TRANSLATION_FULL_TEXT 来源 DATABASE、模型 deepseek-flash；最终地址由请求构造及原验收记录确定为 `https://api.deepseek.com/chat/completions`。本次没有重新发送请求。
- 原部署 JAR 的 SHA256：`74ce36c807ce2e16cdb7a372dd73efe70bbf88bbf1ec08caac717a7bc82ead01`，见 `runtime-identity.json`。当前 HEAD `64e722c29a7da1213334fdf76d1d0b112cd3cf1f` 与部署代码提交 `13f8fc0` 的 backend 差异为空。

按可证实的终止原因分类：

| 类别 | 已确认次数 | 解释 |
| --- | ---: | --- |
| 客户端通用 OUTPUT_INVALID，具体子项丢失 | 10 | 全部终止失败；下表逐任务定位 |
| 已单独证实的外层/内层 JSON 解析错误 | 0 | 无原响应或解析异常类型；真实数量未知，包含在上行 |
| 已单独证实的空/缺失/非字符串 content 或非 object | 0 | 同上，真实数量未知 |
| 翻译字段缺失、索引/分段数量不符 | 0 | 本组终止批次未到达该层，并非检查后全部通过 |
| 翻译长度、截断或语言检查失败 | 0 | 未到达业务检查层；不能据此排除供应商实际截断 |

“0”指零次可证实记录，不能把未知子项相加得到额外失败次数。原始日志中也未出现 JSON_PARSE_ERROR、INCOMPLETE_JSON、EMPTY_RESPONSE、TARGET_LANGUAGE_MISMATCH、UNTRANSLATED_TEXT、OUTPUT_TRUNCATED 或解析器异常栈。

下表批次序号按每个任务的 started 事件从 1 计数；耗时是该失败批次，不是整节翻译耗时。每次都是单分段、语义 attempt=1、httpStatus=null、retryable=false。

| 试验 | task_id | 终止批次 | 输入字符 | prompt 字符 | 失败批次耗时 ms | 具体校验项 |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| algorithms-1 | task_012ad9c1ea20484491aa7ceaa039a8b9 | 10 | 1484 | 2390 | 16698 | 客户端 OUTPUT_INVALID；子项未留存 |
| calculus-1 | task_2f672dd2acb6401c800d53f8830ca7f3 | 1 | 2159 | 3065 | 16038 | 同上 |
| economics-1 | task_8255462bb195479893e67ba63fff27a1 | 1 | 3092 | 3998 | 16708 | 同上 |
| linear-1 | task_d24f7945cfb344289c35c40d94cd47a8 | 3 | 2106 | 3012 | 13476 | 同上 |
| probability-1 | task_824f8160998147e7b7d66a8a33fd0834 | 2 | 2691 | 3597 | 14673 | 同上 |
| algorithms-2 | task_27eabe74454a47b885f005ac81bbe9dc | 4 | 2452 | 3358 | 13358 | 同上 |
| calculus-2 | task_f7d4ccf68ed644e680b6c406d869312f | 3 | 1712 | 2618 | 13559 | 同上 |
| economics-2 | task_7a09477a6dd24cc49ee0ffd645704fad | 1 | 3093 | 3999 | 15237 | 同上 |
| linear-2 | task_1ed8e0722acb4b28ac7409215e08e1f4 | 1 | 1683 | 2591 | 14348 | 同上 |
| probability-2 | task_6544116ea9e448a1b12d57e5786fe74a | 7 | 2551 | 3457 | 15085 | 同上 |

## 2. 样本与期望格式

只有一类可确认失败，取两个样本。以下为日志元数据摘录，均少于 2000 字符，**不是 DeepSeek 原始响应**；不包含请求头或密钥。

```text
样本 A：algorithms-1 / 批次 10
inputCharCount=1484 promptChars=2390 segmentCount=1
system_model_call_completed configVersion=10 outcome=FAILED category=OUTPUT_INVALID durationMillis=16695
llm_aligned_batch_translation_failed providerErrorCategory=OUTPUT_INVALID httpStatus=null providerErrorCode=null retryable=false responseFormatUsed=JSON_OBJECT attempt=1 batchSegmentCount=1 batchInputChars=1484 durationMillis=16698
DeepSeek 原始响应：[未持久化，无法展示或重建]

样本 B：economics-1 / 批次 1
inputCharCount=3092 promptChars=3998 segmentCount=1
llm_aligned_batch_translation_failed providerErrorCategory=OUTPUT_INVALID httpStatus=null providerErrorCode=null retryable=false responseFormatUsed=JSON_OBJECT attempt=1 batchSegmentCount=1 batchInputChars=3092 durationMillis=16708
DeepSeek 原始响应：[未持久化，无法展示或重建]
```

客户端期望：HTTP 为 2xx，响应外层是可解析的 JSON，`choices[0].message.content` 为非空字符串，该字符串还必须能解析为 JSON object。然后业务解析器期望 content 结构如下（**格式示例，非真实输出**）：

```json
{"segments":[{"index":0,"text":"对应输入分段的完整中文译文"}]}
```

本组每批只有一段，prompt 要求 batch-local index=0、恰好一个非空 text，不输出源文、Markdown 或额外字段。业务解析器实际上也兼容原始分段索引，并未强制拒绝所有额外字段。

原始响应缺失范围：失败 10 批及成功 23 批的 HTTP body、content、finish_reason 都没有归档。`results/*.json` 私有文件保存 ASR 原文与最终结果视图；十份 translatedFullText / translations 均为空。日志只保存事件元数据，没有响应体或 Jackson cause。`observe_local_errors.py:26` 的被动观察器只接收 `127.0.0.1:8091` 的本地模型响应，且仅为 HTTP 400 留证；它没有观察 HTTPS DeepSeek。不能用 ASR 原文或模板生成假响应来补这个缺口。

## 3. 与成功 23 批比较

从原始日志配对得到 33 个逻辑批次：23 completed、10 failed。completed 事件发生于业务解析之前；这里每个 completed 后又启动了下一批，且没有语义重试/拆分日志，结合并发=1及提交下一批的位置，可以确认这些早先批次已通过 schema 与批次语义校验。但没有一节课完成全文翻译或通过最终整节校验。

下表均值±标准差使用样本标准差（n−1）。字符为 Java 日志中的 length 口径；不是 token。

| 指标 | 成功 23 批 | 失败 10 批 |
| --- | --- | --- |
| 每批分段数 | 全部 1 | 全部 1 |
| 输入字符范围；均值±SD | 1601–2700；2257.000±325.329 | 1484–3093；2302.300±572.019 |
| prompt 字符范围；均值±SD | 2507–3606；3163.087±325.169 | 2390–3999；3208.500±571.779 |
| 批次耗时 ms 范围；均值±SD | 5335–14744；10632.957±2711.569 | 13358–16708；14918.000±1269.353 |
| 输入 prompt_tokens | 未持久化到逐批日志；不可得 | 不可得 |
| total_tokens（输入+输出） | 合计 66657；1628–3731；2898.130±626.582 | 不可得，不按零计 |
| content 字符数 | 535–843；712.391±91.155 | 不可得 |
| 请求 max_tokens / timeout / maxAttempts | 3072 / 120000 ms / 3 | 相同 |
| prompt 模板 | alignedBatch 普通首次模板 | 同一模板，无语义重试模板切换 |

v10 的模型配置未覆盖上述三个请求参数，客户端 max_tokens 取路由与请求已配置值的较小者。`max_tokens=3072` 是生成预算，不能拿 total_tokens（含输入）大于 3072 推断违规或截断。maxAttempts=3 是上限，失败日志 attempt=1 是语义轮次；现有日志无法恢复供应商 HTTP 实际重试次数。

反例：algorithms-1 第 10 批仅 1484 输入字符仍失败；probability-2 第 3 批 2700 字符、prompt=3606、total_tokens=3731、content=837 字符成功。失败均值只比成功略大，区间大量重叠，不能据此归因为“输入太长”。失败耗时更集中也不足以证明固定 token 上限耗尽。

33 批都使用相同源/目标语言与模板；变化项是 ASR 文本、原始分段索引及 JSON 转义后的长度。没有逐批 prompt_tokens/completion_tokens，无法比较输入 token 分布；不以字符估算冒充供应商返回用量。

## 4. 代码定位与原因判断

路径前缀均为 `backend/src/main/java/com/example/courselingo/`；行号对应当前代码，与部署版本 backend 无差异。

| 位置（文件:行号） | 行为及影响 |
| --- | --- |
| `systemmodel/SystemModelLlmProvider.java:59`（DB 分支 69） | 冻结快照 DATABASE 直接调用 SystemModelChatClient，无其他供应商回退 |
| `systemmodel/SystemModelChatClient.java:59`、`:66` | 构造 max_tokens 与 response_format=json_object；不是 Responses 协议 |
| `systemmodel/SystemModelChatClient.java:92`–`:96` | 外层解析 → content 非空字符串 → 内层必须 object；任何一步失败均无法返回 LlmResult |
| `systemmodel/SystemModelChatClient.java:117`、`:137` | 泛化 catch 及 invalid() 丢弃具体原因，统一 OUTPUT_INVALID/httpStatus=null/retryable=false；还覆盖请求序列化异常（70–73） |
| `systemmodel/SystemModelHttpClient.java:87`–`:99` | 正常传输超时/网络异常保留独立 TIMEOUT/NETWORK 类型；本组没有这些类型。不能把通用异常覆盖风险直接说成这 10 次都是网络或超时，也不能仅凭空 HTTP 状态补写为 200 |
| `subtitle/service/SubtitleTranslationServiceImpl.java:636`（调用 678；失败 691） | 全文路线发 alignedBatch 请求；provider 抛异常时直接包装阶段失败 |
| `subtitle/service/SubtitleTranslationServiceImpl.java:583`、`:598`、`:616` | LlmResult 返回后才依次检查 finish_reason 截断、业务 JSON/schema、语言语义；本组终止批次尚未执行这些逻辑 |
| `subtitle/service/SubtitleTranslationResponseParser.java:30`、`:96`、`:184`、`:209` | 非空/segments 数组、JSON_PARSE_ERROR/INCOMPLETE_JSON、数量/索引、text 类型/非空/敏感文本检查 |
| `subtitle/service/SubtitleTranslationResponseParser.java:110` | 业务解析器可清理单层 Markdown fence、解一层 JSON 字符串；前面的客户端 object 检查会提前拒绝这些形式 |
| `subtitle/service/SubtitleTranslationServiceImpl.java:727`（756–770） | 检查复制原文、中文比例与完整英文散文；不是本组可确认的终止原因 |
| `subtitle/service/SubtitleTranslationServiceImpl.java:1227` | 整节最终空文本、复制源文和中文检查；十任务均未到达。不存在可用于解释本组的固定“译文最短长度”错误记录 |
| `subtitle/service/SubtitleTranslationServiceImpl.java:1098` | 通用 OUTPUT_INVALID 不携带 EMPTY_RESPONSE/INCOMPLETE_JSON 等细分标识，无法触发这些已知输出错误的拆分恢复路径 |
| `subtitle/service/SubtitleTranslationPromptFactory.java:100`（134、139、179） | 首次 alignedBatch 模板，显式 JSON_OBJECT、JSON 示例、逐段 index 与非空译文约束 |
| `subtitle/service/SubtitleTranslationPromptFactory.java:81` | “Do not return JSON” 属于另一条逐段 TEXT prompt，不是本组全文模板，不能归因为该句与 JSON mode 冲突 |
| `ai/llm/OpenAiCompatibleRequestOptionsAdapter.java:17` | 只有 Qwen3 的 enable_thinking 适配，没有 DeepSeek thinking 开关；默认行为由供应商决定 |

判断：

1. **确定的工程缺陷：错误细分及调用证据丢失。** 精确失败项、finish_reason 和用量在最早层就丢了；这是当前不能确认根因的直接原因。
2. **prompt 基本约束已经齐全。** 模板含 JSON 字样、object 示例、数量和中文要求，没有“完全忘记要求 JSON”的证据。可以改良，但无法断言是约束不足造成这 10 次失败。
3. **客户端比业务解析器更严格，存在确定的处理顺序不一致。** 如果响应只是 fence 或双重编码 JSON，会在可兼容它的解析器之前失败；是否实际出现过，未知。缺字段、少分段、非中文不应为通过率而放宽。
4. **不支持 response_format 的归因缺乏依据。** 官方 JSON Output 文档直接用 deepseek-flash 展示 json_object，并要求 JSON 提示与格式样例，当前请求满足这些基本条件；文档同时承认偶发空 content、提醒预算不足可能截断。因此“空 content”与“截断”都是候选原因，不能从当前记录中确定各自次数。[DeepSeek JSON Output](https://api-docs.deepseek.com/guides/json_mode/)、[Chat Completions API](https://api-docs.deepseek.com/api/create-chat-completion/)（2026-10-15 查阅，检索缓存非现场响应证据）。
5. **默认 thinking 与 3072 生成预算的组合值得优先验证，但仍是假设。** 官方当前文档称 thinking 默认 enabled、effort=high；本地未发送关闭参数。没有失败 finish_reason、reasoning token 计数或逐批 usage，不能据此断言“10 次都耗尽思考预算”。不应将 reasoning_content 当译文或记录其正文。[DeepSeek Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)（2026-10-15 查阅）。

## 5. token 用量为何没有持久化，应在哪补记

有三处丢失，既影响失败批次，也影响失败任务中早先成功的批次：

1. `systemmodel/SystemModelChatClient.java:97` 在 content 校验之后才读取 usage；校验抛异常后，即使供应商已返回计费用量也不会进入 LlmResult。finish_reason 同样在成功返回处（108）才取出。
2. `subtitle/service/SubtitleTranslationServiceImpl.java:449` 的 results 只在整节完成后返回；某批异常在 484–490 重抛，已成功批次的结果不会形成正常 run 返回。usage 汇总在 330、1566，仅走整节成功路径。23 条日志只保住 totalTokens=66657，没有 prompt/completion 或缓存拆分。
3. `task/runner/TranslateSubtitleSegmentsStep.java:79` 转成失败记录；`PipelineAiCallRecord.java:108` 的 failed 工厂把 token/批次指标置 NULL；`WriteAiCallRecordStep.java:77` → `ai/record/dto/FailAiCallRecordCommand.java:3` 没有 token 字段；`ai/record/service/AiCallRecordServiceImpl.java:94` 的 failCall 也不写 token。因此十条 DB 失败记录均 NULL 是当前数据流的结果。

建议补记位置（仅设计，未实施）：

- 客户端一旦拿到可解析外层响应，**先提取安全标量** HTTP 状态、模型、finish_reason、usage（prompt/completion/total、缓存 hit/miss、可用时 reasoning token 数量）、内容类型/长度与内部 validationReason，再校验 content；失败异常携带这些脱敏指标。外层无法解析或传输失败时保持 usage 未知，不填零，不伪造状态。
- 在每次物理 HTTP 尝试结束处持久化独立的脱敏调用度量，关联 task/snapshot/configVersion/feature/batch/attempt；确保“已计费但内容无效”和“前几批成功、整节失败”均保留。重试按物理调用计费、任务汇总避免重复相加；不依赖整个阶段成功才能记录。
- 扩展失败记录的数据载体、FailAiCallRecordCommand/校验器/service/mapper，使现有 ai_call_record token 列能保存失败前已知的度量，并区别已知部分与完整汇总。保留原错误，不能因度量落库失败覆盖任务失败原因。
- 仅在受限诊断模式留存脱敏 content 前 2000 字符及截断标记，避免放入普通日志/审计/API；不保存 Authorization、凭据、完整请求文本或 reasoning_content。优先默认只记错误细分、长度和哈希，样本权限与保留期另行设计。

本次无法补回失败 10 批的准确 token，也无法把 66657 拆成输入/输出或缓存命中；这部分费用仍应标为未知，不能据此宣称零费用或完整账单。

## 6. 修复候选及风险（均未实施）

| 方案 | 适用条件与验证方式 | 风险 |
| --- | --- | --- |
| A：先补错误分类与逐调用用量（建议首步） | 区分 ENVELOPE_JSON_INVALID、CONTENT_EMPTY、CONTENT_JSON_INVALID、CONTENT_NOT_OBJECT，保留 finish_reason/usage；用 mock 覆盖含 usage 的失败响应、正常网络/超时及整节部分成功 | 记录重复、遗漏与隐私风险；需验证重试计数和崩溃恢复，不能直接放开原始 body 日志 |
| B：增加 DeepSeek 显式非 thinking 选项 | 单独能力配置，仅作用全文翻译；mock 验证请求参数，再经授权做新候选实验；与保持 thinking 的候选独立比较 | 行为/质量会变；不能重标旧基线，不应扩散到其他功能或无条件按模型名称猜测 |
| C：若细分证明 length/预算不足，调整生成预算或减小输入批次 | 保持总任务上限、授权预算；重新冻结配置与候选身份；验证中文完整性及逐段覆盖 | 更多 token 费用、请求数和尾延迟，不能保证解决偶发空 content；本组连短输入也失败 |
| D：若证明 fence/双重编码，统一有界 JSON 规范化 | 仅接纳明确单层包装，之后仍执行 object/schema/数量/语言校验；mock 覆盖歧义、多 object、尾随垃圾和截断 | 宽松修复可能接受错误内容；禁止补括号猜 JSON、执行模型文本或放宽缺段校验 |
| E：针对可识别空输出/截断做有限重试或拆分 | 在 A 后只针对明确可恢复错误；继续用原冻结快照、原供应商，记录每次用量，尊重取消/截止时间 | 增加费用与时延；持续无效响应仍失败，不能无限重试或自动回退供应商 |
| F：精简 prompt、补一组最小输入/输出示例 | 作为独立候选，与同一组冻结输入比较；继续要求 JSON 与 index 完整性 | 当前模板已具备基本约束，单改 prompt 未必触及根因，可能损害术语与完整译文质量 |

建议顺序 A → 根据细分证据选择 B/C/D/E，F 单独测。先用确定性 mock 验证协议/失败记录，再在另行授权、受限预算下测试真实质量；本轮只读结论不构成修复已验证。

## 7. 复现命令（全部只读，无模型请求）

以下从 `/home/dev/projects/lecturelens` 执行；不运行 measurement driver、observer 或 collect_final（它们可能写记录或调用服务）。

### 7.1 留档完整性、代码身份

```bash
cd /home/dev/projects/lecturelens
sha256sum -c eval/baseline-deepseek-20261015T185735Z/SHA256SUMS --quiet
sha256sum -c eval/baseline-deepseek-20261015T185735Z/RAW_SHA256SUMS --quiet
git diff 13f8fc0 64e722c --stat -- backend
git status --short
```

诊断开始与写入前均通过两个 manifest 检查；本文件不加入旧冻结 manifest。原有公开/私有证据保持原哈希。

### 7.2 逐批配对、失败明细、全部比较数字与缺失字段

```bash
python3 - <<'PY'
import collections, json, pathlib, re, statistics
p = pathlib.Path('eval/baseline-deepseek-20261015T185735Z')
raw = pathlib.Path('.data/baseline-deepseek-20261015T185735Z')
trials = {x['task_id']: x['trial_id'] for line in (p/'trials.jsonl').read_text().splitlines()
          if (x := json.loads(line)).get('task_id')}
rows, events = [], collections.Counter()
for f in sorted((raw/'logs').glob('*.json')):
    ordinal, current = 0, None
    for s in json.loads(f.read_text()):
        d = dict(re.findall(r'([A-Za-z][A-Za-z0-9]*)=([^\s]*)', s.split('message=', 1)[-1]))
        e = d.get('event', '')
        events[e] += 1
        if e == 'llm_aligned_batch_translation_started':
            ordinal += 1
            current = dict(trial=trials[f.stem], task=f.stem, ordinal=ordinal, **d)
        elif e in ('llm_aligned_batch_translation_completed', 'llm_aligned_batch_translation_failed'):
            assert current is not None
            current.update(d)
            current['outcome'] = 'OK' if e.endswith('_completed') else 'FAIL'
            rows.append(current)
            current = None
    assert current is None
assert len(rows) == 33 and sum(x['outcome'] == 'OK' for x in rows) == 23
for r in rows:
    if r['outcome'] == 'FAIL':
        print('failure', {k: r.get(k) for k in ('trial','task','ordinal','inputCharCount',
              'promptChars','batchSegmentCount','durationMillis','providerErrorCategory',
              'httpStatus','attempt','retryable')})
for outcome in ('OK', 'FAIL'):
    cohort = [r for r in rows if r['outcome'] == outcome]
    print(outcome, 'count', len(cohort))
    for k in ('segmentCount','inputCharCount','promptChars','durationMillis','totalTokens',
              'outputLength','maxTokens','maxAttempts','requestTimeoutMillis'):
        z = [int(r[k]) for r in cohort if r.get(k, '').isdigit()]
        print(k, dict(n=len(z), min=min(z), max=max(z), sum=sum(z),
              mean=round(statistics.mean(z),3), sd=round(statistics.stdev(z),3)) if z else 'UNKNOWN')
print('recovery events', {k:v for k,v in events.items()
      if any(t in k for t in ('semantic','split','fallback','retry','aligned'))})
for f in sorted((p/'snapshots').glob('*.json')):
    data = json.loads(f.read_text())
    print('snapshot', f.name, [(s['configVersion'], s['routes']['TRANSLATION_FULL_TEXT']['source'],
          s['routes']['TRANSLATION_FULL_TEXT']['model']) for s in data])
for f in sorted((raw/'results').glob('*.json')):
    d = json.loads(f.read_text())
    print('stored_translation', f.stem, bool(d['translatedFullText']), len(d['translations']))
terms = ('JsonParseException','JsonEOFException','MISSING_SEGMENT','UNEXPECTED_SCHEMA',
         'EMPTY_RESPONSE','JSON_PARSE_ERROR','INCOMPLETE_JSON','TARGET_LANGUAGE_MISMATCH',
         'UNTRANSLATED_TEXT','OUTPUT_TRUNCATED','finish_reason','reasoning_content','"choices"')
logs = [s for f in (raw/'logs').glob('*.json') for s in json.loads(f.read_text())]
print('diagnostic_term_counts', {t:sum(t in s for s in logs) for t in terms})
# 仅输出两个样本的事件元数据，不输出请求、ASR 原文或凭据。
for task in ('task_012ad9c1ea20484491aa7ceaa039a8b9', 'task_8255462bb195479893e67ba63fff27a1'):
    lines = json.loads((raw/'logs'/f'{task}.json').read_text())
    print('sample', task, [s.split('message=',1)[-1][:2000] for s in lines
          if 'event=llm_aligned_batch_translation_failed ' in s])
PY
```

### 7.3 当前 DB 与冻结诊断逐列核对

只选择任务白名单的诊断列，不访问系统配置版本内容、凭据或环境清单。MySQL 登录由容器已有环境在进程内提供，命令不会输出该值。

```bash
python3 - <<'PY'
import json, pathlib, re, subprocess
p = pathlib.Path('eval/baseline-deepseek-20261015T185735Z')
ids = sorted({x['task_id'] for line in (p/'trials.jsonl').read_text().splitlines()
              if (x := json.loads(line)).get('task_id')})
assert len(ids) == 10 and all(re.fullmatch(r'task_[0-9a-f]{32}', i) for i in ids)
q = """SELECT JSON_OBJECT('task_id',task_id,'stage',stage,'status',status,
'model',model,'provider',provider,'error_code',error_code,'error_message',error_message,
'retryable',retryable,'prompt_tokens',prompt_tokens,'completion_tokens',completion_tokens,
'total_tokens',total_tokens) FROM courselingo.ai_call_record
WHERE stage='TRANSLATION' AND task_id IN (""" + ','.join("'"+i+"'" for i in ids) + ') ORDER BY task_id;'
r = subprocess.run(['docker','exec','-i','lecturelens-demo-l2-mysql-1','sh','-c',
    'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" exec mysql -u root --batch --raw --skip-column-names'],
    input=q, text=True, capture_output=True, check=True)
rows = [json.loads(line) for line in r.stdout.splitlines()]
old = json.loads((p/'database-call-diagnostics.json').read_text())
assert len(rows) == 10
for x in rows:
    frozen = next(b for b in old if b['task_id'] == x['task_id'] and b['stage'] == 'TRANSLATION')
    assert all(x[k] == frozen[k] for k in x)
    print(x)
print('live DB matches frozen diagnostics:', len(rows))
PY
```

### 7.4 定位校验器、prompt 与用量落库

```bash
rg -n 'readTree|isTextual|isObject|var usage|catch|invalid\(' backend/src/main/java/com/example/courselingo/systemmodel/SystemModelChatClient.java
nl -ba backend/src/main/java/com/example/courselingo/subtitle/service/SubtitleTranslationPromptFactory.java | sed -n '100,207p'
nl -ba backend/src/main/java/com/example/courselingo/subtitle/service/SubtitleTranslationResponseParser.java | sed -n '30,129p;184,224p'
nl -ba backend/src/main/java/com/example/courselingo/subtitle/service/SubtitleTranslationServiceImpl.java | sed -n '449,490p;552,630p;727,772p;1098,1142p;1227,1258p;1566,1577p'
nl -ba backend/src/main/java/com/example/courselingo/task/runner/TranslateSubtitleSegmentsStep.java | sed -n '62,98p'
nl -ba backend/src/main/java/com/example/courselingo/task/runner/PipelineAiCallRecord.java | sed -n '108,140p'
nl -ba backend/src/main/java/com/example/courselingo/task/runner/WriteAiCallRecordStep.java | sed -n '59,87p'
nl -ba backend/src/main/java/com/example/courselingo/ai/record/dto/FailAiCallRecordCommand.java
nl -ba backend/src/main/java/com/example/courselingo/ai/record/service/AiCallRecordServiceImpl.java | sed -n '94,109p'
```
