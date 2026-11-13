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

## 阶段 4：批次持久化与同任务恢复

阶段 3 提交：`0d64acd6e888b11cabc4fdcf54701e2f5067f7b1`。改动及文件哈希见 `stages/stage4-files.json`，每轮测试命令/日志哈希见 `stages/stage4-checks.json`。新任务策略 v2.4，默认外层关闭；启用检查点要求隔离声明和独立 `lecturelens-p21-` MQ topic/group，禁止混用旧消费者。

V30 增加 plan/batch/attempt/step checkpoint，执行 lease 和 outbox 携带 protocol/epoch。批次唯一键为 task+batch+configVersion，拆分树稳定且唯一；DB trigger 禁止改变输入/期限及已完成结果。已完成批次和原文恢复不重跑；未完成请求保留 UNKNOWN_OUTCOME 与预留预算，不承诺外部 exactly-once。恢复通过原 snapshot 读取配置，未调用 current-head freeze；显式 resume 认证/owner/expected epoch 分别验证 401/404/409。

相关测试最终 **326 项、0 失败、0 错误、0 跳过**；包含真实独立 MySQL 迁移、事务/锁/唯一键/触发器。检查点测试模拟 worker 在部分成功和 STARTED 后丢失，在恢复前将系统配置头从 0 改为 1，恢复仍持有 0；已完成批次的调用数、结果哈希和 attempt_count 不变，父批/拆分子批同样验证。另验并发 resume 仅一条事件、旧 MQ/epoch 不能推进状态、旧 finally 不能关闭新 lease、旧成功响应只能补记用量、最终发布事务回滚、重复领取、持久预算、取消/删除、跨 owner 清理及原 ASR/MQ/用户翻译回归。测试中的版本号与文本为合成 fixture，不是实际系统 v10 或真实模型结果。

原文恢复通过权威字幕行指纹验证；恢复跳过 ASR/原文写入和已完成关键帧捕获。v2 失败不立即清掉恢复必需的 Evidence，原任务期限到达后由清理 outbox 清理派生对象，授权删除同时删私有检查点。ASR 派发、源写入和最终发布检查当前 epoch/deadline，旧 worker 的对象路径按执行身份隔离。费用完整性待阶段 5。

原始尝试保留：compile01/02 编译通过；checkpoint03 为 4 项通过；related04 为 225 项、1 失败（发布回滚测试错误期待原异常，实际按契约安全转换 ACCOUNTING_INCOMPLETE）；related05 为 326 项、1 错误（新夹具未覆盖 pipeline 全步骤）；修正夹具和断言后 related06 为 326 项全部通过，没有放宽业务校验。日志均在 `.data/p2-1-pipeline-20261016T073754Z/checks/`，含全部失败轮次。

数字复现：沿用前文校验脚本，将文件名换成 stage4；最终数字取 stage4-related06.log 的最后一个 Tests run 行，命令参数及磁盘峰值在同名 JSON。没有运行全量测试，没有重启/部署或真实调用，系统绑定未动。10 次真实基线和 1 次独立恢复演示仍待阶段 5、磁盘余量和隔离 Java 启动确认。

## 阶段 5：全物理调用用量与冻结目录价

阶段 4 提交：`ebb2c89e80d8577ecc696ff95a42658cae2e397d`。阶段 5 代码/文档文件与哈希在 `stages/stage5-files.json`；全部轮次日志/复现参数/磁盘峰值在 `stages/stage5-checks.json`。构建出的候选 JAR 路径、SHA256、字节数、31 个迁移在 `candidate-artifact.json`。没有部署或启动该 JAR。

最终相关 Java 测试 **417 项、0 失败、0 错误、0 跳过**，含独立真实 MySQL V31、事务/锁/恢复验证及本地 mock HTTP，不是供应商或真实课程质量成绩。阶段计数有重叠，不相加为独立测试数。`stage5-final05.log` 最后一条 Tests run 为最终数；该日志和对应 JSON 的 hash 已封存。`stage5-package06` 单独 `-DskipTests package` 成功，不把构建的跳过测试当作测试通过。本轮未修改 Python 或前端，也未运行其全量测试；按授权只跑相关层。

新策略 v2.5 固定 `priceSet=catalog-20261016`，旧策略 null 新字段不改变旧 hash。V31 新增 **model_call_attempt** 作为唯一费用账本、不可变 model_price_card；补充 translation_attempt 的推理/缓存/用量状态/校验子项，以及 V26 的 attempt_id。新增物理表覆盖 ASR/资料/视觉而非只翻译，是用户要求静音 ASR 费用和全链路失败调用用量的直接依赖；原 checkpoint 表仍管理翻译恢复预算，不再重复当账单相加。

每次真实 HTTP 前先持久化 STARTED/安全摘要；出网后保存实际 usage、HTTP/finish/error、耗时、模型/fingerprint 哈希。翻译父批、失败、拆分子批均计费。语义失败更新同一 receipt；失败调用的阶段 ai_call_record 也透传账本用量，任何部分未知则保留 null，不凭估算填零。V26 仍是私有诊断，不能作为第二份费用。旧 worker 可追加已发生的用量，任务删除不重建；恢复将旧 STARTED 标记 UNKNOWN_OUTCOME / PROCESS_INTERRUPTED。入账失败阻止最终任务成功，普通浏览器 QA 的独立 operation 不要求处理链 worker lease（新增回归覆盖）。

ASR 在实际 HTTP 边界记录每片和重试，包括 ENV 百炼/SiliconFlow 与 DB 运行时适配；保存静音计划 hash、实际切片区间与来源，不保存音频。三次合成 ASR 请求（2 片、1 次重试）只计三次；其费用属于 ASR 总额，不再次作为“切分增量”叠加。实际 11 个试次尚未运行，不能把该合成测试当实际 ASR 花费。

价格与来源/查阅日期在 `pricing-20261016.json`：DeepSeek USD，百炼北京 ASR CNY，均按 provider 真实 usage；推理已含输出，不能额外收费；缓存/节假日/边界不确定给区间；未知用量/未核实模型价格保持未知。没有假设汇率或免费额度。低层记录安全请求地址、字节/哈希和 options 摘要；资料 HTTP400 私有响应最多 4000 字符，脱敏在截断之前。响应摘录不公开、不进日志，不改变资料生成业务请求/校验。当前 400 样例仅来自 mock，实际课程若发生仍需保留私有证据并定位。

保留全部尝试：compile01 通过；related02 为 272 项、1 失败/8 错误（MySQL DATETIME 的 LocalDateTime 映射、启动夹具缺 ModelCallObserver、旧 H2 诊断夹具缺新增列）；修正后 related03 322 项通过，related04 416 项通过；补独立 QA operation 回归后 final05 417 项通过。所有失败日志均未覆盖。实际 SQL 迁移/锁由专属 tmpfs MySQL 验证，H2 仅保留已有单层回归。最终本轮自建 MySQL 容器在核对精确 ID 与 task 标签后停止/删除，不触及镜像或保护容器；清理日志在私有 owned-mysql-test-cleanup.json。

### 阶段 5 数字与文件复现

```bash
# 只读：核对产物/文件哈希和每轮计数、峰值。每轮实际重跑参数在 execution.command。
sha256sum -c eval/p2-1-pipeline-20261016T073754Z/SHA256SUMS
sha256sum -c .data/p2-1-pipeline-20261016T073754Z/RAW_SHA256SUMS
python3 - <<'CHECK'
import json,hashlib,re,zipfile
from pathlib import Path
p=Path('eval/p2-1-pipeline-20261016T073754Z')
for run in json.loads((p/'stages/stage5-checks.json').read_text()):
    log=Path(run['log_path']);assert hashlib.sha256(log.read_bytes()).hexdigest()==run['log_sha256']
    counts=re.findall(r'^\[(?:INFO|ERROR)\] Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)',log.read_text(),re.M)
    print(run['name'],counts[-1] if counts else 'compile/package',run['execution']['disk_peak_percent'])
a=json.loads((p/'candidate-artifact.json').read_text());jar=Path('.data/p2-1-pipeline-20261016T073754Z/frozen-original.jar')
assert hashlib.sha256(jar.read_bytes()).hexdigest()==a['jar_sha256'];assert jar.stat().st_size==a['jar_bytes']
with zipfile.ZipFile(jar) as z:
    print('migrations',len([n for n in z.namelist() if '/db/migration/' in n and n.endswith('.sql')]))
d=json.loads((p/'runtime-readiness.json').read_text());print('disk_pct',100*d['used_bytes']/(d['used_bytes']+d['available_bytes']))
print('headroom_GiB',d['headroom_below_85_bytes']/2**30,'minimum_GiB',d['real_trial_minimum_headroom_bytes']/2**30)
CHECK
```

恢复机制、ASR 归因、用量与费用断言分别在 TranslationCheckpointMySqlTest / PipelineResumeMySqlTest / PipelineUsageLedgerMySqlTest / ModelPriceCatalogTest，具体 -Dtest 和命令见 checks JSON。新相关检查使用新 name，不覆盖旧日志；需重新创建专属测试数据库并按 runner 的 loopback/_test 限制提供测试连接，不能指向业务库。

## 原代码阶段停止点（历史）

代码阶段 1–5 已分别提交（阶段 5 的自身 hash 在提交后汇报，避免自引用），10 次正常完整链路和 1 次独立恢复演示**尚未进行**。无真实 token/费用/成功率改善结果；不生成假的 trials.jsonl。SUMMARY.md 保留 P1-3 与 P1-3b 原结论。

按已确认 DESIGN.md §12，真实测量要求距 85% 的可写余量至少 2 GiB 或更大的估算峰值；当前仅约 0.4 GiB，runtime-readiness.json 标记未就绪。没有自动清理。`RUNTIME_PLAN.md` 给出隔离 worker/schema/Redis/MQ/端口、原 v10 凭据安全引用、环境 capture 需先验证的边界、10+1 测量及查询计划；`evidence-queries.sql` 是只读预览，未执行。既有生产服务、系统 v10 绑定与旧 eval 原样保留，未读取/打印/记录实际 API Key，未 push/merge/deploy。

待空间满足后仍先报隔离 Java 的启动/停止/中断恢复范围并等用户确认，不能把本次设计确认当后续重启授权。

## 授权后隔离执行与 MQ 缺陷（2026-10-16）

磁盘 `df -B1` 可用约 36.68 GiB，精确使用率 74.57%，距 85% 约 15.05 GiB；达到设计前置。用户确认启动/停止、单次 SIGKILL 与重启范围。隔离 MySQL schema `lecturelens_p21_20261016` 已迁移 V1–V31；Redis DB 15 两次初查均为空。MQ 通过 broker 协议创建本轮新 topic/group，原 topic/group 配置逐项相等（mq-preparation.json）；没有 docker exec 或受保护容器生命周期操作。

启动器从现有受保护部署文件/credential 引用在进程内加载配置，不读 `/proc/*/environ`，不输出凭据或配置原文。真实启动前比较捕获指纹与 v10，二者相同；不需要替代 fingerprint，也未生成 v11。隔离进程禁用 Python Agent/index 同步，防止写 Agent 表。candidate JAR 未改动，Java helper 只做启动门禁、LlmProvider 透传和独立恢复试次 barrier。selftest 验证版本/指纹拒绝、半数且至少两批门槛、阻塞期间零派发与解除后一次派发；不能代替真实恢复。源 MinIO 对象逐个流式 SHA256 匹配冻结清单，没有复制媒体落盘。

保留启动失败：第一次迁移由应用账号创建 trigger 缺权限，归档失败后重建本轮空 schema，并仅用已有数据库管理员完成该 schema 迁移；未改变全局权限/参数。第一次 worker 因 topic 不存在失败；创建专属 topic 后仍有一次 route 传播期间启动失败；随后相同配置 MQ client probe/worker 成功。以上均无任务或供应商调用，日志在私有 startup-attempt*/migration-attempt01-failed.log。

正式原候选只提交 `normal-algorithms-1`，task `task_5b6b1585bf3d4b57b28d91fe9cdf68f2`：outbox 的列及 JSON 均为 protocol=2/epoch=1，发送端独立 payload 漏掉协议字段，消费者反序列化成旧协议，`TaskExecutionLease.open` 拒绝。执行表、ASR、翻译 attempt/物理账本和 scheduler 均无记录，未进入媒体阶段。诊断后通过授权 API 取消并停止 worker。真实记录保留在 trials.jsonl、protocol-defect.json、runtime-evidence/；计划 10 次中仅提交 1 次，剩余 9 次和恢复试次未提交，SIGKILL 为 0 次，不补造结果、不把取消耗时当处理链性能。

替代候选前 DB 15 检出仅本轮任务的进度 key，TTL 约 24 小时，按用户非空即停约束停止、未删 key。随后用户明确授权保留该 key 原样复用，并授权修复后另冻候选做独立 10+1；原失败不混入新统计。后续候选与结果在 [P2-1b](../p2-1b-pipeline-20261016T122904Z/VERIFY.md)。

回归先证实缺陷：`runtime-wire-reproduction01`，5 项、1 失败、0 错误/跳过，比较生产发送字节经真实消费者解析后的 v2/epoch，实际为 null/null。补丁为 transport payload 保留非空协议字段，v1 仍省略 null，未改恢复/租约规则。`runtime-wire-fix02`：48 项、0 失败/错误/跳过（producer、consumer、message、runner、creation）；`runtime-replacement-package03` 离线打包成功。该改动仅 Java MQ 序列化，未修改 Python Agent/runtime 或 DB 机制；本轮不把之前阶段的独立 MySQL 测试重复计入新检查数。

检查记录与原始日志路径见 runtime-checks.json；原候选归档 `.data/p2-1-pipeline-20261016T073754Z/frozen-original.jar` 保持 SHA256 `beaa04ff59fe167950406b693e8f7590185dd98d97e526d12965d3ce9e2884bc`。原 candidate-artifact.json 中构建路径是历史位置，后续构建已替换 target JAR，核验原候选须使用归档。SUMMARY.md、SHA256SUMS 与原失败证据一并本地提交，不 push、不部署。

MQ 修复与本目录首个失败证据已本地提交 `4542af2af122d7229e73637ebed498264ba755d2`。替代候选最终十次正常试次全部执行，翻译10/10发布、完整链路0/10（资料均上下文超限400）；独立第11个任务ASR第70/71片403，未达到barrier、未SIGKILL，恢复演示未完成。所有本轮进程已退出。实际阶段均值±样本标准差、分币种费用、拆批/并发、旧基线对比、失败和外部容器观察差异详见 [P2-1b SUMMARY](../p2-1b-pipeline-20261016T122904Z/SUMMARY.md) 与 [VERIFY](../p2-1b-pipeline-20261016T122904Z/VERIFY.md)。新原始记录索引见 runtime-private-record-manifest.json；原阶段 RAW_SHA256SUMS 未覆盖改写。
