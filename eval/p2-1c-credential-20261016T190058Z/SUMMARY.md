# P2-1c 阶段 5：凭据引用阻塞的实际机制

本轮已定位配置入口不匹配，尚未解除启动授权边界。没有启动隔离 Java、调用供应商或提交试次；冒烟与正式十次均未测，费用未测。

## 证据与结论

1. 当前工作树基准为 `47d8daf`。实际验收对象仍为 `dcc4dda` 冻结候选，JAR SHA-256 `35e8f63b6895e1d69fe45b51be45c196b4585c140b6a6c52b370a9922438d3b0`，92102661 bytes，与原冻结记录匹配；没有重编译、替换或混入后续翻译修复。候选选项仍为 cache OFF、streamingTranslation=false、materialsParallel=false。
2. live 加载的 drop-in 顺序确为 90-asr-bailian.conf、99-system-models.conf，NeedDaemonReload=no。90 提供 `LoadCredentialEncrypted=bailian-asr:/etc/credstore.encrypted/lecturelens-bailian-asr.cred`。99 没有 LoadCredential/SetCredential 项，而是引用 `EnvironmentFile=/home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/system-models.env`。因此此前“未发现 credential 指令”的观察正确，但不能把它等同于系统模型凭据不存在。
3. 仅检查该引用文件的变量名，发现 SYSTEM_MODEL_CONFIG_ENABLED、FLYWAY_ENABLED、SYSTEM_MODEL_MASTER_KEY、SYSTEM_MODEL_PROBE_ALLOWED_ORIGINS；未读取或输出变量值。文件元数据为 dev:dev、0600。没有确认值是否有效、是否为空、具体编码或存储形态，不能称为已确认的明文密钥。
4. 99 的最后一个 ExecStart 使用 `/usr/bin/python3 /home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/run-backend-new.py`，覆盖 90 的启动器。只提取代码结构符号可见 `dict(os.environ)`、CREDENTIALS_DIRECTORY / bailian-asr、read_text、os.execve；未执行或导入启动器，未跟读其运行配置或凭据文件。
5. 冻结提交的 SystemModelSecretCipher 默认构造器直接调用 `System.getenv(MASTER_KEY_ENV)`，变量名为 SYSTEM_MODEL_MASTER_KEY；没有 credential-file 读取入口。系统模型层启用后，主密钥未配置会触发 SYSTEM_MODEL_MASTER_KEY_MISSING。因此只复用 bailian-asr 的 credential 引用，不能满足系统模型主密钥入口。给 unit 增加一个没有 Java 消费入口的 credential ID 也不足以修复。

已确认的阻塞原因是**原受控启动方案限定加密 credential 引用，而 live 的系统模型入口实际是 EnvironmentFile → 进程环境 → Java 主密钥读取**。没有证据表明是模型账户权限或供应商 403；本轮没有发出真实请求。

## 最小可审查方案与所需授权

只给已授权的临时 unit 增加 [PROPOSED_UNIT_DELTA.conf](PROPOSED_UNIT_DELTA.conf) 中的一条 EnvironmentFile 引用，由 systemd 读取已有文件并注入环境。其余凭据仍沿用原 bailian-asr 加密 credential 引用；不复制、解密、转换密钥，不新增凭据，不改 live 文件或权限，不扩大调用预算。

所需新增授权仅为：**允许 `lecturelens-p21c-worker-20261017` 通过上述确切 EnvironmentFile 路径获得系统模型环境，由 systemd 读取注入。** 这与 [原 AUTHORIZED_SCOPE.md](../p2-1c-20261016T155847Z/AUTHORIZED_SCOPE.md) 的“只引用……LoadCredentialEncrypted 路径”不同，不能自行视为已有许可。无需重复批准同一 unit 的 cache OFF 冒烟或满足 ASR 门禁后的正式十次。

这条变更可补足已确认的凭据来源引用缺口，但不表示其余隔离配置已经就绪。获准后仍先复核文件变量名结构、隔离 DB/Redis/topic/端口、冻结选项与 bootstrap 门禁；不能直接复用 live ExecStart 或 live JAR，不读取主密钥或供应商密文验证有效性，不通过复制密钥绕过隔离。若有额外权限需求或机制失败，停止再说明。SIGKILL 恢复和服务重启不包含在本方案中。

## 实际执行状态

- `lecturelens-p21c-worker-20261017` 仍为 not-found / inactive / MainPID=0；18091 无监听。
- live 后端仍为 PID 4866、启动单调时刻 31524728，active/running；没有修改 unit、daemon-reload、环境文件、在线数据库或模型绑定。
- 既有冻结记录与历史验收证据哈希未变；原有未提交 DIAGNOSIS.md 只核对元数据，正文未读、未修改、未提交。
- 正式提交 0；冒烟、十次成功率、阶段耗时、CER、调用费用、缓存演示及恢复演示均未测。没有生成或重标任何成功试次。

安全投影和保护检查见 diagnosis.json；命令及哈希见 VERIFY.md / SHA256SUMS。本次不重复已经完成的回归测试。
