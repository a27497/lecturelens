# 独立 MySQL 验收计划

基准提交 `47de0cc`。用户本轮授权创建和清理新的独立 MySQL 测试实例；不启动应用服务，不复用现存业务数据库。

- 容器 `lecturelens-translation-mysql-20261016T185217Z`，仅映射 `127.0.0.1:33318`，入口库 `lecturelens_translation_test`。
- 本地已有 mysql:8.4 image ID `sha256:3466ba4a4828aa8d46fb7c3bc16b67b781c98413cf4ea0fac6feaa6e881faa26`，不拉取镜像；内存/CPU 各限制为 1 GiB/1 CPU，数据使用独立 1 GiB tmpfs，无生产卷或配置。仅测试库允许空密码。
- 创建前检查磁盘、端口、容器名；冲突则停止。记录创建返回的容器 ID、创建时间、镜像、专属标签、挂载和端口；清理时再次逐项验证，仅删除本轮创建的 ID。
- 使用现有随机 schema + 完整迁移夹具、真实 MyBatis mapper 和 Spring 事务代理。供应商返回值全部合成，传输替身不会发出网络请求。
- 补充 legacy 空 content/length 恢复与 usage、无效输出、深度耗尽、数据库写入失败回滚、失败诊断与任务终态/重复投递边界。
- 运行相关 Runtime、UsageLedger、TranslationCheckpoint、Resume 集成用例，覆盖 V2 持久预算、失败调用台账及 checkpoint 幂等。不同路径的结论分别记录。
- 长命令使用 `nohup + timeout`，Maven 检查使用 `scripts/dev/run_check.py`。保留失败运行和日志，结束后核实随机 schema 清理、停止并删除本轮容器，核验线上身份与受保护证据未变。

真实供应商行为未测；历史十次缺少细分诊断的故障不在本轮重新归因。不运行 P2-1c 正式验收。
