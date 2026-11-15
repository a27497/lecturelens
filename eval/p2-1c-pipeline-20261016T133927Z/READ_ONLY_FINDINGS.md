# P2-1c 只读定位与待确认方案

截至 2026-10-16 21:40（Asia/Shanghai）。本阶段没有业务代码修复、模型配置写入或隔离 worker 启动。仅一次独立 ASR 短音频诊断，不计入 10+1。

## 模型与绑定

从现有部署引用读取凭据至进程内，分别只读查询在线 `courselingo` 和上轮隔离 `lecturelens_p21_20261016` 的系统模型版本；均为 v10，config SHA256 `d02d9d3febf59420cac97c80f35e9e74a9572a85486b9e9baee255c2027fe3e4`。两者 `bindings.LEARNING_PACKAGE` 均为空，生效 ENV 默认模型为 `lecturelens-local-qwen`，providerId/modelId 均为空，路由默认 maxTokens=3072、timeoutMillis=180000、maxAttempts=3。没有将翻译用途绑定的 DeepSeek 错认为资料生成模型。

代码定位（仓库相对路径，行号为修复前）：

- `backend/src/main/resources/application.yml:271`：LEARNING_PACKAGE 环境路由默认 profile `learning-text`；`:291` 定义该 profile，`:295` 的模型优先使用 `COURSELINGO_AI_MODEL_LEARNING_PACKAGE`，再使用 `OPENAI_COMPATIBLE_MODEL`。
- `backend/src/main/java/com/example/courselingo/systemmodel/SystemModelRegistry.java:379`：先读功能的数据库绑定；为空时返回捕获的 ENV 默认路由；非空时解析对应数据库模型和供应商。
- `backend/src/main/java/com/example/courselingo/systemmodel/SystemModelExecutionService.java:64`：任务创建时冻结系统模型版本和解析路由；`:109` 每次调用重新校验冻结版本及可见性，不跟随新配置头。
- `backend/src/main/java/com/example/courselingo/learning/service/LearningPackageServiceImpl.java:213`：优先读取完整翻译结果；`:221` 在存在全文时选全文分支；`:351` 按 taskId/userId/targetLanguage 读取；`:540` 将原文全文、译文全文、视觉信息传入提示工厂；`:824` 应用 LEARNING_PACKAGE 路由。
- `backend/src/main/java/com/example/courselingo/learning/service/LearningPackagePromptFactory.java:190`：系统指令及 JSON 结构；`:275` 用户提示拼接语言、质量要求；`:281` 原文全文；`:282` 译文全文；`:283` 附加视觉时间线。只有视觉时间线已有 40 项/12000 字符界限，全文未分块、未做 token 预检。
- 同提示工厂 `:20`、`:96`：请求显式 maxTokens=4096；`backend/src/main/java/com/example/courselingo/modelrouting/AiModelRoutedLlmRequestFactory.java:48` 仅在请求为空时补充路由默认，所以这里实际请求4096，不能用路由3072描述实际请求。
- `backend/src/main/java/com/example/courselingo/learning/service/LearningPackageServiceImpl.java:789`：直接调用 provider，之前无上下文检查。质量修复分支也重新带入全文。

上轮固定上下文8192，10次资料生成输入11727–17073 token，均返回 exceed_context_size_error；详见 ../p2-1b-pipeline-20261016T122904Z/materials-errors.json。

## 建议 a，待用户选择后实施

按小节/段落构造覆盖完整证据的 map 块，生成有界笔记，再有界分层 reduce 为既有资料结构。缺少章节标签时使用段落/句子边界，并保留块顺序和来源范围。不能简单截断后半节课程。

所有 map、reduce、最终生成及质量修复请求均检查完整消息（含系统提示和质量修复提示）。输入上限取 floor(contextLimit*0.70) 与 contextLimit-outputBudget-reserve 的较小值。tokenizer可用时使用对应模型tokenizer，否则使用明确标注的保守估算，不将估算冒充供应商usage。超限继续拆分；最小块/固定提示不满足、归并不收敛或调用预算耗尽时本地失败，禁止发送已知超限请求。限制调用总数、层数、单次输出及总期限，每次调用保留冻结执行身份并执行取消/可见性校验。最终发布继续通过已有质量校验和 generation fence。

保留系统模型管理对 LEARNING_PACKAGE 的独立模型绑定，可选配 DeepSeek；本轮 a 不修改在线绑定。配置上下文上限需与选定模型实际能力一致。本地默认以8192验证，并冻结候选中的上下文、预检及调用预算配置。

测试应覆盖超长中英文、多段/超长单段、归并再次超限、质量修复新增开销、无可用空间本地拒绝、取消及版本/发布围栏，以及 DeepSeek 数据库绑定路径。测试通过后冻结新候选，单独执行10次完整链路及1次翻译中断恢复。旧失败全部保留。

## 启动边界与待决约束

复用上一轮授权的127.0.0.1:18091隔离Java worker、专用MySQL schema/MQ topic及Redis DB15，真实ASR/翻译；仅对核验身份的隔离worker执行一次SIGKILL并重启，结束后停止本轮进程。不push、不部署、不对受保护容器执行生命周期操作。启动前df至少2GiB，运行时超过85%立即停。

只读扫描DB15发现12个string进度key：原失败任务1个及P2-1b全部11个任务各1个，TTL约23小时；未读值、未删除、未换库。此前明确例外仅覆盖原失败任务1个key，因此已请求扩展到这12个已知key，在收到答复前不启动。

ASR当前AccessDenied.Unpurchased拒绝状态也会阻碍完整链路；本任务对ASR只查不修，不擅自修改账户、凭据、模型或权限。详见 ASR_DIAGNOSIS.md。
