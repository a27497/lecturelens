# 独立 PostgreSQL 测试依赖：待单独启动许可

DESIGN 的全量验证包括 Python/PostgreSQL；当前 AGENT_TEST_DATABASE_URL 未配置，Python fixture 在缺少该值时会跳过数据库用例，不能作为完整通过。本轮不连接未核实的共享 PostgreSQL 或读取部署配置。Python Agent 源码未变，本项为全量回归，不是 Agent 质量重验。

已准备 start_unit_postgres.sh，尚未执行：新建 `lecturelens-p21c-unit-postgres-20261017`，只绑定 `127.0.0.1:33317`，数据库 `lecturelens_p21c_agent_test`。使用已有 pgvector/pgvector:0.8.6-pg17 镜像，固定 image ID `sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f`；不拉取镜像。独立 1 GiB tmpfs、内存上限 1 GiB、CPU 上限 1，无生产卷、无供应商配置；仅本地测试依赖使用 trust 认证。

脚本检查磁盘、端口和容器名，未知占用立即停止，不改任何已有容器。启动与测试结束后仅停止、删除该确切容器一并请求许可；不含 Java 18091 或任何其他服务的启动/重启。

获许可后才执行：

```bash
cd /home/dev/projects/lecturelens
nohup timeout 120 bash eval/p2-1c-20261016T155847Z/start_unit_postgres.sh > /tmp/lecturelens-p21c-unit-postgres-start.log 2>&1 < /dev/null &
```

就绪后的全量 Python 测试命令：

```bash
cd /home/dev/projects/lecturelens
AGENT_TEST_DATABASE_URL='postgresql://lecturelens@127.0.0.1:33317/lecturelens_p21c_agent_test' \
nohup timeout 1860 python3 eval/p2-1c-20261016T155847Z/run_check.py --name stage4-python-full-01 --cwd agent-service --seconds 1800 -- \
./.venv/bin/python -m pytest --junitxml=/home/dev/projects/lecturelens/.data/p2-1c-20261016T155847Z/checks/stage4-python-full-01-junit.xml \
> /tmp/lecturelens-p21c-stage4-python-full-01.log 2>&1 < /dev/null &
```

run_check 只转发基础工具环境和显式测试数据库变量，不读取/转发供应商或部署凭据。实际用例数、失败/跳过数与日志 hash 必须执行后从 JUnit 记录；当前均未测。
