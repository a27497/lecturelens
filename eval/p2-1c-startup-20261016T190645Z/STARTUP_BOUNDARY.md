# 已批准 EnvironmentFile 后的完整启动链检查

新增授权已接受：指定临时 unit 可以由 systemd 直接引用既有 system-models.env，Java 必须为 dev 身份。没有重新请求同一 EnvironmentFile、同一 unit 启动、冒烟或条件满足后的十次许可。本轮尚未创建 unit，因为发现另一个超出来源范围的必要依赖。

## 实际机制

现有 live 的最后生效启动器为 `.data/system-model-management/deploy-20261016/run-backend-new.py`。本轮仅解析其代码结构与路径常量，没有执行或导入启动器，也没有跟读配置值。

其执行链为：

1. 继承 systemd 注入的环境。
2. 从 `/home/dev/projects/lecturelens/.data/live-access/runtime.json` 读取配置，并整体加入子进程环境。
3. 从 CREDENTIALS_DIRECTORY 下的 bailian-asr JSON 中读取 BAILIAN_ASR_API_KEY / ENDPOINT / MODEL，映射到 Java 环境。
4. 固定 execve 到 `.data/system-model-management/deploy-20261016/backend.jar`，另加载既有 asr-bailian.yml。

该启动器没有 sys.argv 参数入口；不能直接指定 P2-1c JAR。执行它会启动 live JAR，且默认运行参数不能证明已隔离，因此本轮没有执行。没有修改它、替换其 JAR、修改 live 环境或用 monkey patch 绕过路径。

已获准的 system-models.env 仅有 SYSTEM_MODEL_CONFIG_ENABLED、FLYWAY_ENABLED、SYSTEM_MODEL_MASTER_KEY、SYSTEM_MODEL_PROBE_ALLOWED_ORIGINS 四个赋值项（前轮只读名称投影，值未读）。它不提供完整的 DB/Redis/MQ/存储等运行配置。新增授权明确只放宽这一条来源，不能由此推定已允许新启动器加载 runtime.json。

另外，冻结候选 BailianAsrProperties 只有 apiKey 属性，没有 apiKeyFile / CREDENTIALS_DIRECTORY 入口。仅挂载 encrypted credential 还不等于已经完成 ASR 注入；需要受信任的服务内适配。冻结 SystemModelEnvironment.capture() 的指纹包含环境路由及原始 key 字符串，本轮只看代码，不读这些值；原 P21Bootstrap 要求版本 10 和指纹一致。省略旧环境配置、禁用系统模型、改指纹或创造新版本均不是合规修复。

前次授权方案只列出了主密钥入口，没有把 runtime.json 和固定 JAR 启动器依赖一并列清；本轮已补齐这部分审查，保留前轮记录不改写。

## 最小新增范围（待批准，尚未实施）

允许为 `lecturelens-p21c-worker-20261017` 创建独立的、以 dev 运行的服务内启动适配器；同 unit 内的受控验收进程也遵循以下内存与来源边界，明确允许它：

- **仅在服务进程内**读取既有 `/home/dev/projects/lecturelens/.data/live-access/runtime.json`，消费与原 live 启动器相同的运行配置；值不返回给 Codex 工具，不打印、不落盘，不生成包含值的 EnvironmentFile。这是本轮缺少的额外配置/凭据来源许可，不能把它当成已批准。
- 按既有 live 的 ASR 注入方式，在服务内消费 systemd 提供的 bailian-asr JSON 并注入 Java；允许的是运行时消费，不允许 Codex 检索密钥值或导出环境。仅挂载文件而不消费，无法满足冻结实现。
- 保留已经批准的 system-models.env（只由 systemd 读取），不再手动打开该文件，不覆盖其主密钥。
- 只改变非敏感的启动目标与隔离覆盖：冻结 JAR/原有 bootstrap 身份门禁、127.0.0.1:18091、lecturelens_p21_20261016、Redis DB 15、指定 topic/独立消费组，以及 candidate-options.json 中原冻结参数。cache OFF；C/E 仍为 false；不扩大上下文、次数或时间预算，不改变模型绑定。

数据库仅使用既有隔离应用账号，不把 MYSQL_ROOT_PASSWORD 转发给 Java/验收进程，不新增 GRANT，不用 root 数据库连接来绕过隔离账号权限。验收所需认证或连接材料只能在 unit 内消费，不能用旧 deployment()/jwt() 工具把环境值读回 Codex。所需权限不足时按原门禁停下。

适配器必须先校验 dev UID、冻结 JAR 哈希、所有强制隔离覆盖，禁止配置/环境整体输出。系统模型版本/指纹、DB/Redis/MQ 门禁通过后才允许任务提交；失败则只保留固定错误码和安全元数据。不得调用旧 runtime_support.deployment()，不得修改 live 启动器或任何现有配置文件，不能以 root 启动 Java。

如果不批准新增来源/服务内消费，则需要由运行环境所有者提供一个已存在、受信任且支持上述冻结 JAR 与隔离覆盖的启动入口；不能把当前固定启动 live JAR 的入口冒称为可复用入口。

## 本轮执行结果

- 冻结 JAR SHA-256 仍为 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`；3 个相关实现源码均与冻结记录哈希一致。
- 临时 unit 仍 not-found / MainPID=0，18091 无监听；没有启动 Java、没有权限试探、没有读取 runtime.json 值或 ASR credential 值。
- DB/Redis/topic 当前连通性及 bootstrap 身份门禁未执行，不能沿用历史成功记录充当本轮通过。
- 冒烟未测；正式提交 0，成功率、阶段耗时、CER、调用费用均未测。trials.jsonl 为空，不生成虚构或失败替换的试次。
- 没有创建需要清理的运行资源；在线服务及既有证据未变，没有 push、merge、部署、SIGKILL 或重启。

安全投影与磁盘记录见 preflight.json；原始命令和保护复核见 VERIFY.md / closeout.json。
