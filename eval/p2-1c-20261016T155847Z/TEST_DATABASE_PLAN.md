# 独立 MySQL 测试依赖：已获许可并启动

当前 `SYSTEM_MODEL_TEST_JDBC_URL` 未配置。独立 MySQL 检查不能以跳过代替通过；本轮不读取部署配置、不连接未核实的共享数据库，也不启动或重启应用。

用户已批准并执行 `start_unit_mysql.sh`，实际身份见 test-database.json；后续可复用同一许可。它只创建新容器 `lecturelens-p21c-unit-mysql-20261017`：

- 使用本地已有镜像 `mysql:8.4`，固定 image ID `sha256:3466ba4a4828aa8d46fb7c3bc16b67b781c98413cf4ea0fac6feaa6e881faa26`，不拉取镜像。
- 仅监听 `127.0.0.1:33316`，入口库 `lecturelens_p21c_test`，数据放独立 1 GiB tmpfs，内存上限 1 GiB、CPU 上限 1；无生产卷、无应用配置、无供应商凭据。
- 仅此隔离测试依赖允许空数据库密码。测试 fixture 自动创建/删除自己的随机 schema；不能使用 P2-1b 运行库作为单测库。
- 脚本先检查磁盘与端口/容器名；有占用则停止，不修改已有容器、不重启。
- 测试结束仅停止并移除该确切名称且标签匹配的本轮测试容器；启动与清理一并请求用户许可。不访问演示/验收或其他受保护资源。

获许可后启动命令：

```bash
cd /home/dev/projects/lecturelens
nohup timeout 120 bash eval/p2-1c-20261016T155847Z/start_unit_mysql.sh > /tmp/lecturelens-p21c-unit-mysql-start.log 2>&1 < /dev/null &
```

就绪后独立 MySQL 机制检查命令（由 fixture 隔离；provider 为确定性替身）：

```bash
cd /home/dev/projects/lecturelens
SYSTEM_MODEL_TEST_JDBC_URL='jdbc:mysql://127.0.0.1:33316/lecturelens_p21c_test?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC' \
SYSTEM_MODEL_TEST_MYSQL_USER=root \
nohup timeout 660 python3 eval/p2-1c-20261016T155847Z/run_check.py --name stage1-mysql-01 --seconds 600 -- \
./mvnw -o -B '-Dtest=SystemModelRuntimeMySqlTest,SystemModelMySqlIntegrationTest,LearningPackageTransactionIntegrationTest' test \
> /tmp/lecturelens-p21c-stage1-mysql-launcher-01.log 2>&1 < /dev/null &
```

启动许可只用于本测试依赖，不包括隔离 Java `18091` 的启动、重启或故障注入；那些操作仍需另行停下请求许可。
