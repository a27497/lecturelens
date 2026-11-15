# P2-1c：资料生成上下文修复、处理链加速与重跑验收设计

状态：阶段 0，待用户确认。本文的参数是拟议配置或验收条件，不是实测结果。确认前不改业务代码、不改数据库或模型绑定、不启动或重启服务、不发模型请求。仅本地提交本文，不 push、不 merge、不部署。

## 1. 基点、边界与只读发现

- 工作目录：`/home/dev/projects/lecturelens`；基点 `aea84c417dfb1c24d737c7edbf95da4b18234727`；沿用当前分支 `codex/p14-system-model-management`。已有未跟踪文件 `eval/baseline-deepseek-20261015T185735Z/DIAGNOSIS.md` 原样保留，不纳入本轮提交。
- 唯一真实链路运行时：Java `127.0.0.1:18091`、MySQL `lecturelens_p21_20261016`、Redis DB 15、topic `lecturelens-p21-20261016T073754Z`；消费者组身份沿用 P2-1b 冻结记录，不另建公共消费方。新任务使用新 taskId，不覆盖历史任务、台账或证据。
- 阶段开始已执行 `df -B1 /home/dev/projects/lecturelens`，通过磁盘门禁。写设计前再次检查，UTC `20261016T155847Z`：文件系统总量 154894188544 bytes，used 116349243392 bytes，available 38528167936 bytes。按 `used/(used+available)` 使用率 **75.123443%**，距 85% **14.246028 GiB**。这与 df 向上取整显示的 76% 区分。
- 只读 `ss -H -ltn 'sport = :18091'` 当时无输出，表示检查时该端口没有监听者；没有启动 worker。当前账户权限、在线模型绑定及 Redis key 集合本轮未查询；历史证据不能替代运行前检查。
- 不访问、检查或操作演示/验收容器、`grok-lecturelens-preview-20261009`、`samescale-grok-qa-*`、harnesslab 资源。即使只是复用旧脚本，也须先移除其受保护资源探测路径。
- 不读取、打印、复制或写入供应商 API Key；不读 `.env`、密钥文件、容器环境、`/proc/*/environ` 或含凭据的数据库列。运行前只能通过既有系统模型管理读取非敏感投影；真实调用由获准运行时内部的既有模型客户端完成。若启动方案需要外部脚本提取或复制凭据，停止报告，不能沿用该方案。
- 本轮是确定性课程准备可靠性与性能工作，属于 Java 媒体/业务边界；不迁移 Python Agent 决策、Session/Run 或 PostgreSQL 状态，不宣称提升已经验收的 Agent 智能。

已有实现与历史结果：

| 项目 | 本轮只读核实的基点事实 | 本轮处理 |
| --- | --- | --- |
| A | `aea84c4` 已加入 `LearningPackageContextGuard`：完整消息预检、段落切分、map/reduce、共同调用/时间预算；失败仍统一映射 `AI_PROVIDER_FAILED` | 增补小节结构、独立错误分类与原文输入路径，复测而非重写已有守卫 |
| 旧 P2-1c | `eval/p2-1c-pipeline-20261016T133927Z/SUMMARY.md` 记录正式试次提交为 0；独立资料补测在总期限内未完成 | 旧失败保留，新候选独立目录与身份；不得复用成新成功 |
| ASR 访问 | 旧诊断记录 `403 AccessDenied.Unpurchased`；这不是本轮现状检测，也不是 429 | 单节冒烟重新验证；仍 403 就停止真实验收，不换模型/账户绕过 |
| B | `AsrChunkingProperties` 已有默认并发 2、最大 4；静音策略也限制不超过 4；没有 ASR AIMD | 在现有配置与冻结策略上扩展，不重复造另一套静态开关 |
| C | `PipelineSourceCheckpointStore` 只在整节原文持久化时记录 checkpoint；`TranslationCheckpointStore.active()` 校验整节 source fingerprint | 增量输入需要显式协议扩展，不能向现有全文指纹塞不断增长的字幕 |
| D | 静音策略默认 min/target/max 为 15/30/60 秒；短 speech island 被分开处理 | 先合并相邻来源区间，再应用目标区间与文件大小约束 |
| E | worker 依次执行步骤；资料服务优先取全文译文，缺译文还会检查翻译段 | 增加原文专用资料输入，显式移除该依赖后再并行 |
| F | `FfmpegProperties` 默认已是 WAV / 16000 Hz / 1 channel；抽取命令已有 `-ar`、`-ac` | 核实实际配置和输出，补指标；不能预报性能或文件大小下降 |
| G | 现有原文 checkpoint 是同任务恢复机制 | 新增跨任务、同所有者授权范围的可关闭 ASR 结果缓存；不得把恢复复用当缓存命中 |

历史入口：`eval/p2-1b-pipeline-20261016T122904Z/{SUMMARY,VERIFY}.md`、`eval/p2-1c-pipeline-20261016T133927Z/{READ_ONLY_FINDINGS,ASR_DIAGNOSIS,SUMMARY}.md`、`docs/AGENT_PRODUCT_CONTRACT.md`、`docs/LEARNING_PACKAGE_CONTEXT.md`。历史文档中的授权仅供核查；本轮以当前用户约束为准。

## 2. 公共执行与数据约束

新增能力全部进入任务创建时的冻结策略，包含引擎版本、模型执行引用、上下文/提示版本、切片计划、缓存模式、并发/速率上限和持久预算。旧任务继续旧协议；不把新开关追溯应用到旧任务。迁移只增补表/列，不改历史迁移、既有幂等唯一键或旧配置内容。

MySQL 保存课程准备状态、闭合转写批次、增量翻译计划与缓存；PostgreSQL 的 Agent 状态不参与此处理链。每次持久化和派发前继续校验 task/user、删除状态、来源 revision、eventId、execution epoch、租约及 generation fence。供应商 I/O 不能包在数据库事务内。取消、失去租约、删除和预算耗尽均关闭新派发，拒绝晚到结果，保留已产生费用与未知网络结果。

保留当前任务从首次提交计时的总期限、翻译从首次派发计时的期限、恢复次数和物理调用/token 预算；重启不重置。新增 ASR 自适应窗口/冷却期及分片重试消耗持久化，不能借进程重启重获预算。模型调用事实仍以 `model_call_attempt` 为唯一费用来源。

## 3. A — 资料生成上下文修复

1. 优先使用课程小节/段落及时间范围建立有序 map 输入；没有小节标注时按段落、句子、完整 Unicode 字符依次退化。保留 source segment IDs、起止时间、内容 hash 和块序号，覆盖完整原文，不能只保留前半节。视觉证据若当前任务启用，作为独立有界来源处理，不引入译文依赖。
2. 所有 map、reduce、最终生成、质量修复请求都在真实派发前检查完整消息及输出预留。继续使用 `min(floor(context*0.70), context-output-reserve)`。已有默认 context 8192、reserve 256、map output 512、最终 output 4096、最多 64 次请求、6 层 reduce、总期限 900 秒先保留，冻结后不为跑过验收而扩大。
3. 使用匹配冻结模型的 tokenizer（若已具备）；否则沿用可解释的 UTF-8 保守上界，标注为预检估算，绝不作为计费用量。未知 tokenizer/模型能力不能声称已精确计数。预检超限继续切分；reduce 请求也须继续分组/压缩。最小块、固定提示仍不满足时，本地拒绝，物理调用计数不增加。
4. 拟新增 `LEARNING_PACKAGE_CONTEXT_LIMIT_EXCEEDED`，区分本地最小请求超限与供应商返回上下文超限的 origin；预算/超时/协议失败继续各自分类，不全部误标成上下文超限。只记录安全码、长度、hash、估算/实际 token，不记录请求正文或敏感响应。
5. 模型仅通过既有系统模型管理的 `LEARNING_PACKAGE` 功能绑定选择已有 DeepSeek 模型；不得直接编辑密文、复制翻译凭据或使用新直连客户端。先读取非敏感能力/模型/版本投影；确认实施后仅在隔离配置作用域完成绑定并冻结新版本。上下文能力需有可信来源，不能把 output maxTokens 当 context。若现有管理接口无法限制到隔离作用域，则保留原绑定并报告，不能改在线配置。
6. 资料产物继续经过结构、覆盖和质量校验及最终发布围栏；记录 MODEL / REPAIRED / DETERMINISTIC_FALLBACK 来源。机械结构通过不代表教学质量通过；退化产物单独列示，不能隐瞒来声称模型生成成功。map 笔记有损，必须检查五课概念覆盖与来源支持。

拟改：`learning/service/LearningPackageContextGuard.java`、`LearningPackageProperties.java`、`LearningPackagePromptFactory.java`、`LearningPackageServiceImpl.java`、`GenerateLearningPackageCommand.java`；`common/error/ErrorCode.java`，必要时 `task/runner/LlmFailureDiagnostic.java` 与既有 LLM 错误安全映射；上述 Java 路径均位于 `backend/src/main/java/com/example/courselingo/`。系统模型管理原则上复用已有能力，仅在发现隔离作用域缺陷时修复对应边界。

风险：过度分块造成调用放大和总期限耗尽，摘要损失公式/定义，模型绑定污染在线配置。回退：保留现有上下文守卫，按新任务切回已冻结的旧模型绑定/资料输入模式；不提供关闭预检后发送已知超限请求的开关。更换模型或提示形成新候选，旧失败不重跑覆盖。

## 4. B — ASR 并发 2→4 与 AIMD

只读来源（2026-10-16 查阅）：[百炼限流文档](https://help.aliyun.com/zh/model-studio/rate-limit)，`Qwen-Audio-ASR / 华北2（北京）` 表列 `qwen-audio-3.1-asr-flash` **600 RPM**；文档说明按主账号汇总，业务空间共同消耗额度，可能另按秒执行。600/60=10 requests/s 是目录值换算，不是本账户实测 QPS，也不是并发额度。本轮未访问账户控制台，账户定制配额与剩余容量为**未测**。如后续有安全的只读配额视图，仅取模型、地域及配额，不进入凭据页面。并发 4 可实施的依据是配置上限和受限试运行，不是已经证明账户稳定。

- 拟冻结 initial=2、min=1、max=4、successStreak=3；每个成功窗口达到阈值时加 1，429/明确限流时降为 `max(1,floor(window/2))`，清空增长计数，遵从有界 Retry-After 或指数退避加抖动。已有在途调用自然结束，不补发超额请求。
- 并发控制与速率控制分开：按 provider/model/非敏感账户配置引用建立进程级共享 limiter，平滑派发，速率不得超过核实目录/账户上限的较小值；未知账户额外限制由 429 收缩处理，不能保证隔离 worker 独占主账号额度。
- ASR 每次重试重新申请 permit；窗口变化、在途数、派发时间、限流原因、冷却和恢复事件持久化。401/403 不做 AIMD 重试或自动换供应商，直接停止该试次并停止后续验收提交。
- 正式十次固定 max=4，不掺 max=8。只有十次中观察到窗口实际到达 4、无 ASR 权限故障/限流且链路与 CER 门槛通过，才允许单列试验 8；需同步修改当前两个硬上限并冻结独立实验身份。8 不影响正式十次分母、均值或判定；未达到条件写“未测”。

拟改：`task/runner/{AsrChunkingProperties,TranscribeAudioStep}.java`，`media/SilenceSegmentationPolicy.java`，`subtitle/pipeline/{PipelineTranslationProperties,PipelinePolicyService,TranslationPolicy}.java`；新增 `ai/asr/AdaptiveAsrController.java`、ASR limiter/持久状态接口与安全限流观测；必要时 `ai/asr/AsrCallFailure.java`、`AsrProviderException.java`。所有路径相对上述 Java 根目录。

风险：共享账号其他流量、冷却期恢复风暴、重试放大、恢复时重置窗口。回退：ASR adaptive=false、concurrency/maxConcurrency=2，按新任务冻结；保留请求速率限制与原重试预算，不改旧任务策略。

## 5. C — 边转边译与增量 checkpoint

1. ASR 任务开始即冻结完整切片 manifest。每片成功后，以 task/clip/config 为唯一身份保存不可变源结果及 hash；完成通知只负责唤醒，丢通知后从持久待办恢复。允许物理乱序完成，但按 manifest 顺序推进连续原文 watermark，不能按完成先后分配字幕序号。
2. 每个闭合原文批次立刻投递翻译，不等整节结束。闭合规则依据冻结的片序、输入预算、段落边界与结束标记；出网前超预算按现有拆分协议处理。尾部批次只在 source sealed 后封口。待办持久化，内存队列有界并提供背压。
3. 保留翻译唯一键 **taskId + batchNo + configVersion**、子批树、attempt 记录及预算规则。根批/子批编号共用既有受锁分配器；来源区间到根批编号的映射一经落库就不重分配，重启或后续追加不得改写已完成请求 hash。
4. 给计划增加显式 FULL / INCREMENTAL 模式、输入 watermark、闭合批次摘要、source-sealed 标记与最终 manifest hash。旧 FULL 模式原有全文 source/root hash 校验保持。INCREMENTAL 模式派发只校验不可变闭合批次及已冻结 manifest，不能每追加一片都令整节 source fingerprint 失效，也不能因此放松权属/epoch 检查。
5. 整节原文完成后，将 source subtitle/段落映射与最终 source checkpoint 一致提交；对已翻译批次验证最终覆盖、顺序、来源 hash，然后才发布整节译文。翻译中断恢复直接复用已成功批次；暂未提交或网络结果未知的调用单独处理，不承诺外部供应商 exactly-once。

拟改：`task/runner/{TranscribeAudioStep,PipelineAnalysisTaskWorkExecutor,PipelineAnalysisTaskStepContext,TranslateSubtitleSegmentsStep}.java`、`task/service/{PipelineSourceCheckpointStore,PipelineExecutionGuard,PipelineCheckpointDeletion}.java`、`subtitle/pipeline/{TranslationCheckpointStore,TranslationBatchCoordinator,TranslationBatchPlanner,TranscriptParagraphService}.java`、`subtitle/service/SubtitleTranslationServiceImpl.java`；新增增量 coordinator/转写批次 store；增补数据库迁移（基点最新 V31，预计从 V32 起，编号实施时复查）。

风险：可变原文破坏指纹，乱序/尾批遗漏，队列丢失，root/child 编号冲突，旧执行晚到写入。回退：streamingTranslation=false 恢复整节 barrier；已经创建的增量任务按冻结协议完成或显式终止，不能中途改成旧模式重算。保留增补表，不破坏历史数据。

## 6. D — 合并相邻静音切片

- 在现有静音候选区间上确定性合并相邻 speech islands，拟配置 min=60s、target=90s、max=120s。仅提高 target 不能解决当前短 island 独立输出，必须增加合并步骤。
- 默认保留相邻片之间的原始静音，以一个连续 `[start,end)` 从原音频提取，避免拼接后时间偏移。每片保存所有旧子区间、夹入静音、原片索引及原因；所有输出时间仍指向原课程时间轴。确需移除间隔时必须有逐区间映射，不能沿用单一 offset 冒充原时轴。
- provider 时长、原始/编码文件大小限制优先于目标长度。尾片、长静音间隔或文件上限导致不足 60s 时显式标注；不能为了凑区间吞掉语音或超限。实测文件大小校验在派发前进行。
- 每课记录“同一音频、同一检测结果、旧规则片数 / 合并后片数”、实际时长分布、例外原因、source mapping hash；只需规划旧片数，不额外调用 ASR。后续 CER 不通过则不宣布合并验收成功。

拟改：`media/{SilenceAudioChunkPlanner,SilenceSegmentationPolicy,AudioChunk}.java`、`task/runner/TranscribeAudioStep.java`、冻结策略与来源观测模型。风险：跨片术语丢失、静音误判、长间隔使文件增大、时间轴错位。回退：merge.enabled=false，恢复原静音分片规则，仍保留所有时间来源；改规则形成新候选，失败试次保留。

## 7. E — 资料生成与翻译并行

原文最终 checkpoint sealed 后即可启动资料分支，同时继续消费/等待翻译分支。资料输入只取原文及当前任务已有的有界视觉证据，目标语言由原有参数决定；不得读取译文全文、等待翻译状态、把缺译文误判为资料前置失败。资料 schema/下载产物和权属边界保持原有约定。

使用有界执行器、分支独立的不可变上下文及调用记录收集器；不得并发修改现有共享 `completed`/AI records 列表。两个分支分别保存终态和发布 fence；全部必需分支成功后才生成完整产物并置任务成功。一分支失败时关闭兄弟新派发，处理在途请求、记录已提交产物及费用；不能让失败任务在回调中改成成功。重启复用已完成资料/翻译 checkpoint，禁止重复发布。

拟改：`task/runner/{PipelineAnalysisTaskWorkExecutor,PipelineAnalysisTaskStepContext,GenerateLearningPackageStep,GenerateArtifactsStep,AnalysisTaskWorkExecutorConfiguration}.java`、A 所列资料 command/service/prompt，以及分支 checkpoint。若 `FUSE_VIDEO_SEGMENTS` 或产物步骤依赖译文，将其保留在翻译后，不能借并行提前发布未完成译文。

风险：隐含译文依赖、分支竞态、孤儿线程、多个分支共用 provider 时预算竞争。回退：materialsParallel=false 回串行，资料仍支持原文模式；materialsSource=legacy 仅用于关闭并行的新任务。回退顺序先停新任务，再按获准生命周期操作切配置；不热改运行中任务。

## 8. F — 直接抽取 16 kHz 单声道

复用 `FfmpegAudioExtractorImpl` 已有一次性 `-ar 16000 -ac 1` 路径，明确 WAV PCM 编码并用 ffprobe 验证实际输出采样率、声道、时长和文件大小，避免新增重复全量重采样。每片仍可按统一编码要求提取，不能假设复制 PCM 必然更快。

记录同一源文件 hash、输入音频 metadata、实际命令的非敏感参数、抽取开始/结束、输出 bytes/hash。与 P2-1b 比较抽取耗时；若旧抽取输出仍在且能确认身份，读取其 metadata/bytes 作大小比较；若不可得，大小变化写“未测”，不得用公式估出旧文件大小。若旧输出也已是相同格式，如实报告已存在该能力。

拟改：`media/{FfmpegAudioExtractorImpl,FfmpegProperties,AudioExtractionResult}.java`、`task/runner/ExtractAudioStep.java` 与相关安全指标。风险：配置覆盖默认值、格式与扩展名不一致、重复转码。回退：使用原有 ffmpeg 参数配置值；正式候选固定 16000/1，回退后需新候选，不混入十次。

## 9. G — ASR 结果缓存

逻辑键固定为 **audioSHA256 + asrConfigVersion**；hash 针对规范化后实际送入 ASR 的音频字节。采用分片结果粒度，整节 manifest 另存来源音频 hash。ASR 配置版本必须覆盖模型/供应商/端点地域的非敏感身份、语言/热词/上下文选项、编码及适配器版本；切片变更会改变音频字节 hash。不得把任务 ID 放进内容键以制造无法复用的缓存，也不得跨版本复用。

缓存存放在同所有者命名空间，键查找先鉴权；即使音频相同也不允许跨用户读转写。命中后重新执行当前 task/user、删除/来源/版本检查，通过新任务的围栏写入来源 checkpoint。只存已成功且校验完成的结果，不存 403、429、超时、部分或未知响应。写入原子化，损坏/hash 不符按显式 miss 并留下审计；过期、容量、引用与删除语义有界，任务删除不能复活缓存中的私有课程内容。

拟配置 cache.enabled=false 为默认，支持 READ_WRITE/OFF；**冒烟、正式十次、CER、并发 8 试验及恢复测速均强制 OFF，同时禁用读和写**。运行 gate、冻结策略与每次 ASR 派发记录同时证明有效值，存在命中即该次测速不合格且保留原试次，不能静默补跑替换。

独立演示使用同一份已锁定课程、独立任务先 READ_WRITE 冷运行建缓存，再运行一次同版本命中任务；两次均标为 CACHE_DEMO，不能借正式 OFF 试次偷偷填缓存。报告冷/热实际 ASR 调用数差及 ASR/端到端实测耗时差；其他阶段仍真实执行。冷运行只作为命中演示准备，不宣称只有一次供应商调用或把冷运行费用漏账。

拟新增：`ai/asr/AsrResultCache*.java`、缓存迁移、观测与清理接口；修改 `TranscribeAudioStep`、策略冻结及 `PipelineCheckpointDeletion` 的所有者/删除路径。风险：配置漏项误命中、跨用户泄漏、缓存压垮磁盘、命中绕过取消。回退：cache.enabled=false（读写同时禁用），保留同任务合法 checkpoint；清理仅限本轮明确拥有的缓存对象，不能清库。

## 10. 文件与提交分阶段

上面 Java 文件均相对 `backend/src/main/java/com/example/courselingo/`。配套只改必要的 `backend/src/main/resources/application.yml`、增补 Flyway 迁移和 `backend/src/test/java/com/example/courselingo/` 下对应测试；配置中只写非敏感参数，不填任何密钥值。

文档预计更新：`docs/LEARNING_PACKAGE_CONTEXT.md`、`docs/PIPELINE_TRANSLATION_V2.md`、`docs/ASR_BAILIAN.md`，必要时 `docs/SYSTEM_MODEL_MANAGEMENT.md`、README/部署说明，明确实验实现与真实验收状态。不改变 Python Agent 质量声明。新增运行/复算脚本及公开证据仅在本目录；私有媒体、模型正文和完整运行日志放仓库忽略的 `.data/p2-1c-20261016T155847Z/`，不进 Git，且日志本身也不得包含密钥。

| 阶段 | 计划本地 commit 内容 | 继续条件 |
| --- | --- | --- |
| 0 | 本 DESIGN.md | 写完并本地提交后停下等用户确认 |
| 1 | A、原文资料接口及独立错误码 | 定向机制与独立 MySQL 检查通过 |
| 2 | B、D、F、G：ASR 调度/合并/抽取/缓存 | 有界重试、时间映射、缓存权限/关闭测试通过 |
| 3 | C、E：增量 checkpoint 与分支并行 | 旧协议兼容、取消/删除/恢复/预算竞态测试通过 |
| 4 | 冻结候选、全量测试及文档 | 没有失败/错误；数据库测试不跳过；候选/配置/脚本 hash 固定 |
| 5 | 冒烟、十次、CER、恢复、缓存演示及证据封存 | 每步遵守磁盘、权限、重启审批与固定样本门禁 |

每阶段开始前检查磁盘；占用 >85% 或距 85% <2 GiB 立即停止报告，不自行删文件继续。运行中每次提交/模型派发检查，独立监测周期拟为 2 秒。公式统一 `usage=used/(used+available)`、`headroom=0.85*(used+available)-used`，保留原始 bytes 与时间。触线关闭本轮新派发，只处理本轮进程的安全停止，不触碰保护资源。

## 11. 机制验证与真实验收

### 11.1 全量测试

本阶段只写文档，**测试未测**。确认后先跑定向测试再跑全量，不用历史 148 项或其他数字冒充本候选。Java 全量 `./mvnw -B test` 配合独立本地 MySQL test 库；现有 fixture 要求 loopback 且入口数据库名以 `_test` 结尾，不能将 `lecturelens_p21_20261016` 当单测库。前端执行 `npm run test:unit`，Python 执行其项目完整 pytest，数据库部分使用单独 PostgreSQL test 库。测试数据库仅通过既有非供应商凭据路径配置；不启停任何现有服务，依赖不可用就报告未完成。

每个测试命令保存退出码、完整安全日志、JUnit/pytest 报告、运行/失败/错误/跳过数。数据库跳过不算全量通过，确有不适用项须逐项说明，不能汇成“全部通过”。不预填通过数量。

重点用可控供应商测试：完整提示预检与最小块拒绝的零出网；质量修复再超限；reduce 不收敛/超时；429 减半和重试 permit；403 零重试；ASR 乱序、水位与尾批；append/seal 崩溃点；已成功翻译零新增调用；并行分支失败/取消/删除/过期 epoch；缓存版本隔离/跨用户拒绝/损坏/关闭；ffmpeg 真实文件格式与时间映射。机制测试与真实模型效果分表。

耗时较长的测试/构建/验收命令均使用 `nohup timeout ...`，重定向到本轮安全日志并记录 PID、start ticks、cwd、命令与退出码。最终 VERIFY 记录实际命令，不能只有含糊占位符；不采集带密钥的命令行或环境。

### 11.2 启动门禁与单节冒烟

实施确认不等于服务重启许可。任何启动/重启前先停下请求用户；包括恢复演示中的重启，不能将旧历史授权沿用为本轮许可。先核验运行时身份、端口、schema/topic/group/Redis15 以及非敏感冻结模型元信息，出现未知占用/资源即停止，不杀占用者、不重置 Redis、不清 MQ。Redis 只查 key 身份/类型/TTL，不读进度正文；旧 P2-1c 记录的历史 key 数不能替代当前核验。

固定 algorithms 单节完整冒烟 1 次，cache=OFF，maxConcurrency=4，单列 SMOKE。要求真实 ASR HTTP 成功、无 403，原文完成且后续链路/资料可检查，再进入正式十次。403、上下文超限、非预期降级或链路失败均先停止；记录原因，不自动追加冒烟、切账户或挪用正式试次填补。当前 ASR 可用性为**未测**。

### 11.3 正式十次与统计

复用 `eval/baseline-asr-20261015/assets.lock.json` 的五节完整 MIT OCW 媒体及参考字幕 hash，顺序固定 algorithms/calculus/economics/linear/probability，每节各 2 次，任务间串行。输入无合格内嵌字幕绕过路径，真实 ASR、翻译、资料、产物齐全；cache=OFF。正式 NORMAL 分母固定为 10，保留每次失败/取消/未知状态；不替换、不剔除、不补跑凑成功。如硬停止发生在十次提交之前，写已提交数/计划数及其结果，正式成功率写“未测（未完成十次）”，不把未提交算失败。

完整链路成功要求任务 SUCCEEDED、原文/译文覆盖及对齐通过、资料与产物持久化且可按所有者读取，另列资料生成来源与质量问题。不把资料独立补测或翻译成功写成完整链路成功。

阶段 wall time：抽取为实际调用起止；ASR 为首次派发至最后必要分片结果提交（含排队/退避）；翻译为首次批次就绪至最后批次提交；资料为原文 sealed 后进入生成至结果提交；终态为提交前 monotonic 起点至观察到终态。另记每个 provider 活跃区间、总物理调用耗时与并行重叠，不能将其相加解释为端到端。进程重启跨段用持久事件/数据库 UTC 时间对齐，注明观测边界。

mean±sample std（ddof=1），同时给 n；n<2 时标准差为“未测”，未进入阶段为“未测”，成功/失败阶段分开。并发协议改变后附 P2-1b 原串行日志口径与新事件口径说明，不给伪同口径加速比。

| 阶段 | P2-1b 秒（历史实测） | 本候选 |
| --- | --- | --- |
| 抽取 | 9.439±1.543，n=10 | 未测 |
| ASR | 172.145±41.116，n=10 | 未测 |
| 翻译 | 29.428±7.308，n=10 | 未测 |
| 资料生成 | 成功样本无；失败耗时 0.112±0.050，n=10 | 未测 |
| 提交至终态 | 213.832±44.533，n=10，全部 FAILED | 未测 |
| 完整链路成功 | 0/10 | 未测 |

每次记录：合并前后片数、例外片、实际 ASR 物理调用数（含失败/重试）、基于台账时间区间的峰值并发、429/限流响应数、AIMD 降窗事件数与窗口轨迹。不能以线程池配置值冒充实测峰值，也不能把一次 429 引发的多个日志重复计数。

ASR 费用按实际 `model_call_attempt` 的 input/output tokens 计算 `(input*0.8 + output*2.7)/1000000` 元，标注**目录价估算**；失败/重试一并纳入，缺 usage 的调用列“未测/未知费用”，不能填零或按音频时长猜 token。沿用用户指定北京目录价，来源：[百炼模型价格](https://help.aliyun.com/zh/model-studio/model-pricing)。翻译/资料若报告费用，分 provider 与币种另列，不与 ASR 重复计费或混币相加。

### 11.4 CER：同 P1-3 口径

复用 `eval/baseline-asr-20261015/score.py` 的 reference 读取与 normalize，不改参考、术语或数字规则：HTML decode、Unicode NFKC、casefold、去标记/方括号非语音/讲者前缀、数字分组逗号处理、num2words 0.5.14 英文数字归一，仅保留 Unicode 字母/数字。使用 Levenshtein codepoint edit distance；总 CER 为 `sum(edit)/sum(reference_chars)`，不能简单平均五课百分比。

P1-3 可用 ASR 基线实际是 **9014/216217 = 4.168959888%（约 4.169%），n=9**，概率课仅一份有效转写；十次全任务空输出惩罚指标另有保留，不能混淆。新十次同时报告可用 ASR CER 与固定全试次失败情况；无执行 ASR 的任务不能伪造识别分数。

合并验收的描述性门槛为新可用加权 CER 不高于上述基线，并逐课列原/新结果与分母；另外提供与旧九次相同 course/repeat 配对视图，避免新第十份样本权重影响被掩盖。以原始未舍入值比较，不从结果反推容忍区间。失败就报告未通过，不调整 normalization 或补跑换输出；此小样本不证明统计学非劣效或未见课程泛化。

### 11.5 翻译 SIGKILL 恢复演示

独立 RECOVERY 任务使用经济学课，cache=OFF，同冻结候选。翻译达到至少 2 个根批完成且至少一半已完成、仍有待处理批次时，先在派发前 barrier 暂停新调用并等待已派发请求结束，保存 task、source-sealed/watermark、计划、已完成批次、hash、attempt_count、物理调用 ID、epoch 和预算快照。可在完整原文 sealed 后注入，避免 ASR 在途结果干扰本项翻译恢复判定。

先向用户展示核验后的隔离 worker PID/start ticks/cwd/JAR hash 与重启命令并停下，明确请求本轮 SIGKILL 及随后重启许可。拿到许可才执行；若用户仅许可 kill 而未许可重启，kill 后仍须单独等待重启许可。等待期间不持有数据库事务，不让 barrier 等待重置持久期限；期限过期如实失败，不延长后伪称恢复。

恢复同一 taskId/配置，租约恢复提升 epoch。逐批对比已成功 batch 的 ID、请求/结果 hash、attempt_count 与物理调用 ID 集合，必须完全不增加；待处理批次继续，最终检查发布与终态。未知在途网络结果单列，不能声称供应商绝对只执行一次。未实际杀进程/重启或未进入翻译屏障均写“未演示”，不能用单测代替。此任务不计入正式十次耗时/成功率。

### 11.6 缓存命中演示与封存

按 G 执行一次独立命中演示（冷准备+热任务），实际节省调用与耗时从台账/事件复算；无实际命中则失败，不能人为塞旧结果冒充命中。并发 8（如满足 B 的前提）单列，不追加进正式样本。

最终本目录交付 `DESIGN.md`、`VERIFY.md`、`SUMMARY.md`、`trials.jsonl`、`SHA256SUMS`，以及冻结身份/公开安全投影、逐阶段日志索引、复算脚本。VERIFY 列出实际改动文件、源码/候选/JAR/脚本/配置非敏感身份、结果文件 hash、原始记录位置、每个数字的实际复现命令、全量测试日志位置与退出码；SHA256SUMS 不包含自身。原始私有记录另存 hash 清单，密钥不得进入任何记录。

`trials.jsonl` 追加式记录 SMOKE/NORMAL/RECOVERY/CACHE_COLD/CACHE_HIT/CONCURRENCY8 的计划、提交、事件与终态；补测、未提交和失败不能改名为成功。读数据的复算命令与会调用模型/变更状态的复现实验命令明确区分。

每次提交只 stage 本阶段明确文件，检查 diff；最后列出本地 commit 列表与磁盘快照。回退以新任务配置开关或本地 revert 为准，不清表、不删历史失败、不修改在线配置、不部署。

## 12. 当前停止点

阶段 0 仅完成只读梳理与本文；本轮 ASR、完整链路、CER、缓存、恢复、单测结果均为**未测**。等待用户确认本文后才进入阶段 1。任何服务启动/重启仍另行停下请求许可。
