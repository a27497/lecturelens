# P2-1c 当前验证记录

状态：阶段 1 通过；独立 MySQL 最终 32 项通过、0 跳过，全量回归未测、真实验收未测。这里的机制检查不能替代正式十次或真实模型质量。

## 实施范围

Java 根目录 `backend/src/main/java/com/example/courselingo/` 下：

- `learning/service/GenerateLearningPackageCommand.java`、`ValidatedLearningPackageCommand.java`、`LearningPackageValidators.java`：显式原文输入标记，保留旧构造入口与冻结执行引用。
- `learning/service/LearningPackagePromptFactory.java`、`LearningPackageSourceSection.java`：原文段落、时间/hash 来源与独立视觉观察；原文修复也不读取译文。
- `learning/service/LearningPackageContextGuard.java`、`LearningPackageContextException.java`：原文小节优先切块、最小超限零出网、供应商超限单独分类；保留原调用/上下文/时间参数。
- `learning/service/LearningPackageServiceImpl.java`：原文路径绕过翻译查询；保存后记录 MODEL/REPAIRED/DETERMINISTIC_FALLBACK，记录真实输入长度。
- `common/error/ErrorCode.java`、`task/runner/LlmFailureDiagnostic.java`：超限码及来源进入任务诊断。
- `ai/llm/LlmProviderFailureClassifier.java`：识别旧证据中的 exceed_context_size_error，保留有类型的阶段错误，401/403/429 等独立分类。

配套测试：`LearningPackageServiceTest`、`LearningPackageContextGuardTest`、`LearningPackagePromptFactoryTest`、新增 `LlmProviderFailureClassifierTest`。公共行为文档仅更新 `docs/LEARNING_PACKAGE_CONTEXT.md`，不改变历史验收结论。

本目录脚本不读部署环境/供应商凭据。`run_check.py` 后续运行只向子进程转发明确白名单的基础工具环境和独立测试数据库配置；不转发供应商或应用配置。单测日志与 XML 归档在 `.data/p2-1c-20261016T155847Z/checks/`，不进 Git。每轮 JSON 记录实际命令、退出码、PID/start ticks、日志 hash、各 suite/JUnit hash、磁盘前后及峰值。

## 已执行检查与复算

第一轮 `stage1-unit-01.json`：72 项，失败/错误/跳过均 0。第二轮 `stage1-unit-02.json`：134 项，失败/错误/跳过均 0；加入供应商适配与物理调用观测回归。最终源码完成后的 `stage1-unit-final.json` 为 134 项，失败/错误/跳过均 0，不合并多轮为测试数量。

精确命令保存在上述 JSON 的 `command` 和 `cwd`。长命令实际由 `nohup timeout 660 python3 .../run_check.py --seconds 600 -- ./mvnw -o -B ... test` 执行；启动日志索引为 `/tmp/lecturelens-p21c-stage1-launcher-{01,02,final}.log`，完整 Maven/JUnit 以 `.data` 内的归档为准。

只读复算每轮测试数量、退出码、日志/JUnit 归档 hash：

```bash
cd /home/dev/projects/lecturelens
python3 eval/p2-1c-20261016T155847Z/verify_stage1.py
sha256sum -c eval/p2-1c-20261016T155847Z/SHA256SUMS
```

如需重新执行检查，使用 JSON 内的原命令，但给 `run_check.py --name` 一个全新名称；脚本拒绝覆盖旧证据。`bash -n .../start_unit_mysql.sh` 与 Python `ast.parse` 已执行；它们仅检查脚本语法，不能声称 MySQL 启动或数据库测试通过。

独立 MySQL 运行命令在 TEST_DATABASE_PLAN.md；test-database.json 冻结获准测试容器的实际身份。stage1-mysql-01.json 的 32 项有 1 failure、1 error：断言固定 V25 和空密码 Map.of。修正测试为要求所有当前迁移完全应用、兼容无密码独立夹具后，stage1-mysql-02.json 的 32 项全部通过，失败/错误/跳过均 0；两轮日志/JUnit 均保留。阶段 0 设计文件保留，用户新授权及对冒烟/A 失败的修订见 AUTHORIZED_SCOPE.md。

## 结果身份与未执行范围

本地代码与公开结果的精确 SHA256 见 SHA256SUMS。没有冻结新的可运行 JAR；真实任务的配置、模型绑定和 ASR 访问资格本轮未检查。没有使用旧转写代替新 ASR，没有生成本轮耗时/CER/费用数据。

代码审阅时发现原文路径日志会继续使用译文长度；已修正为原文长度并在最终回归中验证。此前两轮通过记录原样保留，不覆盖。已有未跟踪文件 `eval/baseline-deepseek-20261015T185735Z/DIAGNOSIS.md` 不纳入本轮提交。

磁盘原始 bytes、使用率与距 85% 余量可由各轮 JSON 的 `disk_before`/`disk_after` 复算；公式为 `used/(used+available)` 和 `0.85*(used+available)-used`，单位 GiB 除以 `1024**3`。初始 df 显示 76%，阶段开始通过门禁；后续仍逐阶段检查。

## 阶段 2

详见 STAGE2.md。V32 增补 ASR 状态/事件/分片 checkpoint/缓存及不可变输入约束；存储在 task/service，调度在 task/runner，ASR adapter 无数据库依赖。新增 AsrPipelinePolicy 可选字段不改变旧策略序列化。切片规划和 TranscriptParagraphService 同步支持合并后的冻结上限。抽取显式 PCM 与实际 bytes/耗时观测，默认 16000/1 沿用旧值。对应配置在 application.yml 中默认关闭。

执行只读复算：`python3 eval/p2-1c-20261016T155847Z/verify_checks.py --prefix stage2- --final stage2-merged-integration.json`。当前阶段没有编译可运行候选 JAR、没有真实课程请求；所有实际检查数字均由每轮 JSON/JUnit 复算。
