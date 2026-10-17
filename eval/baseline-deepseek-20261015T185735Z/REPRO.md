# P1-3d：翻译观测与一次真实复现

2026-10-15 UTC。观测代码提交：`bc2e6cc79f1a3311b90cc4d407f75d2e20048275`。本轮只新增观测；未修改翻译 prompt 文本、HTTP 参数、校验条件、错误分类/重试决策、并发、超时或功能绑定。最终仍保留 DeepSeek 配置版本 10。未 push、合并或重启 agent-service。

## 结果与根因

**本次直接失败项是 CONTENT_EMPTY：DeepSeek 返回 HTTP 200，但最终 content 是空字符串，finish_reason 为 length，且 reasoning_content 非空。生成在给出最终译文之前因长度限制结束，客户端原有的非空检查据此抛出 OUTPUT_INVALID。** 这次不是翻译字段、分段数量或中文校验拒绝译文，也不是“不支持 JSON mode”的 HTTP 拒绝。

| 项目 | 证据值 |
| --- | --- |
| 新任务 | `task_1b5dd375008544258544f7b6f3a2001c`；只创建 1 次，未重投 |
| 来源 | 原 P1-3 的 economics / MIT OCW 第一讲；复用已完成上传 `up_b5618740a8c248b3b163a379b9b30c74` |
| 视频身份 | `116afb01df8dc39dc048273a91ce9e03df793a6cda12364d19b165da43e56222`（SHA256）；原 CC BY-NC-SA 4.0 归属见旧基线 SOURCES.md |
| 冻结执行 | snapshot `a846fab4-158b-4bb7-88d6-ac3c76b1b5c6`；configVersion=10；DATABASE；deepseek-flash |
| 地址 | `https://api.deepseek.com/chat/completions`，沿用原请求构造 |
| 首批输入 | 1 个分段；原始分段索引 0；输入 3093 字符；prompt 3999 字符 |
| 请求 | JSON_OBJECT；max_tokens=3072；timeout=120000 ms；maxAttempts=3；未发送关闭 DeepSeek thinking 的参数 |
| 返回 | HTTP 200；content=""；reasoning_content 非空；finish_reason=length |
| 用量（供应商原值） | prompt_tokens=903；completion_tokens=3073；total_tokens=3976 |
| 调用 | 物理调用 1 次，provider_attempt=1；无实际 HTTP 重试；成功批次 0，失败批次 1 |
| 耗时 | 提取 8724 ms；ASR 104849 ms；翻译阶段到失败 17431 ms；调用观测 17312 ms；提交到终态观察 132646.959 ms |
| 终态 | FAILED / TRANSLATE；未进入资料生成，不构成模型学习质量验收 |
| 磁盘 | 任务监测峰值 84.8966563433369%；结束复核 84.81246703111945%；未超过 85% |

供应商返回 completion_tokens=3073，比请求上限 3072 多 1；按原值保留，不将其改成 3072，也不自行解释供应商计数边界。直接的长度终止证据是 finish_reason=length。当前没有单独记录 reasoning_tokens，因此不能声称 3073 全部是思考 token。

本次响应确实包含非空 reasoning_content，结合请求没有关闭 thinking，支持“当前生成预算在最终译文形成前耗尽”的判断。DeepSeek 当前官方说明 thinking 默认开启；JSON mode 文档同时提示空 content 与输出截断问题，见 [Thinking Mode](https://api-docs.deepseek.com/guides/thinking_mode/)、[JSON Output](https://api-docs.deepseek.com/guides/json_mode/)（2026-10-15 查阅）。这支持优先验证 thinking/预算组合，不支持把历史 10 次失败全部追认成同一原因：历史原响应仍然缺失，P1-3c 的未知结论保留。

## 按子项分类

| 校验位置/子项 | 成功批次 | 失败批次 | 本次证据 |
| --- | ---: | ---: | --- |
| 客户端 content 非空检查 / CONTENT_EMPTY | 0 | 1 | 空字符串；原异常类别保持 OUTPUT_INVALID |
| 外层 JSON 解析 | 1 | 0 | 已解析到 choices、usage 与 finish_reason |
| 内层 content JSON 解析 | 0 | 0 | 非空检查已失败，未执行 |
| 翻译字段 / FIELD | 0 | 0 | 未执行 |
| 分段数量/索引 / SEGMENT_COUNT | 0 | 0 | 未执行 |
| 业务截断检查 / LENGTH | 0 | 0 | LlmResult 未返回，业务检查未执行 |
| 语言 / LANGUAGE、整节最终校验 | 0 | 0 | 未执行 |

同一调用另有供应商终止原因 length=1，不能把它与 CONTENT_EMPTY 再相加成两次失败。“外层解析成功 1”也不是成功翻译批次。所有业务 validation 字段为 NULL，表示未到达，不能记成 PASSED。

## 原始响应与用量证据

任务诊断行：`4befe79c-b79f-46ac-9341-66cf6fc53b10`，表 `translation_call_diagnostic`。完整收到的 body 长度 11337 字符，按要求在脱敏后只保存前 4000 字符（response_truncated=1）。**没有保存完整 body**；finish_reason 和 usage 在未截断的内存响应中提取为独立列，随后原响应不再持久化。

以下是为阅读整理的字段投影，非完整原始 JSON；reasoning 正文不复制到 Git 文档：

```json
{
  "choices": [{"message": {"content": "", "reasoning_content": "[非空，正文仅在私有截断诊断中]"}, "finish_reason": "length"}],
  "usage": {"prompt_tokens": 903, "completion_tokens": 3073, "total_tokens": 3976}
}
```

精确的脱敏截断响应在本机：

- `/home/dev/projects/lecturelens/.data/baseline-deepseek-20261015T185735Z/p13d/response-excerpt.txt`
- 同目录 `diagnostics-with-excerpts.json`：数据库诊断行及其 response_excerpt。
- 截断响应 UTF-8 SHA256：`950bcb648c94bbf4d16ce8e60726edec98274d9c1502a416b542a9f2cee97fb8`。
- `p13d/diagnostics.json`：可提交的字段投影及逐响应摘要哈希；`p13d/RAW_SHA256SUMS`：本次私有证据哈希。供应商原始响应和课程全文不进 Git。

实际用量现在已持久化在**逐物理调用诊断表**，即使终止任务的这一批 content 无效也保存 903/3073/3976。原 `ai_call_record` 仍是既有阶段汇总语义，失败阶段的 token 列仍可能 NULL；本轮没有改其 API、阶段聚合或错误返回。核算本次失败调用应读新表，不能继续用该旧 NULL 推断零用量，也不能把两张表重复计费。

## 实现与测试

改动 10 个代码/迁移/测试文件，完整清单：`p13d/code-files.json`。

- `SystemModelChatClient.java:111` 起记录外层解析、缺失/null/空/非字符串 content、内层解析、非 object 的不同原因；原 invalid() 异常、校验条件和重试行为保持不变。finally 写入每次物理调用，返回结果只携带诊断 ID。
- `TranslationCallDiagnostics.java:37` 写入独立事务；按 snapshot/task/user/configVersion 校验关联。不将响应、请求头或凭据放入日志、审计、异常或任务结果 API。先替换本次运行凭据（包括 JSON 转义形式），再处理常见凭据字段/Bearer/sk-模式，最后截断 4000 字符。
- `SubtitleTranslationServiceImpl.java:611`、`:639`、`:647`、`:650` 只旁路记录原有截断、字段/数量/解析与语义检查结果；`:337` 起记录整节 coverage 和语言检查结果。没有新增宽松解析、重试、拆分条件、供应商回退或 prompt 文本。
- V26 只新增私有表，不更改业务表/系统版本表。诊断随执行快照删除级联清理；本轮不增加查询接口。观测写入失败只记固定警告，不带 SQL 参数、响应或异常 cause，不改变原翻译结果。
- prompt factory 仅新增诊断 metadata（输入字符和源索引），不会进入 messages 或 HTTP body。原请求 JSON mode、max_tokens、timeout、concurrency 保持原值。

相关测试共 **115 项，0 失败、0 错误、0 跳过**：客户端观测 9；诊断持久化/脱敏/权限/事务/级联 15；翻译服务 81；响应解析器 7；prompt 3。首轮曾因诊断 INSERT 占位符数量错误导致 3 项 H2 用例错误，修正后两轮通过（113、115）；失败日志保留在私有目录，不覆盖或当成真实模型试次。

只跑上述相关 Java 测试与打包，未运行全量 Java、前端或 Python runtime 测试；没有修改 agent-service。原始日志：`p13d/checks/java-related-tests.log`、`p13d/checks/backend-build.log`；明细：`p13d/checks/test-summary.json`。

## 部署与影响范围

沿用既有生产 Java 启动器和环境，只原子替换 JAR、重启 `lecturelens-live-backend`。更新前活动分析任务为 0；Java PID 2659162 → 3251334。Flyway V26 成功、/actuator/health=UP。agent-service PID=5102、llama PID=5105，PID 与 start_ticks 均未变；RocketMQ 未重启。未修改 ASR 路由或环境；本任务仍走原 ASR 配置。无生产流程以外的部署。

`p13d/deployment-intent.json` 含新旧 JAR 哈希、代码提交和部署前磁盘；`deployment-result.json` / `final-check.json` 含迁移、健康、进程和结束检查。管理员 catalog 前后完全一致（`catalog-before.json` / `catalog-after.json`），系统配置仍 v10，其他功能的有效配置没有变化。新日志无 translation_diagnostic_write_failed；sk-/Bearer 凭据模式扫描通过，未读取实际供应商密钥进行比对，不把模式扫描当成所有可能密钥形态的数学证明。

本机备份：私有目录 `backend-before.jar` 为旧 JAR 硬链接（不复制占用），`flyway-before.sql.gz` 为迁移历史备份，无供应商凭据表。需要撤回观测版本时先确认无活动任务，用该旧 JAR 原子替换当前部署 JAR，再只重启 Java；V26 表保持不动，旧版不消费它。此次未执行回滚。

## 修复建议（未实施）

优先单独验证 DeepSeek 显式非 thinking 参数 `thinking={"type":"disabled"}`，仍保持 JSON mode、完整译文/索引校验和原供应商；它直接针对“先产生 reasoning、最终 content 未生成就结束”的观察。风险是行为与译文质量变化，需要作为新候选、在另行授权的有限真实调用中验证，不能仅凭 mock 宣称质量改善。

备选是在保留 thinking 时提高生成预算，或减小输入分段；风险是费用、尾延迟或请求数上升，不保证消除所有空输出。当前 max_tokens=3072 与实际 length 终止直接相关，但本轮不改预算或分段。

还可在后续把“空 content + finish_reason=length”报告成明确的长度原因，并有界恢复；这会改变现有判定/重试行为，应另做改动与测试。本轮只观察，仍按原逻辑报 OUTPUT_INVALID。无需为本例放宽 JSON/schema/语言校验，也不建议把 reasoning_content 当成译文。

## 复现与核对命令

以下命令只读证据/数据库，不重新调用模型：

```bash
cd /home/dev/projects/lecturelens
python3 eval/baseline-deepseek-20261015T185735Z/p13d_verify.py
sha256sum -c eval/baseline-deepseek-20261015T185735Z/SHA256SUMS
sha256sum -c eval/baseline-deepseek-20261015T185735Z/RAW_SHA256SUMS
sha256sum -c eval/baseline-deepseek-20261015T185735Z/p13d/RAW_SHA256SUMS
```

数据库限定查询（不会打印 response_excerpt 或凭据）：

```bash
python3 - <<'PY'
import sys
sys.path.insert(0, 'eval/baseline-deepseek-20261015T185735Z')
from support import sql
print(sql("""SELECT JSON_OBJECT('provider_reason',provider_reason,'http_status',http_status,
'finish_reason',finish_reason,'prompt_tokens',prompt_tokens,'completion_tokens',completion_tokens,
'total_tokens',total_tokens,'excerpt_chars',CHAR_LENGTH(response_excerpt),'config_version',config_version)
FROM courselingo.translation_call_diagnostic
WHERE task_id='task_1b5dd375008544258544f7b6f3a2001c' AND user_id=9"""))
PY
```

如需重跑相关单元测试（不是真实模型复现）：

```bash
cd /home/dev/projects/lecturelens/backend
./mvnw -Dtest=TranslationCallDiagnosticsTest,SystemModelTranslationObservationTest,SubtitleTranslationServiceTest,SubtitleTranslationResponseParserTest,SubtitleTranslationPromptFactoryTest test
```

真实任务的原执行命令是下列 nohup + timeout 命令，**仅供审计，不要自动重放**。驱动已存在 submission-intent.json，会拒绝再次创建任务；此次没有删除该保护标记：

```text
nohup timeout 1900 python3 eval/baseline-deepseek-20261015T185735Z/p13d_reproduce.py --run-authorized-one-task > .data/baseline-deepseek-20261015T185735Z/p13d/reproduce.log 2>&1 < /dev/null &
```

## 磁盘停止与本次补交

前次真实任务已结束后，封存阶段检测到磁盘约 85.58%，已停止继续提交；该读数不属于前述单任务运行峰值。用户随后仅授权处理 trials.jsonl 的十个上传临时目录。

本次检查时间：北京时间 `2026-10-16T14:49:32.324933+08:00`（UTC `2026-10-16T06:49:32.322337+00:00`）。十个精确路径在检查前已全部不存在；十个上传均为 STORED，11 条关联任务记录均为 FAILED。对全局 lsof 文件描述符清单按十个路径逐个匹配，包括已删除但仍被打开的文件名，结果为 0；由于目录已不存在，没有把 `lsof +D` 的“路径不存在”报错当成检查通过。

本次实际删除目录 **0**，本次删除实际释放 **0 字节**，未扩大清理范围。检查后磁盘精确占用 `84.503865%`，低于 85%，因此继续补交证据。`df -h` 的 Use% 向上取整可能仍显示 85%，不等于精确占用达到阈值。检查清单、SQL 状态、lsof 结果和 df 原文见 `p13d/upload-temp-cleanup.json`。remotion、puppeteer、日志、镜像、卷、受保护容器及原始证据均未修改；未重新调用模型或重启服务。
