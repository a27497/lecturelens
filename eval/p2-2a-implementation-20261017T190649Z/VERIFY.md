# P2-2a 本地实现与只读预检

状态：拟默认开启，未发布。用户批准设计并限定本轮只读预检、独立环境机制检查和本地分阶段提交；不 push，不执行真实浏览器/模型验收，不启动或重启 Java，不操作现有服务或数据库。

## A. 只读预检及上一轮观察更正

命令：`systemctl show lecturelens-live-backend.service -p ActiveState,SubState,MainPID,ActiveEnterTimestamp`；同样查询 `lecturelens-live-agent.service`。具体字段见 [preflight.json](preflight.json)。

| unit | ActiveState / SubState | MainPID | ActiveEnterTimestamp |
| --- | --- | ---: | --- |
| lecturelens-live-backend.service | active / running | 4682 | 2026-10-17 07:35:50 UTC（北京时间 15:35:50） |
| lecturelens-live-agent.service | active / running | 4681 | 同上 |

`ss -ltnp` 确认 Java PID 4682 监听 `[::ffff:127.0.0.1]:8080`，Python PID 4681 监听 `127.0.0.1:8090`；另有模型 8091、网关 443、MySQL 13306、PostgreSQL 15439。未见历史演示端口 8084/8094/5184。`ss -tnp` 可看到 PID 4682 到 13306、16379、18081 的连接。

**live backend 当前 active；没有恢复操作。上一轮设计中的“8080 未监听”结论错误。** 当时将 `ss -ltn` 输出截为前 45 行，漏掉末尾 IPv4-mapped IPv6 的 8080 行。该历史调研缺陷在此明确更正，原 DESIGN/OBSERVATIONS 按本轮文档范围保持原样，不用它们的端口结论判断现在的服务状态。

“是否存在一个正在运行且已授权、正好连接 `lecturelens_learning_loop` 与 `lecturelens_agent_loop_test` 的 Java/Agent 组合”：**未知**。已有进程与端口不证明具体 MySQL schema、PostgreSQL 库或当前课程账号授权。本轮没有读取 EnvironmentFile、credential、真实 `.env*`、`/proc/*/environ`，没有为了猜测数据库配对而读取配置/密钥或访问现有库。后端选择留给用户；未把 active 当作课程链路健康或数据库配对成功。

## B. 实现范围

- `feedback_store.py`：只把缺省 `STUDY_FEEDBACK_ENABLED` 从 false 改为 true；显式 false、权限、持久预算、checkpoint、版本及模型逻辑保持原语义。
- `.env.agent.example`：示例开关同步 true；未改任何真实环境文件或运行配置。
- `PracticeFeedbackPanel.vue`：复用已有时间格式，引用按钮显示起止区间和“片段起点”，保留每条引用的毫秒 seek 参数。
- `CourseAgentPanel.vue`：“跳到视频”改为“回看片段起点”，沿用已有起止时间和毫秒事件。
- Python 测试：验证未配置/显式 true/大小写兼容、必须保存真实答案、反馈入队与幂等；显式 false 拒绝新反馈，但旧反馈/核对记录可读、核对可保存、答案可继续修改，旧反馈仍绑定旧答案。
- 前端测试：更新单来源、多来源和学习产物引用断言，同时断言显示时间与精确 seek 毫秒值。
- 公共说明只改 `docs/DEPLOYMENT.md`、`agent-service/README.md`，明确“拟默认开启，未发布”、owner 范围、主动请求及回退。其他公共文档等待真实验收；未改旧设计、FREEZE 或冻结评测记录。

## 检查隔离与记录

新检查均由 `scripts/dev/run_check.py` 管理，使用独立记录名、有限 timeout、终态及后代回收检查。无 Java/JVM 构建或测试，无 provider 调用，无 CI 操作。

Python 使用本地缓存 `pgvector/pgvector:0.8.6-pg17`，每次新建带时间戳的独立容器、随机匿名卷、随机凭据、仅 `127.0.0.1` 的随机宿主端口，库名 `lecturelens_p2a_test`。只在新容器中创建 vector 扩展并执行测试；没有连接 `lecturelens_agent_loop_test` 或任何现有库。每次检查结束均按本轮容器 ID 删除容器及卷，再确认不存在。凭据不写入参数、报告或 Git。

前端从当前 tracked 工作区文件复制临时源码快照，排除全部 `.env*`，只复用已有 node_modules。测试和 `npm run build` 均在副本中运行，避免 Vite 自动读取原环境文件，build 输出亦在副本中，**没有覆盖 live 网关挂载的 frontend/dist**。已核对 4 个改动源码/测试与已测试副本逐字节一致。build 有既有第三方 PURE 注解警告，退出码为 0。

### 失败记录保留

1. 首个临时容器 `lecturelens-p2a-pg-20261017T190649Z` 准备失败，pytest 未启动；原报告为 STARTING 加 CalledProcessError，不将它当成成功测试。未捕获底层 stderr，根因未知。随后把准备就绪检查改为容器内最终 TCP 服务就绪，避免仅凭初始化期间的 socket 可连接开始检查；这是预检稳健性改动，不作为首个失败根因已证实的结论。
2. 第二个独立容器 `…-r2` 完成测试：99 项中 98 通过、1 失败、0 跳过。新增测试未声明 `practice` fixture，调用 helper 时传入 fixture 定义，引发 TypeError。此前的关闭开关、作答/反馈保留、核对保存断言已通过。只修正测试签名；原记录、JUnit 和 supervisor FAILED 终态保留。
3. 最终复验使用另一个全新容器 `…-r3`；正式数字及清理结果见 [checks.json](checks.json)。不覆盖前两次记录，不用最终成功重标历史失败。

| 最终检查 | 结果 | reviewer |
| --- | --- | --- |
| Python/PostgreSQL：feedback、attempts、study | 99 passed，0 failed，0 errors，0 skipped | 模型辅助，待人工 |
| 前端：反馈、学习入口、作答、播放器 4 个文件 | 31 passed，0 failed，0 skipped | 模型辅助，待人工 |
| 隔离前端 build | vue-tsc / Vite 退出 0，supervisor SUCCEEDED | 模型辅助，待人工 |
| 静态检查 | 两个 Python 文件 Ruff lint/format、diff whitespace、改动密钥扫描通过 | 模型辅助，待人工 |

前端提交 `347d147`；默认值与 Python 回归提交 `a6181be`。均为主仓库当前分支的本地提交，未 push。收尾磁盘约 78.12%，可用 31.57 GiB，距离 85% 约 9.93 GiB；全过程未触发磁盘停止线。

结果表见 [RESULTS.csv](RESULTS.csv)。所有 reviewer 均为“模型辅助，待人工”；用户本人负责后续人工审阅。机制测试通过不代表真实模型任务质量或人工批准。

原始运行日志、JUnit、资源记录位于本地忽略目录 `.data/p2-2a-impl-20261017T190649Z/` 及 `-r2/`、`-r3/`；supervisor 记录在 `.data/dev-checks/p2a-*/`。公开 `checks.json` 仅保留无凭据的计数、摘要、清理结果和记录哈希。

## 停止点

停在本地实现/检查完成；未执行 G1–G5、登录共享账号、创建真实学习 Run、调用模型或改变服务。每个学习目标结果为 NOT_RUN，reviewer 为“模型辅助，待人工”，不得计为通过。

真实浏览器验收使用哪个后端由用户依据预检决定。本轮没有申请或执行任何 Java 启动/重启；若后续必须申请，应先说明目标 unit/JAR、数据库配对、Flyway 是否会向 demo-l2 执行迁移及其他启动写入。当前这些启动副作用未经核实，不能承诺“不会写库”；未核实并获批前不得操作。不得为此解冻或排障 P2-1c。
