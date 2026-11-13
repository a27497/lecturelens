# 独立 PostgreSQL 测试：方案与实际执行

用户明确批准本方案的启动、Python 全量及仅停止删除该容器；不含 Java 18091。已执行完毕，确切身份和启动日志 hash 见 test-postgres.json，停止删除证据见 test-postgres-cleanup.json。

使用本机已有 pgvector/pgvector:0.8.6-pg17 镜像，固定 image ID `sha256:cf134a767f474095eeba57e0117be8e568e011a63f33fbf252f14c9b760f8e6f`，没有拉取镜像。新建容器 `lecturelens-p21c-unit-postgres-20261017` 只绑定 `127.0.0.1:33317`，独立 1 GiB tmpfs，内存上限 1 GiB、CPU 上限 1，无生产卷、无供应商配置；仅本地测试依赖使用 trust 认证。脚本检查磁盘、端口和容器名，未知占用停止。

初始计划库名 lecturelens_p21c_agent_test 被既有 pilot 脚本的固定测试库白名单拒绝：首轮 727 项中 726 通过、1 失败、0 错误/跳过。未改脚本校验或应用/测试源码；只在同一已核验容器内 createdb lecturelens_agent_test，实际命令见 test-postgres-database-adjustment.json。重跑 727 项全部通过，0 失败/错误/跳过。Python Agent 源码未变，这是机制回归，不是模型质量重验。

首次启动执行的是提交 9b688c3 中的 start_unit_postgres.sh（原计划库名）：

```bash
cd /home/dev/projects/lecturelens
nohup timeout 120 bash eval/p2-1c-20261016T155847Z/start_unit_postgres.sh > /tmp/lecturelens-p21c-unit-postgres-start.log 2>&1 < /dev/null &
```

当前启动脚本已修正为白名单测试库名，修正后没有再次执行或重启容器。第一轮实际测试命令：

```bash
cd /home/dev/projects/lecturelens
AGENT_TEST_DATABASE_URL='postgresql://lecturelens@127.0.0.1:33317/lecturelens_p21c_agent_test' \
nohup timeout 1860 python3 eval/p2-1c-20261016T155847Z/run_check.py --name stage4-python-full-01 --cwd agent-service --seconds 1800 -- \
./.venv/bin/python -m pytest --junitxml=/home/dev/projects/lecturelens/.data/p2-1c-20261016T155847Z/checks/stage4-python-full-01-junit.xml \
> /tmp/lecturelens-p21c-stage4-python-full-01.log 2>&1 < /dev/null &
```

同一容器创建白名单测试库后，重跑实际命令：

```bash
cd /home/dev/projects/lecturelens
AGENT_TEST_DATABASE_URL='postgresql://lecturelens@127.0.0.1:33317/lecturelens_agent_test' \
nohup timeout 1860 python3 eval/p2-1c-20261016T155847Z/run_check.py --name stage4-python-full-02 --cwd agent-service --seconds 1800 -- \
./.venv/bin/python -m pytest --junitxml=/home/dev/projects/lecturelens/.data/p2-1c-20261016T155847Z/checks/stage4-python-full-02-junit.xml \
> /tmp/lecturelens-p21c-stage4-python-full-02.log 2>&1 < /dev/null &
```

清理实际命令（脚本先核验已归档的 ID、image、标签）：

```bash
nohup timeout 60 python3 eval/p2-1c-20261016T155847Z/cleanup_unit_postgres.py > /tmp/lecturelens-p21c-unit-postgres-cleanup.log 2>&1 < /dev/null &
```

run_check 只转发基础工具环境和显式测试数据库变量，不读取/转发供应商或部署凭据。两轮计数、命令和日志/JUnit hash 在 stage4-python-full-{01,02}.json。只读复算：

```bash
python3 eval/p2-1c-20261016T155847Z/verify_checks.py --prefix stage4-python-full- --final stage4-python-full-02.json
```

重新执行必须使用新记录名，不能覆盖旧证据；本次容器已删除，未来新启动仍按当时授权边界处理。
