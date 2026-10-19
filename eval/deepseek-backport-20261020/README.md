# 冻结 Java 基线的 DeepSeek 协议 backport（未部署）

本候选从实际线上 JAR 对应的旧源码构建，不发布开发 HEAD。审批目录为本 worktree 下 `.data/deepseek-backport-approval/`；完整 JAR 摘要、逐条目差异、测试原始记录及部署/回滚文字方案在该目录的 `report.md`。该目录不进入 Git。未 push、未部署；未启动应用服务、访问生产数据库或调用真实供应商。

## 身份与范围

- 线上 JAR：`/home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/backend.jar`。
- 线上 SHA256：`42d6d982d213eb7b0c88bb4b8a431ce88108e2d232a8922df83aad0615c823a2`。
- 线上内嵌身份：`bc2e6cc-diagnostics-null`，build time `2026-10-19T14:17:25.493Z`。
- 原冻结源码：`bc2e6cc79f1a3311b90cc4d407f75d2e20048275`。
- 本地重建冻结基线：`6d6ead56bb46974a30d7951975b1922c168d71af`，只加入此前 `37605e6` 的诊断模型名返回 null 方法及其测试。重新构建的每个文件条目均与线上一致，只有 build-info 构建时间不同。
- 修复来源：`f2900c383949ce75abd3d4814ce1ab68c7a21c44`，相对新版 HEAD 的原补丁没有直接应用。

保留冻结基线的依赖、配置、V1–V26 迁移、任务执行器和所有预算/重试设置。没有 Translation V2、TranslationFailure、resume、checkpoint 或 ASR cache 的移植。新 `LlmOutputException` / `LlmOutputDiagnostics` / `LlmOutputGuard` 仅承接协议失败，不带课程内容、密钥、响应片段、异常 cause 或执行状态。

## 冻结基线的实际入口

| 入口 | 旧实现与本次移植 |
| --- | --- |
| 普通 JSON / TEXT | `OpenAiCompatibleLlmProvider` 原已调用公共 options adapter；加入 DeepSeek 参数，DTO 内容映射前检查 length |
| 系统 DATABASE | `SystemModelLlmProvider` → `SystemModelChatClient`；公共参数适配器，content/JSON 校验前 guard，私有诊断记录 OUTPUT_TRUNCATED |
| 系统 ENV | 路由 Provider → 普通 Provider；安全协议异常穿过 ENV 包装，保留 HTTP/usage/finish reason |
| 全文对齐翻译 | TRANSLATION_FULL_TEXT → 同一冻结文本 Provider；未改翻译服务，保留既有有界拆分/语义恢复 |
| 逐段翻译 | SUBTITLE_TRANSLATION → 同一冻结文本 Provider，业务使用 TEXT；公共 TEXT 与系统路由均有离线请求路径回归 |
| 普通视觉 | `OpenAiCompatibleVisionProvider`；解析正文前 guard，协议失败直接 FAILED + 可选安全诊断，不新增 Provider 重试 |
| 系统视觉 DATABASE / ENV | 原 `SystemModelVisionProvider` 分别委托注入传输 / Java HTTP 客户端，再走普通视觉 Provider；本次未改系统视觉路由，两个分支均实际测试，ENV 使用 loopback HTTP 桩 |
| 管理员探测 | `SystemModelProbeService` 的 Chat 分支；同一适配器和 guard，Result 新增可选诊断，旧构造器兼容。ASR 分支未改；未进行真实探测 |
| 可选 LangChain4j | `DefaultLangChain4jChatModelClient` 的 customParameters 使用同一 DeepSeek 白名单；`LangChain4jResultMapper` 在正文判定前拒绝 LENGTH。SDK 不暴露成功 HTTP 状态，保留 null |

参数白名单原样来自 f2900c3：deepseek-flash、deepseek-v4-pro、deepseek-v4-flash、deepseek-v4-flash-vision-exp。仅这些 ID 设置 `thinking.type=disabled`。Qwen 和未知模型的原参数保持；SDK 的 Qwen 参数也保持原状。length 对所有供应商都拒绝，包括空正文、部分正文和合法 JSON。普通 DeepSeek 空正文有独立 EMPTY_OUTPUT 分类；其他供应商普通空正文仍走旧逻辑。

## 离线验证与失败保留

所有 Maven 检查通过主仓库当前 `scripts/dev/run_check.py`，遵循 `docs/LOCAL_CHECK_EXECUTION.md`，每轮使用不同名称；原始失败不覆盖。仅合成客户端、mock 持久层及 loopback HTTP，未启用 MySQL 测试。

- 冻结源码重建包：36 例通过。
- 首轮新增协议回归（旧基线）：176 例，84 失败、15 错误、0 跳过。错误包含基线没有安全诊断 accessor；不是候选通过记录。
- 首版候选：183 例通过。
- 首轮较广回归：485 例，6 失败、1 错误、0 跳过，均来自旧 observation 测试对 length 的旧契约。将原无效内容用例改为 stop 保留内容分类覆盖，另加 7 例明确验证 length 优先，成功用例也改为 stop。
- 增强后的候选：531 例通过，0 失败/错误/跳过。包含 212 例协议矩阵、7 例 length 私有诊断、3 例通过真实 Provider 的旧有界翻译恢复；其他为相关旧回归。
- 最终测试放回独立旧源码再次复现，失败明细与首次记录均另存；见审批报告。

协议矩阵覆盖 11 条实际请求路径 × 6 种输出、11 路径 × 10 个模型参数、11 路径 × 3 种非 DeepSeek 截断；另有 3 个冻结路由控制异常用例，同时检查文本和视觉不吞取消、快照冲突或任务租约失效，不调用传输。最终干净打包再次运行完整选定集合，以该轮 XML 和 supervisor 终态为准。旧 target 目录可能残留前轮未执行的 XML；计数按每轮 Maven 实际执行 suite 核对，不能直接汇总整个旧 target。

## 可重建方式

取本 backport 的完整提交 SHA，用 `git archive <SHA> backend` 导出到全新目录（没有 target），Java 21、同一 Maven wrapper 与 Spring Boot repackage，离线执行：

```bash
python3 /home/dev/projects/lecturelens/scripts/dev/run_check.py \
  --name deepseek-backport-package-UNIQUE --cwd /absolute/clean-build/backend --timeout 300 -- \
  bash ./mvnw -o -B -Dcourselingo.build.git-commit=<完整backport提交SHA> \
  '-Dtest=FrozenDeepSeekProtocolTest,*Llm*Test,OpenAiCompatible*Test,SystemModelProbeTransportTest,SystemModelTranslationObservationTest,SystemModelDiagnosticsTest,TranslationCallDiagnosticsTest,CourseQaServiceTest,CourseChapterServiceTest,VisionAnalysisServiceTest,SubtitleTranslation*Test,TaskCommandServiceTest,TaskCreationServiceTest,PipelineAnalysisTaskWorkExecutorTest' package
```

审批包保留确切命令和 export 文件清单。构建时间元数据使后续重建 JAR 的整体 SHA 可能变化；逐条目比较需只容许 build-info 的时间/提交身份差异及明确列出的协议类。禁止打包整个当前开发分支。初次打包发现 6 个仅因源码行号偏移而变化的附带类；确认指令不变后保留这些原有类型的源码行位，消除附带字节码差异，不改编译器设置或手工替换 class。比较脚本为同目录 `compare_jars.py`，只读 ZIP 内容，不运行 JAR。

## 验证边界

通过的是离线协议、业务恢复和打包检查，不证明真实供应商是否接受参数、费用/延迟、课程重处理质量或浏览器端验收。未读取保留评测题、部署环境文件或凭据，未修改模型配置、预算、恢复策略或迁移。后续部署及任何付费验证均需用户另行明确批准。
