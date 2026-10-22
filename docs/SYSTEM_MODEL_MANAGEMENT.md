# 系统级模型管理（P1-4，分阶段实现）

本配置层属于 Java/MySQL，服务课程准备、普通课程问答与视觉分析。Python Study Agent 的个人连接、decision/review 和 PostgreSQL Run 快照继续使用[用户模型管理](MODEL_MANAGEMENT.md)。本阶段不统一 Python 系统配置，不切换 embedding，不新增 Anthropic、Responses、插件或故障转移。

## 当前实现

已实现管理员权限、离线管理员命令、配置写接口、Java 文本/视觉解析、两路翻译绑定、ASR 运行时切换、不可变配置版本与执行快照。系统层默认关闭；管理员页面位于 `/admin/settings/models`，与个人学习 Agent 的 `/settings/models` 分开。

- `user_account.role` 仅允许 `USER/ADMIN`，存量和新注册用户默认 `USER`。注册请求拒绝额外字段，包括客户端提交的 `role`。
- 登录、刷新和 `GET /api/me` 返回角色。新 JWT 签入角色；旧 JWT 没有角色时解析为 `USER`。管理授权始终重新读取数据库角色和账号状态，提权、撤权和禁用不依赖令牌到期。
- `/api/admin/system-models` 及其所有子路径经过统一管理员拦截器。未登录返回 401，普通用户返回 403。所有当前配置、版本和执行查询使用专用 DTO 投影，密钥字段仅有 `hasKey/keyLast4`；不返回版本 JSON、密文、凭据内部引用或环境指纹。
- Flyway V25 创建供应商、模型、功能绑定、当前版本指针、不可变配置版本、追加式审计和执行快照表。配置版本与审计的 UPDATE/DELETE 由 MySQL trigger 拒绝；迁移账号需要创建 trigger 的权限。
- `FUSION_SUMMARY` 的目录状态为 `connected=false`，数据库约束禁止绑定。首版协议仅有 `OPENAI_CHAT`、`BAILIAN_ASR`、`SILICONFLOW_ASR`。

当前可以绑定 `TRANSLATION_FULL_TEXT`、`SUBTITLE_TRANSLATION`、`LEARNING_PACKAGE`、`COURSE_QA`、`COURSE_CHAPTER` 和 `VISION_FRAME_ANALYSIS`，均走 OPENAI_CHAT。全文和逐段翻译分别解析绑定，保留各自的 JSON/纯文本输出契约；全文模式仍默认开启。视觉绑定要求 VISION/JSON_OUTPUT 声明，不会自动开启业务侧 VLM 开关。模型能力声明不代表真实可用性或课程质量认证。

供应商最多 100 个、模型最多 500 个；模型参数只接受 temperature、maxTokens、timeoutMillis、maxAttempts，分别限制到 0–2、1–32768、100–180000 毫秒、1–3 次。请求自身的 token/时间/重试限制继续约束实际调用。配置保存不产生供应商请求。

## 启用与版本冻结

显式设置 `SYSTEM_MODEL_CONFIG_ENABLED=true`、`FLYWAY_ENABLED=true` 并向进程提供有效的 `SYSTEM_MODEL_MASTER_KEY`。主密钥缺失在启动期间报错，不等待第一次加解密。关闭该层时，不要求新增主密钥，不查询配置表，也不改变原 provider 选择。

首次启用时，服务把当前 YAML/环境默认及其加密凭据捕获为不可变版本。以后默认变化也生成新版本；多实例应使用相同主密钥和部署默认。当前表是管理索引，完整版本是执行依据，两者与变更审计在同一事务更新。

- 分析任务在创建事务内冻结整个文本/视觉/ASR 配置及翻译模式，冻结失败不投递新任务。自动重投/恢复读取原快照，异步分支和批次显式传递执行引用。
- 普通课程问答、章节和手动资料生成按操作冻结新版本；内容修订与协议内重试继续使用同一引用。
- 执行快照只有版本号和无密钥解析结果，没有明文或密文。调用前按版本号从不可变版本解密；编辑、轮换密钥或删除当前对象不改旧快照。
- 创建新快照直接读取并锁定当前版本，不能以缓存或 Redis 作为当前版本权威；Redis 在提交后通知缓存失效。漏通知不影响新任务版本，`expectedVersion` 防止并发覆盖。
- 旧任务首次接管标记 ADOPTED，不追认为创建时已冻结。取消、删除或 owner 不匹配的任务不能继续解析；原 generation fence、租约及晚到结果保护保留。
- 原 worker 不支持新快照。部署升级或关闭该层前需要排空相关任务，避免旧 worker 接管新任务；本次没有执行部署操作。

没有数据库绑定时，使用冻结的原部署配置；原 OpenAI 路径的 `/v1` 补全和兼容语义保留。数据库绑定存在时，配置、认证、模型、解密和协议失败均明确报错，不回退其他供应商；数据库绑定的 JSON 调用不降级纯文本。LangChain4j 默认仍关闭；本层启用时要求关闭该独立旧路径，绑定使用直接 Chat Completions 适配器。

数据库 OPENAI_CHAT 地址只追加 `/chat/completions`，不补 `/v1`：DeepSeek 前缀 `https://api.deepseek.com` 生成 `https://api.deepseek.com/chat/completions`；已有 `/v1` 或 `/compatible-mode/v1` 前缀保留。成功文本结果元数据记录最终 URL、快照、版本与功能；执行日志只记录标识、结果类别和耗时。

## ASR 运行时选择

系统层启用后同时注册百炼与 SiliconFlow 适配器工厂，唯一 ASR 入口按任务执行引用解析 `ASR_TRANSCRIPTION`。该功能要求模型声明 `ASR`，协议为 `BAILIAN_ASR` 或 `SILICONFLOW_ASR`；文本/视觉不能绑定这两类协议。保存绑定、清除绑定及回滚均生成新版本，不重启服务。

- 新任务创建时冻结 ASR 路由；真正需要外部转写时只创建一次任务专属适配器。所有分片、并发 worker、重试、合并都显式使用它，不读取当前绑定或可变单例选择。自动重投继续原执行引用。
- 无绑定时捕获原 `ASR_PROVIDER=bailian|siliconflow|mock|none`，显式 provider 优先；缺省时只允许一个旧 enabled 开关，多个开关冲突仍拒绝启动。原环境密钥加密到版本，百炼上下文/热词、语言提示、大小/超时及 Mock 文本等非密钥选项随路由冻结。`none` 明确不可用；数据库绑定即使部署默认为 Mock，认证/解密/协议错误也直接失败。
- 百炼 `baseUrl` 填写完整同步端点（例如 `https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`），保留 HTTPS、同步模型白名单、WAV/Base64 大小与不足五分钟输入限制；SiliconFlow 保留已有规则，使用地址的 origin 加 `/v1/audio/transcriptions`，忽略自定义 path。不会把 ASR 地址拼成 Chat Completions。
- 数据库模型的 `timeoutMillis` 缺省为 180000；`maxAttempts` 可覆盖分片重试次数，缺省沿用部署的分片重试配置。分片/单文件大小同时受部署分片配置与该供应商冻结上限约束，切换供应商不会绕过限制；不会自动重新选择分片时长，过大的分片明确失败，部署者应设置两供应商均可接受的分片参数。
- 合格内嵌字幕仍优先使用，不创建 ASR 适配器、不要求 ASR 密钥。真实 ASR 结果及合并元数据记录 `systemModelSnapshotId/systemModelConfigVersion/systemModelSource`；可通过管理执行查询按任务核对，日志仅记录标识、类别、状态与耗时。
- 第②提交已存在的执行快照没有 ASR 路由，不能推断当时未冻结的凭据，遇到外部 ASR 明确返回快照无效。升级前应排空这些任务；没有执行快照的旧任务继续按 ADOPTED 规则冻结。本次未进行部署或线上任务迁移。

数据库绑定共用禁止重定向/HTTP 或 SOCKS 代理、3 秒连接与 2 MiB 响应上限的有界传输；实际套接字只使用经公开地址检查的 DNS 结果，字面 IP 同样检查，Host/SNI/证书校验保留原主机名，避免校验后再次解析造成 DNS 重绑定。传输复用项目已使用的 OkHttp 4.12.0，显式禁止隐式连接重试；原环境默认继续原传输兼容行为。模型/认证、429、超时、无效 JSON、地址与响应上限失败不回退其他供应商。第三阶段使用实际适配器组装请求并替换 HTTP 发送验证机制，不代表真实识别质量；验收记录见 [第③阶段 VERIFY](../eval/system-model-management/phase3/VERIFY.md)。

## 管理员页面

`/admin/settings/models` 的入口只对 `/api/me` 返回 ADMIN 的账号显示，直接导航也重新读取角色；最终授权由每个管理 API 的后端拦截器执行。管理 API 的 403 保留普通用户的有效登录会话；管理页收到 403 后移除管理员内容并清空密钥。角色不存入浏览器存储。

页面复用中性标题、面板、状态与模型选项组件，不修改个人页的 decision/review 绑定或命令。供应商/模型增改删、独立功能绑定、历史脱敏查看、单功能恢复绑定、任务快照和审计查询均走 Java 管理 API。

页面把“配置可解析”与“连通性测试通过”分开：前者只检查本地解析、地址格式和密钥解密，不能证明认证、模型或 DNS 可用；同时标记当前翻译模式、章节/视觉部署开关与 FUSION_SUMMARY 未接通。最终地址按当前协议规则展示，环境默认保留原 `/v1` 行为。

密钥表单只保存在组件内存，不写 localStorage/sessionStorage；提交（含失败）、切换供应商、刷新、pagehide、撤权及离开组件后清空。重新打开只显示 `hasKey/keyLast4` 掩码。测试结果只留在当前页面，配置版本变化或重新打开后清除，避免把旧测试当作当前配置保证。

## 当前 API

下列路径均相对于 `/api/admin/system-models`。除 capabilities 外，配置层启用后才注册这些端点。

| 方法与路径 | 行为 |
| --- | --- |
| GET `/catalog` | 当前版本、供应商、模型、绑定及脱敏有效配置 |
| GET `/status?version=...` | 指定版本的本地状态、实际来源、最终地址、功能模式/部署开关；不发供应商请求 |
| GET `/probe-policy` | 测试 origin 白名单、固定限额及 ASR 夹具哈希 |
| POST `/probes` | 管理员手动测试已保存模型，参数 expectedVersion/modelId |
| POST `/providers`；PATCH `/providers/{id}` | 创建/编辑供应商及密钥；返回脱敏 catalog |
| DELETE `/providers/{id}?expectedVersion=...` | 删除没有模型引用的供应商 |
| POST `/providers/{id}/models`；PATCH `/providers/{providerId}/models/{id}` | 创建/编辑精确模型 ID、能力和允许参数 |
| DELETE `/models/{id}?expectedVersion=...` | 删除未绑定模型 |
| PUT `/bindings` | 原子更新指定功能，值为模型 ID；null 恢复部署默认 |
| POST `/rollbacks` | 指定 feature/targetVersion，恢复历史模型引用并生成新版本 |
| GET `/versions?before=...`；GET `/versions/{version}` | 分页版本概要/专用脱敏配置投影 |
| GET `/audit?before=...` | 分页变更审计元数据，不透传任意存储 JSON |
| GET `/executions?taskId=...`；GET `/executions/{id}` | 按课程查找或读取脱敏执行快照 |

版本、审计和执行列表每次最多 50 条。写操作使用 `expectedVersion`，版本冲突为 409；provider 请求字段为 name/protocol/baseUrl/enabled/apiKey/clearKey，model 为 model/capabilities/parameters/enabled。apiKey 缺省保留、clearKey 显式清除，两者不能同时提交。改变地址或协议须重新提交密钥或明确清除；不能清除或停用被绑定对象，也不能静默删除绑定。

绑定例：`{"expectedVersion":7,"bindings":{"TRANSLATION_FULL_TEXT":12,"SUBTITLE_TRANSLATION":null}}`。回滚例：`{"expectedVersion":8,"feature":"TRANSLATION_FULL_TEXT","targetVersion":6}`。所有保存都生成版本和审计；回滚记录独立动作及目标历史版本。不支持幂等键和回滚预览。

## 首个管理员与撤权

先在目标数据库执行 Flyway 迁移，并已有正常注册的有效账号。部署操作者在服务器环境中设置 `MYSQL_JDBC_URL`、`MYSQL_USERNAME`、`MYSQL_PASSWORD`，然后从仓库根目录运行：

```bash
bash scripts/admin/system-model-admin.sh grant --user-id 123
bash scripts/admin/system-model-admin.sh revoke --user-id 123
```

命令编译 Java CLI 并加载 JDBC 依赖，不启动 Spring 或 HTTP 服务，不执行迁移，不注册账号。账号 ID 必须为正整数，账号必须存在且为 ACTIVE。角色更新与 `LOCAL_CLI` 审计在一个事务内提交；审计失败时角色更新回滚。重复指定同一角色返回 UNCHANGED，不追加重复变更记录。CLI 不打印数据库连接错误、密码或完整环境。

该命令使用数据库操作者权限，没有公开 HTTP 提权入口。账号删除不改写历史操作者 ID；审计不保存账号邮箱和密码。注册端点不会自动指定管理员。

## 密钥边界

`SystemModelSecretCipher` 使用 AES-256-GCM，只从进程环境变量 `SYSTEM_MODEL_MASTER_KEY` 读取 Base64 编码的 32 字节主密钥。没有 YAML、数据库、JWT secret 或默认密钥来源。

- 主密钥应随机生成并通过部署 secret 管理，生成值和备份不得提交 Git。
- 每次加密使用独立 12 字节 nonce 和 128-bit 认证标签，AAD 绑定 LectureLens 用途、格式版本和凭据 ID。数据库密文采用 `v1.` 加 Base64URL 封装。
- API key 接受 8–4096 个可打印 ASCII 字符，不接受空白或控制字符。保存结果的公开投影只包含 `hasKey` 与 `keyLast4`，不序列化密文；内部对象的 `toString()` 也不输出密文。
- 系统层关闭时缺少主密钥不影响旧部署；启用时缺失主密钥直接启动失败。非空且无效的主密钥在初始化时失败。工具本身也拒绝未配置密钥时的加解密。
- 密文损坏、凭据 ID 不匹配或错误主密钥返回固定的解密错误类别，不保留底层异常原因，不回退到其他凭据。
- 主密钥轮换工具不在首版范围。需要保留主密钥以读取历史版本，直接换掉它会使旧密文及依赖该版本的任务失效。

管理写接口、历史和执行查询已用 Mock 供应商与独立真实 MySQL 验证；没有进行真实模型调用或任务质量评测。历史版本继续保留加密凭据，首版不提供历史版本清理或主密钥轮换工具。

## 运行边界与连通性测试

四阶段已交付；整体改动、冻结提交与验收证据见 [VERIFY.md](../eval/system-model-management/VERIFY.md)。本次只做本地提交，没有发布。

多实例相关验收只模拟漏通知和 `expectedVersion` 并发冲突，不要求启动多实例。

数据库供应商地址仅允许 HTTP/HTTPS，禁止私有、回环、链路本地等非公网 IP。**已知局限：首版不固定已校验的 IP 到实际连接，DNS 校验与连接之间仍存在重绑定窗口。** 本次不实现该防护。

数据库绑定的运行时传输禁用重定向和环境/JVM 默认代理，连接限时 3 秒，响应上限 2 MiB，异步请求的总等待包括慢响应体；压缩响应明确拒绝。DNS 查询使用有界工作队列和 3 秒等待。保存地址和每次调用均检查全部解析 IP；环境默认路径保留原传输兼容行为。

主动连通性测试只有管理员点击后发送，读取 `expectedVersion/modelId` 指定的已保存数据库配置，不接收临时地址、密钥或任意音频；当前版本不匹配返回 409。测试不改变绑定、配置版本、审计或任务快照，也不保存测试记录表。结果仅有通过状态、固定错误类别、耗时、版本、模型 ID 及最终地址，不返回原始错误、正文、转写或凭据。

- 部署设置 `SYSTEM_MODEL_PROBE_ALLOWED_ORIGINS`（逗号分隔的精确 HTTP(S) origin），默认空即禁止测试。白名单区分协议、域名和端口，不允许 path、查询、fragment 或 userinfo；默认端口规范化。示例：`https://api.deepseek.com,https://api.siliconflow.cn`。名单由部署者管理，页面不能修改。
- 命中 origin 后仍检查 DNS 的全部 IP，禁止私有、回环、链路本地等地址；白名单不能绕过地址策略。传输禁用重定向和环境/JVM 代理，不固定连接 IP，DNS 重绑定窗口仍是已知限制。
- 测试整次等待最多 10 秒，连接最多 3 秒，响应最多 64 KiB（含慢响应体），每实例最多两个请求，不排队、不自动重试。超时后若 worker 尚未退出仍占用并发名额，避免取消绕过限制；限额不是跨实例全局限流。
- OPENAI_CHAT 只发一条短消息、32 个输出 token，并强制 `response_format: {type: json_object}`；使用严格 JSON 对象校验，拒绝重复字段及尾随内容。该测试不验证工具调用、视觉输入或教学质量。
- ASR 使用仓库 MIT 授权的固定一秒合成音频，[夹具及复现说明](../backend/src/main/resources/system-model-probe/NOTICE.md)，不含真人或下载媒体。空转写可通过，只验证请求及响应协议，不验证识别质量。
- 本次全部供应商 HTTP 调用由测试替身接管（传输边界仅访问本机测试服务器）；真实 DeepSeek/ASR 调用必须另行得到用户授权和凭据。

首版不创建 `system_model_probe_record`，不实现幂等键和回滚预览。回滚仅把指定功能恢复到指定历史版本的模型引用，生成新版本；不连带回退供应商或模型记录，历史引用的对象不存在或失效时明确冲突失败。已有任务仍通过自己的不可变配置版本解析旧配置。

## 验证入口

Java 全量测试包含角色、权限、加密和可选的真实 MySQL 测试。CI 的 backend-test 提供独立 MySQL 8.4；本机须显式提供以下测试环境变量，不能把跳过数据库测试记作完整通过：

```bash
# JDBC URL 必须指向本机独立测试 MySQL，基准库名以 _test 结尾。
# 测试账号需要创建/删除临时测试数据库权限。它不迁移传入的基准库。
export SYSTEM_MODEL_TEST_JDBC_URL='jdbc:mysql://127.0.0.1:3306/lecturelens_system_model_test?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC'
export SYSTEM_MODEL_TEST_MYSQL_USER=root
# 在本机环境中配置 SYSTEM_MODEL_TEST_MYSQL_PASSWORD，不把部署密码写入命令记录。
cd backend
bash ./mvnw -B test
```

测试自行创建随机名称的 `lecturelens_p14_*` 数据库，分别验证空库迁移和 V24→V25 升级，结束后只删除自己创建的数据库。不会迁移或清理现有业务库。分阶段结果和原始日志索引记录于 `eval/system-model-management/`；整体汇总见 [VERIFY.md](../eval/system-model-management/VERIFY.md)。


## Integration with structured learning scope

The integration baseline includes PR1 and PR2. Scoped QA validates owner/course/revision and canonical selection before freezing an operation; retrieval still filters the authorized scope before ranking. The scoped QA/Study/Evidence routes, signed path and no-fallback contract remain unchanged. Model routing does not grant Evidence access. Python user connections, PostgreSQL scope states and Run/checkpoint snapshots are unchanged.

When management is disabled and Flyway initializes the database, the integration binary refuses startup if a pinned pipeline remains active. With Flyway disabled it preserves the default database-free startup, but actual execution still fails closed when the database is unavailable. It also rejects run/retry of any pipeline with an existing system snapshot before claiming or changing task state. Legacy tasks without a snapshot retain their original path. The execution check requires a reachable configured business database, but no model master key. Only an actual missing-table SQL state permits pre-V25 behavior; denied SELECT or hidden metadata fails closed.

This guard is absent from earlier binaries. Do not run old and scope-aware/system-snapshot workers on the same task queue during activation or rollback. Stop task ingress and dispatch, drain/cancel active work, stop all old Java consumers, back up and migrate the independent MySQL schema, then start compatible Java gateways/workers before reopening traffic. Preserve PR2's Java → Python → frontend release order; this integration does not change Python. Rollback requires the same quiescence barrier; retain system configuration versions, encryption keys, execution snapshots, MySQL migrations and PostgreSQL scope/checkpoint fences. Never delete or rewrite snapshots to make an old worker resume a new task. A completed pinned task needs a compatible enabled version for later pipeline retry.

Readiness of these mechanisms is not authorization to deploy. PR1/PR2 media, production authentication, long-course/device and recovery gates remain required. QA record-to-snapshot presentation and four-level model diagnostics remain separate PR3 work.
