# T0b V25 触发器权限检查：未通过最终门禁

最终状态见 [FREEZE.md](FREEZE.md)：已经止损，不 push、不 merge PR、不更改 base，也未 rebase。两个验证包装器的失败记录分别保留，#35触发器验证未完成。

## 只读检查

#34/#35远端均 OPEN，head分别为 `0471652`/`fefa5d5`，与任务指定一致。迁移/Mock E2E失败、其余三类CI通过；本轮没有重跑远端CI。

完整 rg 结果见 [PRIVILEGED_MIGRATIONS.txt](PRIVILEGED_MIGRATIONS.txt)。#34仅V25的4个触发器；#35另有V27的1个、V30的2个、V31的1个，共8个静态定义。没有显式 `DEFINER=`，没有函数/过程/事件或Java迁移。V30的DELIMITER语法由MySQL客户端支持，没有Flyway占位符。

CI设置 `COMPOSE_FILE=compose.yaml:compose.ci-minio.yml`；叠加文件只有minio/minio-init配置，不覆盖mysql。`scripts/demo/start-infrastructure.sh`只用Compose启动，没有替换MySQL command。未执行demo脚本，也未读取任何现有.env文件。

## 完整代码与部署说明 diff

```diff
diff --git a/compose.yaml b/compose.yaml
index 1b0e0b1..91d378f 100644
--- a/compose.yaml
+++ b/compose.yaml
@@ -4,6 +4,8 @@ services:
     command:
       - --character-set-server=utf8mb4
       - --collation-server=utf8mb4_unicode_ci
+      # V25 triggers require this for non-SUPER migration accounts when binlog is enabled.
+      - --log-bin-trust-function-creators=1
     environment:
       MYSQL_ROOT_PASSWORD: ${MYSQL_ROOT_PASSWORD:-change-me-root-password}
       MYSQL_DATABASE: ${MYSQL_DATABASE:-courselingo}
diff --git a/docs/DEPLOYMENT.md b/docs/DEPLOYMENT.md
index 9a1fd30..6b7065f 100644
--- a/docs/DEPLOYMENT.md
+++ b/docs/DEPLOYMENT.md
@@ -171,6 +171,10 @@ docker compose --env-file .env ps
 
 Compose 配置见 [`compose.yaml`](../compose.yaml)。它会启动 MySQL、Redis、MinIO、RocketMQ NameServer 和 RocketMQ Broker/Proxy，并初始化 MinIO bucket。确认容器状态正常后再启动后端。
 
+自管 MySQL 在启用 binlog、由非 SUPER 账号执行迁移时，需要设置 `log_bin_trust_function_creators=ON`，或由具备所需权限的账号执行 V25。
+V25 创建配置版本和审计保护触发器；缺少该设置或权限会报 `HY000/1419`。Compose 已设置该实例参数，binlog 保持开启。
+该参数放宽实例内触发器/函数创建的 binlog 权限检查，不授予应用账号 SUPER；迁移账号仍需相应的数据库级 DDL/触发器权限。
+
 当前固定 MinIO vendor 镜像的匿名获取问题仍未修复，普通部署配置保留原始镜像 pin。CI 的无 Key Mock E2E 显式加载 [`compose.ci-minio.yml`](../compose.ci-minio.yml)，通过 [`Dockerfile.ci`](../infra/minio/Dockerfile.ci) 从与原镜像 release 对应的同一 commit 的官方源码构建；源码归档 SHA256、Go 工具链和基础镜像 digest 均固定，不声称与 vendor binary byte-identical。该 CI 路径已在 fresh GitHub hosted runner 上通过完整 Mock E2E；远端结果和验证边界见 [CI 后续记录](REPOSITORY_CLOSEOUT.md#2026-10-07-successor-ci-only-minio-source-build)。
 
 ## 10. Windows PowerShell 启动后端
```

## 本地独立验证

采用缓存mysql:8.4、两轮同名但不同ID的临时容器，127.0.0.1随机端口、tmpfs数据、没有生产目录挂载。command仅为compose的字符集/排序规则及实验组新增trust参数；没有 `--skip-log-bin`。应用账号和库与compose缺省一致，密码随机生成且未打印。

用mysql客户端按文件版本数字顺序执行原SQL，未启动Java/Flyway应用；未创建伪造Flyway历史。原SQL SHA256逐份比对保持不变（见results.json），两个分支的migration目录未改动。

对照组原始输出：

```text
ERROR 1419 (HY000) at line 112: You do not have the SUPER privilege and binary logging is enabled (you *might* want to use the less safe log_bin_trust_function_creators variable)
```

实验组#34最高V25、25份SQL完成、0次迁移错误，SHOW TRIGGERS原文见 [B-SHOW-TRIGGERS.txt](B-SHOW-TRIGGERS.txt)。#35包装器在V31后的触发器计数失败，输出未保留，因此不报告成功或把静态8个定义冒充实际查询结果。详见results.json。

## 提交/同步状态与记录

尚无新的提交SHA。未执行计划中的#34 commit/#35栈merge，两个分支保持原head。未运行push dry-run：在止损前没有产生待推送提交，旧head的dry-run不能证明本次修复可推送。

两个分支的git log --oneline -3：

```text
B:
0471652 docs: record system model deployment and rollback verification
9655ac9 P1-4④：增加管理员模型页面与有界连通性测试并汇总验收
d326b7f P1-4③：按任务冻结配置切换 ASR 供应商
C:
fefa5d5 test(mysql): expect P2-1b schema V31 in fresh and upgrade regression
9a46f05 test(pipeline): register checkpoint and policy dependencies in executor fixture
40ae33a feat(pipeline): publish bounded long-course translation and checkpoint evidence
```

包装器初次/实验组均FAILED，原记录位于Git忽略的`.data/ci-v25-trigger-20261017T112531Z/`及`.data/pr-check-tool/.data/dev-checks/ci-v25-*/`。代码改动diff --check通过；密钥/大文件扫描见后附结果。清理记录、磁盘和用时见results.json/FREEZE.md。

扫描：Gitleaks 8.30.1 对两处代码/部署改动和新公开证据扫描，命中0、真实密钥0；大于5,000,000字节文件0。扫描输入SHA256在SCAN.json；临时凭据仅用于容器初始化，文件已删除，未写入公开文件。
