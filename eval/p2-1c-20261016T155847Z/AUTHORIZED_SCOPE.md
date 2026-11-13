# 阶段 0 后的实施授权

用户已确认按 DESIGN.md 进入阶段 1，并补充以下约束；与原设计有差异时以此为准。

- 阶段 3 的 C/E 若测试不能稳定通过，允许以 `streamingTranslation=false`、`materialsParallel=false` 冻结 A+B+D+F+G 候选；SUMMARY 必须注明 C/E 未纳入，其他门禁不放松。
- A 优先；资料生成真实调用若仍失败，正式十次继续并保留失败，不扩大上下文或调用/时间预算以求通过。单节冒烟的 ASR 必须正常且无 403；单独资料失败不阻止正式十次，机制检查失败仍需先修复。
- 每阶段本地提交后简要报告测试并继续；遇服务启动/重启、403、磁盘门禁则停下。此前设计中的相关审批边界保留。

不 push、不 merge、不部署，不读取或操作供应商密钥、不接触保护资源。已有未提交文件保持原样。

用户随后明确批准启动 `lecturelens-p21c-unit-mysql-20261017`（127.0.0.1:33316）做独立 MySQL 测试，后续阶段可复用同一许可，测试结束仅停止并删除该确切容器；不含 Java 18091 或其他服务启动/重启。

用户随后明确批准按 POSTGRES_TEST_PLAN.md 启动 `lecturelens-p21c-unit-postgres-20261017`（127.0.0.1:33317），运行 Python 全量，结束后仅停止并删除该确切容器。此许可不含 Java 18091。

用户随后指定通过 `sudo systemd-run` 创建临时 unit `lecturelens-p21c-worker-20261017`，只引用 live backend 两个指定 drop-in 中既有 LoadCredentialEncrypted 路径：90-asr-bailian.conf 的 bailian-asr，以及 99-system-models.conf 的凭据项。允许仅检查凭据指令名和路径，不输出 Environment 行或凭据内容；若 99 使用明文 Environment 密钥则停止，不复制。允许启动隔离 Java 127.0.0.1:18091、cache OFF 单节冒烟，ASR 正常且无 403 后继续正式十次，结束后停止该临时 unit。不得 restart/stop 任何 lecturelens-live-* 服务或容器；SIGKILL 恢复仍需单独许可。检查结果未取得 99 的任何凭据指令/路径，尚未创建或启动 unit，见 stage5-startup-preflight.json。
