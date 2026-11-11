# T0b 冻结：验证未完成

遵循本任务“若下面的验证第二次仍失败……停止，写 FREEZE.md”的边界，在第二个验证包装器返回失败后停止。未继续修正验算器或重建第三个容器。

- 仅在 `/home/dev/projects/lecturelens-pr` 的 #34 分支修改 compose MySQL 参数及现有部署说明；6 行新增。未修改源工作目录、任何 V*.sql、PR base 或已推送历史。
- 对照组：binlog=ON，trust_function_creators=OFF，应用账号仅有 `courselingo.*` 权限、无 SUPER；V25 第112行实际复现 `ERROR 1419 (HY000)`。原始片段见 CONTROL.txt。
- 初始包装器在容器已删除后，因只识别大写 Docker 错误字符串而失败。确认实际输出为小写 `error: no such object` 后，保留失败记录、修正删除校验并继续首次实验组；没有重复执行对照组。
- 实验组：binlog 保持 ON，trust_function_creators=ON，同一非 SUPER 应用账号；#34 V1–V25 成功，SHOW TRIGGERS 确认4个触发器。
- #35 顺序 SQL 执行走到了 V31 之后的触发器检查，但包装器以 `TRIGGER_COUNT_MISMATCH` 失败。按 `SHOW TRIGGERS --raw` 的物理行数计数无法可靠处理 V30 的多行正文；该次查询输出未保存，不能宣称 #35 全部验证通过。
- 两个本任务临时容器均已删除（包括 `--volumes`），原 ID 的 inspect 已确认不存在；临时凭据文件已删除。未操作其他容器/线上服务/harnesslab，没有启动 Java。

冻结时磁盘 77.33%，距85%约 11.06 GiB；用时 6.23 分钟，未超过1.5小时。

当前没有新 commit、没有把 #34 merge 到 #35、没有 push。#34原HEAD `0471652`，#35原HEAD `fefa5d5`；改动和证据留作本地审阅。需要用户另行授权继续验证，才会修正验算器、补采 #35 的触发器输出并按原计划提交/同步。此次失败不能改写成成功。
