# P2-1 验证记录（分阶段更新）

设计基线 `a7ad19aebfdf5b56f5212512737c83da414a9339`；用户确认的 DESIGN.md SHA256 为 `1e0636b669eed750b20fe652c3c8ca933ccde08748be93bc3658440c66945946`，保留未修改。仅本地提交，不 push/merge，不部署或重启现有服务，不调用真实供应商。

## 阶段 1：翻译修复

代码和文档改动 **24 个文件**，逐文件路径及结果哈希见 `stages/stage1-files.json`。新增 V27 执行策略表及不可变更新约束，任务创建事务内冻结策略；默认关闭 v2，只对具有冻结策略的任务使用新路径。系统模型配置版本和凭据存储方式不变。

已实现：DeepSeek 全文非 thinking、动态输出预算、length 优先分类、明确空/格式/语言/网络/HTTP 类别、有界拆分和统一物理尝试预算、无隐式 TEXT fallback、原时间区间保留、失败实际基本 usage 携带。输入预算方法为 `UTF8_CONSERVATIVE_V1`，**不是精确 tokenizer**；未下载新依赖或模型，不能用估计 token 计费。

最终相关测试：**252 项，0 失败、0 错误、0 跳过**，包含独立 MySQL 集成测试。当前只是机制验证，不是 DeepSeek 真实译文或 10 次基线通过。

| 轮次 | 测试 / 失败 / 错误 / 跳过 | 说明 |
| --- | --- | --- |
| stage1-unit-01 | 192 / 2 / 0 / 0 | 架构边界失败：响应解码和安全错误类型放错包；移至 LLM 层，未放宽边界检查。 |
| stage1-unit-02 | 192 / 0 / 0 / 0 | 边界修正后通过。 |
| stage1-mysql-01 | 47 / 1 / 0 / 0 | 旧启动测试夹具缺少 P1-3d 新增诊断 Bean；补齐夹具，未改生产 Bean 的必需性。 |
| stage1-combined-03 | 252 / 0 / 0 / 0 | 全部相关单元及独立 MySQL 回归通过，包含新增截止时间及任务诊断测试。 |

MySQL 容器为本任务新建 `lecturelens-p21-mysql-test-20261016`，只监听 `127.0.0.1:33316`，`/var/lib/mysql` 使用 768 MiB tmpfs，内存限制 1536 MiB、CPU 1、日志最多 2 MiB。未连接 demo/acceptance 数据库，未修改受保护容器。首个容器创建因日志驱动“不允许 max-file=1 且开启压缩”失败；仅移除该未启动的本任务容器，显式关闭日志压缩后创建成功。两次记录均保留。数据库测试使用合成凭据，不读取部署环境或供应商 API Key。

安全及兼容证据：

- `SystemModelTranslationV2Test`：真实响应形状的合成空 content + length 优先归 TRUNCATED，并保留 903/3073/3976 原值；DeepSeek 参数、最终 URL、路由上限、逐段/QA 不变；401/404/429/500/408/400 单次物理请求且不泄露合成密钥；ENV 兼容路径不自动转 TEXT。
- `TranslationBatchCoordinatorTest`：截断缩小源文本、空输出一次纠正、认证无重试、网络/429 共用尝试限额、Retry-After 上限、递归总调用上限、拆分深度、未知 usage 预留、开始前/执行中 deadline、动态输出上限和非法配置。
- `PipelineTranslationServiceTest`：真实服务入口复用严格解析/语义校验，拆分后只提交一份完整原段译文。
- `PipelinePolicyMySqlTest`：V27 迁移、策略冻结后配置改变不影响旧任务、关闭开关仍可读取旧策略、owner 隔离、无凭据字段、禁止 UPDATE、任务删除级联。
- 原字幕服务、解析器、prompt、诊断、OpenAI 兼容 provider、任务创建，以及系统模型文本和 ASR 运行时回归同轮通过。

完整日志和各轮执行参数/磁盘采样：

```text
.data/p2-1-pipeline-20261016T073754Z/checks/stage1-unit-01.{log,json}
.data/p2-1-pipeline-20261016T073754Z/checks/stage1-unit-02.{log,json}
.data/p2-1-pipeline-20261016T073754Z/checks/stage1-mysql-01.{log,json}
.data/p2-1-pipeline-20261016T073754Z/checks/stage1-combined-03.{log,json}
.data/p2-1-pipeline-20261016T073754Z/checks/mysql-test-start.json
.data/p2-1-pipeline-20261016T073754Z/checks/mysql-test-start-02.json
.data/p2-1-pipeline-20261016T073754Z/RAW_SHA256SUMS
```

每轮日志哈希、测试结果及启动/结束/峰值磁盘在 `stages/stage1-checks.json`，不依赖后续会覆盖的 target/surefire-reports。MySQL 表中的 media_identity_hash 是上传记录的固定身份摘要，不能冒充媒体文件 SHA256；真实基线仍须核对原 assets.lock.json。

## 数字与哈希复现

下面只读已存证据，不创建任务或调用模型：

```bash
cd /home/dev/projects/lecturelens
sha256sum eval/p2-1-pipeline-20261016T073754Z/DESIGN.md
sha256sum -c eval/p2-1-pipeline-20261016T073754Z/SHA256SUMS
sha256sum -c .data/p2-1-pipeline-20261016T073754Z/RAW_SHA256SUMS
python3 - <<'PY'
import json,re,hashlib
from pathlib import Path
d=Path('eval/p2-1-pipeline-20261016T073754Z')
files=json.loads((d/'stages/stage1-files.json').read_text())
print('stage1_file_count',len(files))
for run in json.loads((d/'stages/stage1-checks.json').read_text()):
    p=Path(run['log_path'])
    assert hashlib.sha256(p.read_bytes()).hexdigest()==run['log_sha256']
    counts=re.findall(r'^\[(?:INFO|ERROR)\] Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)',p.read_text(),re.M)
    print(run['name'],counts[-1],run['execution']['disk_peak_percent'])
PY
```

再次运行相关测试的**命令参数**位于 `stage1-checks.json` 最后一项 execution.command；需先提供独立本地 `_test` 数据库的 `SYSTEM_MODEL_TEST_JDBC_URL` 等测试环境变量。不能使用业务库。示例的 guard runner 只运行指定检查，有 240 秒超时和每秒磁盘检查，超过 85% 结束检查；每轮使用新 name，拒绝覆盖旧日志：

```text
nohup timeout 300 python3 eval/p2-1-pipeline-20261016T073754Z/run_related_checks.py --name stage1-recheck-NEW --timeout 240 -- ./mvnw -o -Dtest=TranslationBatchCoordinatorTest,SystemModelTranslationV2Test,PipelineTranslationServiceTest,TranslationFailureDiagnosticTest,TaskCreationServiceTest,PipelinePolicyMySqlTest,SystemModelRuntimeMySqlTest,SystemModelAsrMySqlTest,TranslationCallDiagnosticsTest,SystemModelTranslationObservationTest,SubtitleTranslationServiceTest,SubtitleTranslationResponseParserTest,SubtitleTranslationPromptFactoryTest,OpenAiCompatibleLlmProviderTest test > NEW-LAUNCHER.log 2>&1 < /dev/null &
```

## 后续验收范围

阶段 4–5、10 次正常基线和 1 次隔离 Java 恢复演示尚未执行。不会把空 trials 或 mock 成功当作真实测量。重启前另报影响范围并等确认；真正实测还受磁盘余量前置约束。

用户补充已纳入实施：**单节费用包含全部 ASR 调用，静音切分引起的调用数量/费用影响单独列出**。仅把“增量”作为差分说明，不能再加到已包含全部 ASR 的总费用上重复计费。若供应商没有返回实际计费单位，明确未知或目录价估算；跨币种没有可信汇率时保留各币种组成，不伪造统一总额。当前阶段未进行费用测量。

## 阶段 2：静音切分、时间来源与对齐发布

阶段 1 提交：`98b0cd4d1798ee74acce15098fd9b34d6e81ea95`。本阶段代码/文档文件和 SHA256 在 `stages/stage2-files.json`；阶段提交记录在 `stages/commits.json`，当前提交的 hash 在提交后汇报、后续阶段写入，避免自引用。

新任务冻结 v2.2；旧 v2.1 序列化不增加 null 字段，不被重解释。默认切分策略 -35 dB / 600ms / 15–30–60s / 最多 256 片，冻结采样参数、ASR 并发、尝试数、退避及大小限制。ASR 适配器在任务开始只获取一次，所有切片和重试使用同一个适配器。静音模式显式走 ASR；旧任务保持原嵌入字幕优先行为。

FFmpeg 检测输出最多 256 KiB，截断必须明确失败；以静音边界优先、时长/供应商大小限制兜底，标注短尾、语音孤岛、文件上限与强制时长原因。切片在 worker 内按需生成、出网前校验大小、每次请求结束清理，不预先落盘整节全部切片。区间只来自实际音频切片或服务商有效 ASR 时间；不对字符作时间插值。秒级展示向外取整，保留毫秒值及来源，不声明词级精度。

V28 除设计中的 paragraph/member 外增加 **timing_plan**（切片计划与 ASR 尝试计数只存一份）及 **alignment_publication**（最终译文绑定确切源指纹）。这两个辅助表分别支持用户补充的 ASR 费用归因、以及防止原文变化后同索引旧译文被误配；没有增加独立译文副本或跨服务状态。旧字幕行明确标记 ESTIMATED，新对齐结果拒绝把它当作精确时间来源。最终发布事务校验源指纹，原文/译文按相同原子成员构建 paragraph；源变更、成员缺失、未发布与跨 owner 均不能得到错误对齐。

最终相关测试 **222 / 0 失败 / 0 错误 / 0 跳过**。其中有真实本地 FFmpeg 合成音频集成测试（20 秒音调 + 10 秒静音 + 20 秒音调），验证检测边界、按需物化的 WAV 时长与区间一致，无供应商调用。其他证据包括独立 MySQL V28 迁移、对齐先完整发布后可读、源变化/成员删除拒绝、清理级联、两种时间来源、冻结 ASR 适配器/重试参数，以及原字幕/ASR/翻译回归。

所有尝试保留：`stage2-compile-01` 因误写 AsrChunkingProperties 包名编译失败；`stage2-related-02` 为 198 项、1 错误（延迟物化前旧日志先读取文件）；修正后 `stage2-related-03` 为 221 项通过。最后补正常时长片段不得误标短段的测试，`stage2-related-04` 为 222 项全通过。没有放宽原测试。

日志：`.data/p2-1-pipeline-20261016T073754Z/checks/stage2-{compile-01,related-02,related-03,related-04}.{log,json}`。每轮命令、哈希、磁盘前后/峰值见 `stages/stage2-checks.json`。沿用本任务独立内存盘 MySQL，没有新增或重启 Java worker，没有变更系统 v10 或调用真实 ASR。

阶段 2 数字/日志复现：将上方数字复现脚本中的 `stage1-files.json`、`stage1-checks.json` 分别替换为 `stage2-files.json`、`stage2-checks.json`，跳过没有 result 的编译轮次；每轮测试参数在 execution.command，使用新的 --name 重新执行以免覆盖证据。文件列表记录阶段时点，后续改动须在该阶段 commit 上通过 `git show <commit>:<path>` 校验，不拿旧 hash 强行匹配新工作树。

## 阶段 3：token 批量与动态并发

阶段 2 提交：`7f9f915902ab868d00e1ada050d14f63534572f1`。本阶段代码/文档变更及哈希见 `stages/stage3-files.json`。

新任务冻结 v2.3；旧 v2.1/v2.2 不增加 null 字段，不套用新并发。输入按完整消息的保守 token 预算装箱，超限原子项出网前拆分；顺序、原段时间和一一映射保留。并发从 1 起，连续 3 次校验成功 +1，最大 4；429/timeout 减半，最低 1，旧拥塞窗口迟到失败不重复减半。模型重试仍由唯一控制器管理，不能绕过阶段 1 的总调用/预算/deadline。

同供应商的多个任务共享进程级 4 个名额。获取共享名额后重新检查窗口和冷却，窗口缩小时不超发，不取消已健康请求。事件写入失败释放所有名额并明确失败，不留下许可泄漏。V29 保存逐任务状态和有序事件：时间、batch/attempt、old/new window、inflight、windowEpoch、streak、reason 和 cooldown；同任务重新打开显式记 RECOVERY_RESET（真正任务恢复及旧 worker epoch fence 在阶段 4）。

相关测试 **125 项、0 失败、0 错误、0 跳过**。原始日志 `.data/p2-1-pipeline-20261016T073754Z/checks/stage3-related-01.log`，参数/峰值等见同名 JSON 与 `stages/stage3-checks.json`。机制覆盖 token 装箱、超限出网前拆分、20 个合成批次实际并行且顺序保持、窗口增长/减半/上限、不同任务共享许可、观测失败不泄漏许可、取消唤醒、5xx 不额外减半，以及真实独立 MySQL 的事件顺序/重置/owner/级联。这里的 20 是 mock 调用数，不是真实课程或翻译质量成绩。

数字和日志复现沿用上述脚本，将阶段文件名替换为 stage3；实际测试命令在 `stages/stage3-checks.json` 的 execution.command。未重启、部署或调用真实供应商，未修改系统绑定。
