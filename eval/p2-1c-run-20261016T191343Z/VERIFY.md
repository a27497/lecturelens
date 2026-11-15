# 受控启动命令与记录

本轮基准 d4cb00d。用户追加授权仅允许指定 dev 临时 unit 内的启动及验收进程消费既有 runtime.json、已批准 EnvironmentFile 与 ASR credential；不允许 Codex 工具读取值。本轮没有执行旧 live 启动器、旧 deployment()/prepare_runtime.py/measure_runtime.py，也没有启动 live JAR。

## 冻结与仪器

原候选来自 `.data/p2-1c-20261016T155847Z/candidate/backend.jar`，字节/hash 与原 candidate-artifact.json 一致。BOOT-INF/classes 和 BOOT-INF/lib 原样提取到本轮私有 runtime；只在独立 extra 目录编译旧 P21Bootstrap.java 和新增 P21IsolationGate.java，未覆盖候选类或 JAR。

实际编译命令：

```bash
nohup timeout --kill-after=10s 90s javac \
  -cp '.data/p2-1c-run-20261016T191343Z/runtime/BOOT-INF/classes:.data/p2-1c-run-20261016T191343Z/runtime/BOOT-INF/lib/*' \
  -d .data/p2-1c-run-20261016T191343Z/extra \
  eval/p2-1c-run-20261016T191343Z/P21Bootstrap.java \
  eval/p2-1c-run-20261016T191343Z/P21IsolationGate.java \
  > .data/p2-1c-run-20261016T191343Z/compile.log 2>&1 < /dev/null &
```

extra/META-INF/spring.factories 只注册 P21IsolationGate 监听器。原 bootstrap selftest 的实际命令、输出位于源码及 `.data/p2-1c-run-20261016T191343Z/bootstrap-selftest.log`；它校验版本/指纹拒绝与合成屏障，没有加载环境凭据、连接数据库或调用供应商。instrumentation-check.json 保存合成日志过滤/命令边界检查，instrumentation-compiled.json 保存本轮编译产物哈希。运行目录在门禁停止后已删除，重建必须从冻结 JAR重新提取，不修改冻结 JAR。

## 唯一一次受控 unit 创建

```bash
nohup timeout --kill-after=10s 45s sudo -n systemd-run \
  --unit=lecturelens-p21c-worker-20261017 --uid=dev --gid=dev --collect \
  --property=EnvironmentFile=/home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/system-models.env \
  --property=LoadCredentialEncrypted=bailian-asr:/etc/credstore.encrypted/lecturelens-bailian-asr.cred \
  --property=WorkingDirectory=/home/dev/projects/lecturelens --property=UMask=0077 \
  --property=NoNewPrivileges=yes --property=Restart=no --property=KillMode=control-group \
  --property=SendSIGKILL=no --property=TimeoutStopSec=60 \
  /home/dev/projects/lecturelens/.data/p2-1-pipeline-20261016T073754Z/venv/bin/python3 \
  /home/dev/projects/lecturelens/eval/p2-1c-run-20261016T191343Z/runtime_service.py \
  > .data/p2-1c-run-20261016T191343Z/systemd-create.log 2>&1 < /dev/null &
```

**这不是当前可直接重跑的命令。** Redis 门禁已经失败且 unit 已退出；重建/重启和后续处理需要遵守停止边界，不能把重复执行当作已通过的授权内重试。

唯一 InvocationID 为 83307e3128ac414689f94e2ebeaf8caf。runtime_service.py 检查实际 UID 非 root 且账号为 dev，然后才读取配置。配置只转发冻结配置引用的变量名，剔除 root DB 密码、外部 JVM options，并在启动目标上强制隔离覆盖。env 内容、令牌和供应商响应体不被保存；Java 原始 stdout 计划通过内存过滤，只有固定阶段事件/字段可进入 events.jsonl（本轮 Java 未启动，只有合成检查）。

实际停止记录：`closeout-service.json`，code=REDIS15_UNEXPECTED_KEYS、owned_tasks=[]、java_exit=null、used_sigkill=false。

只读 journal 复核（Python解析只保留固定消息及 UID/GID/PID/InvocationID/时间，不保存其他 journal 内容）：

```bash
journalctl -u lecturelens-p21c-worker-20261017.service \
  --since '2026-10-16 19:20:00 UTC' --no-pager -o json \
  --grep=REDIS15_UNEXPECTED_KEYS
```

结果在 unit-journal-safe.json；dev 实际 UID=1002、GID=1003。最初“UID=1000”的日志投影断言失败，已保留说明；这是记录器的账号假设错误，不是服务权限失败，也没有因此重试服务。

## 数据与费用

本轮没有 bootstrap-preflight/runtime-ready/java-identity 或 task 记录。trials.jsonl 为 0 字节，没有提交失败或成功任务。DB/Redis/存储预检只读，不做 DDL、GRANT、业务 INSERT/UPDATE/DELETE、Redis写入或对象删除。未运行供应商探测或任何真实模型请求。

因此正式成功率、阶段 mean±std、CER 和费用均未测，不能复用 311/47 项离线测试或旧 P2-1b 数字替代。未来若进入真实试次，ASR 目录价估算仅用真实台账 prompt/completion token × ¥0.8/¥2.7 每百万；未知 usage 保持未知，不作为零费用。

## 清理与保护

resource-cleanup.json 记录仅删除本轮创建的 runtime/extra/tmp/workspace 与测试导入缓存，保留安全日志及证据；临时 unit 由 --collect 自动清理，未重启或 SIGKILL。没有本轮任务或派生对象，因此没有数据库、Redis、存储删除操作。

before.json / closeout.json 对比原有证据哈希、在线服务身份与 JAR、冻结候选和原有未提交文件 inode/size/mtime。DIAGNOSIS.md 正文未读、未提交。隐私检索事件只记元数据，不复制错误返回的正文片段。

```bash
sha256sum --check --quiet eval/p2-1c-run-20261016T191343Z/SHA256SUMS
git diff --check
```

SHA256SUMS 从仓库根目录校验本轮公开文件、安全私有日志和原冻结 JAR，不包含配置值、环境文件、credential 文件或任何供应商正文。
