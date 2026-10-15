# 系统级模型管理（P1-4，分阶段实现）

本配置层属于 Java/MySQL，服务课程准备、普通课程问答与视觉分析。Python Study Agent 的个人连接、decision/review 和 PostgreSQL Run 快照继续使用[用户模型管理](MODEL_MANAGEMENT.md)。本阶段不统一 Python 系统配置，不切换 embedding，不新增 Anthropic、Responses、插件或故障转移。

## 当前实现

第①提交实现角色、管理员接口边界、存储迁移、加密工具和离线管理员命令。尚未提供配置编辑页面、配置写接口、热生效或运行时切换；新增表不改变现有 AI 调用选择。

- `user_account.role` 仅允许 `USER/ADMIN`，存量和新注册用户默认 `USER`。注册请求拒绝额外字段，包括客户端提交的 `role`。
- 登录、刷新和 `GET /api/me` 返回角色。新 JWT 签入角色；旧 JWT 没有角色时解析为 `USER`。管理授权始终重新读取数据库角色和账号状态，提权、撤权和禁用不依赖令牌到期。
- `/api/admin/system-models` 及其所有子路径经过统一管理员拦截器。未登录返回 401，普通用户返回 403。当前只有 `GET /api/admin/system-models/capabilities`，返回协议与功能目录，不包含凭据。
- Flyway V25 创建供应商、模型、功能绑定、当前版本指针、不可变配置版本、追加式审计和执行快照表。配置版本与审计的 UPDATE/DELETE 由 MySQL trigger 拒绝；迁移账号需要创建 trigger 的权限。
- `FUSION_SUMMARY` 的目录状态为 `connected=false`，数据库约束禁止绑定。首版协议仅有 `OPENAI_CHAT`、`BAILIAN_ASR`、`SILICONFLOW_ASR`。

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
- 缺少主密钥不影响当前旧部署启动，但加解密操作拒绝执行；非空且无效的主密钥在初始化时失败。后续启用系统配置层和完整持久化冻结前，必须提供有效主密钥。
- 密文损坏、凭据 ID 不匹配或错误主密钥返回固定的解密错误类别，不保留底层异常原因，不回退到其他凭据。
- 主密钥轮换工具不在首版范围。需要保留主密钥以读取历史版本，直接换掉它会使旧密文及依赖该版本的任务失效。

当前工具和存储约束的测试验证加密边界，不代表尚未交付的管理写接口已完成验收。

## 后续提交的已确认约束

第②提交接入文本、视觉、两种翻译功能绑定及执行快照；第③提交接入 ASR 运行时切换；第④提交完成管理员前端与总验收 VERIFY.md。每个提交完成测试后暂停，等待用户验收。

配置保存以 `expectedVersion` 做并发控制。不可变配置版本保留加密凭据；执行快照只保存配置版本号和无密钥解析结果，不复制明文或密文。执行时通过冻结的版本和凭据 ID 解密。自动重试、分片及恢复继续旧快照；手动新任务使用最新版本。配置读取失败不能当作无绑定而回退。

无数据库绑定时保留现有 YAML/环境变量的请求行为；新数据库 OPENAI_CHAT 地址只追加 `/chat/completions`，不补 `/v1`。LangChain4j 保持默认关闭，系统绑定不经过该路径。

Redis 仅通知版本失效；新任务冻结前读取数据库当前版本以覆盖漏通知。多实例相关验收只模拟漏通知和 `expectedVersion` 并发冲突，不要求启动多实例。

地址检查仅允许 HTTP/HTTPS，解析并校验所有地址，禁止私有、回环、链路本地等非公网 IP；禁用重定向和环境代理。**已知局限：首版不固定已校验的 IP 到实际连接，DNS 校验与连接之间仍存在重绑定窗口。** 本次不实现该防护。

连通性测试使用固定小请求及授权音频夹具，限制超时、响应大小和并发，返回错误类别、耗时及脱敏最终地址。只用 Mock 供应商验收；真实 DeepSeek/ASR 调用必须另行得到用户授权和凭据。

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

测试自行创建随机名称的 `lecturelens_p14_*` 数据库，分别验证空库迁移和 V24→V25 升级，结束后只删除自己创建的数据库。不会迁移或清理现有业务库。分阶段结果和原始日志索引记录于 `eval/system-model-management/`；最终汇总在第④提交提供。
