# 阶段 3：C/E 未纳入，冻结获准的串行候选

用户允许 C/E 不能稳定满足门禁时，以 streamingTranslation=false、materialsParallel=false 冻结 A+B+D+F+G。本轮采用该选项；不宣称已实现增量翻译协议或资料/翻译并行运行时。

## 兼容性探针实际失败

PreparationOverlapProbe 显式通过 `-Dtest=PreparationOverlapProbe` 运行，stage3-overlap-probe.json：2 项，1 failure、1 error、0 skipped，退出码 1。

- C：已有成功翻译后追加闭合原文批次，再用现有 coordinator 接续，实际返回 SOURCE_CHANGED。现有计划根 hash/全文指纹不可变，不能把 append 视为合法增量输入；没有删 trigger、放松版本检查、改写成功批次或重置预算绕过。
- E：要求资料在翻译未结束时启动，实际未启动；当前 runner 按顺序执行。原文资料入口的存在不等于已经获得分支并行、分支恢复与原子终态协议。

这是对当前接口的特性验收探针，不是完整 C/E 实现。失败保留、不改成成功，也不纳入正式十次。Probe 命名为显式验收入口，不属于 Maven 默认 *Test 单元回归；默认回归通过不抵消其特性验收失败。

## 实际保留的变更与验证

新增可选冻结 flow：sourceOnly、streamingTranslation、materialsParallel。两个 overlap 标记为 true 时，启动校验/反序列化明确拒绝；不会默默回退或让未合格路径运行。旧任务缺 flow 时保持原序列化和行为。

新任务可设 PIPELINE_MATERIALS_SOURCE_ONLY=true，GenerateLearningPackageStep 校验冻结模型执行引用后，用冻结 sourceOnly 构造资料命令，旧任务不跟随当前配置。A 的上下文、输出、调用数和时间预算不扩大。是否使用 DeepSeek 仍只由既有系统模型管理决定，本轮尚未改绑定。

stage3-qualified-checks.json：101 项通过，失败/错误/跳过均 0；范围是 A 接线、关闭开关、旧 checkpoint 恢复、权属与快照等机制，不代表 C/E 通过。复算：`python3 eval/p2-1c-20261016T155847Z/verify_checks.py --prefix stage3- --final stage3-qualified-checks.json`。

候选实际运行结构保持整节原文提交后翻译、再生成资料；正式 SUMMARY 必须继续注明 C/E 未纳入。真实质量、耗时、CER、恢复与缓存演示均未测。
