# 受控启动仍停在机制/来源门禁

本轮接受 system-models.env 的唯一新增引用授权，并继续完成只读启动链检查。发现 live 启动器还整体加载 `.data/live-access/runtime.json`，并固定执行 live backend.jar，不能直接用于冻结 P2-1c 候选。该额外配置来源和服务内启动适配尚未获准，未执行或导入旧启动器/验收脚本。

当前结果：临时 unit 未创建、Java 未启动、18091 无监听；冒烟未测，正式提交 **0**，完整成功率/阶段耗时/CER/费用均**未测**。没有新运行资源需要清理，没有通过试次或调用台账可以报告。

冻结 JAR 与相关源码哈希一致；cache OFF、隔离 DB/Redis/topic 及预算未改。当前 DB/Redis/MQ 连通性和 bootstrap 指纹门禁没有运行，不能用旧记录代替本轮验证。在线服务、环境文件、冻结证据及原有未提交文件未改。

最小新增授权与完整路径依赖见 [STARTUP_BOUNDARY.md](STARTUP_BOUNDARY.md)：仅允许同一个 dev 临时 unit 内的受控启动/验收进程，在内存中消费现有 runtime.json，沿用既有 ASR 注入方式，并强制冻结 JAR/隔离覆盖。不把值返回工具、日志或文件，不使用 root 数据库连接，不改 live 或任何既有配置，不绕过版本/指纹/预算门禁。EnvironmentFile 的既有许可无需重批。

本轮没有回归重跑、付费调用、SIGKILL、重启、部署、push 或 merge。证据为 preflight.json、closeout.json、空 trials.jsonl 和 SHA256SUMS；复算见 [VERIFY.md](VERIFY.md)。
