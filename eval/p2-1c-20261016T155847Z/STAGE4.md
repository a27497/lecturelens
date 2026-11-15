# 阶段 4：全量回归通过，真实运行等待 Java 启动许可

| 检查 | 实际结果 | 原始索引 |
| --- | --- | --- |
| 后端首轮全量 | 1765 项，1 failure，0 errors/skipped | stage4-backend-full-01.json |
| 装配夹具修复复核 | 3 项全部通过，0 失败/错误/跳过 | stage4-assembly-fix.json |
| 后端全量重跑 | 1765 项全部通过，0 失败/错误/跳过 | stage4-backend-full-02.json |
| 前端全量 | 119 项全部通过，0 失败/错误/跳过 | stage4-frontend-full-01.json |
| 前端类型检查 | 退出 0；不是单元测试，不计用例数 | stage4-frontend-types.json |
| 离线 package | 退出 0，-DskipTests；不作为额外测试通过 | stage4-package.json |
| Python/PostgreSQL 首轮 | 727 项，1 failure，0 errors/skipped | stage4-python-full-01.json |
| Python/PostgreSQL 重跑 | 727 项全部通过，0 失败/错误/跳过 | stage4-python-full-02.json |

后端首轮失败是配置装配夹具缺少 Pipeline 现有依赖。只补齐 mock bean，不把生产依赖改成可选、不放宽断言。补丁在 stage4-test-fixture.patch；首轮失败与重跑原始日志/JUnit 均保留。

默认 Maven 单元回归不包含显式 PreparationOverlapProbe 特性验收入口。C/E 的两项特性探针仍为失败，本候选不包含 C/E，不能用 1765 项通过抵消它们。

## 候选与资源

Java JAR 已本地归档：.data/p2-1c-20261016T155847Z/candidate/backend.jar。精确大小、SHA256、生产源码身份/逐文件 hash 在 candidate-artifact.json；构建元信息与旧包名的存储 class 不存在检查在 candidate-build-info.json。source_commit 固定生产代码，测试夹具未提交补丁另有 hash；没有修改候选 JAR 字节。

candidate-options.json 是待实际启动核验的参数，不冒充已运行配置。候选意图为 A 原文模式、B 自适应上限 4、D 合并、F 16000/mono、G 测速缓存 OFF，C/E 均 false；上下文 8192、64 次调用、6 层 reduce、900 秒资料期限不扩大。没有改系统模型绑定，没有调用供应商。

测试 MySQL 由用户明确授权创建，所有检查完成后按确切 ID/image/标签核验，仅停止删除该容器；见 test-database-cleanup.json。PostgreSQL 按后续独立许可创建并在测试后仅停止删除该确切容器，见 test-postgres.json/test-postgres-cleanup.json。Java 18091 未启动，正式试次提交 0。历史阶段快照保留在 stage4-checkpoint.json；全量门禁完成后的磁盘/端口/容器核验见 stage4-gates-verified.json，df 显示 76%。

## 继续边界

Python 已使用获准的独立 PostgreSQL 完成全量，0 跳过。首轮 1 项失败来自计划库名不在既有 pilot 安全白名单内；只在同一容器内创建白名单库 lecturelens_agent_test，不改生产/测试代码或安全校验，重跑全部通过。库名调整命令在 test-postgres-database-adjustment.json，DSN 与执行命令在 POSTGRES_TEST_PLAN.md；首轮日志/JUnit 保留。唯一 warning 是已安装 Starlette/AnyIO 的弃用提示。

全量机制门禁通过，不代表真实课程验收完成。candidate-artifact.json 是打包时的历史快照，内含当时 Python 未测状态，保持原样；后续通过状态与候选源码/配置/JAR 字节一致性检查见 stage4-gates-verified.json。C/E 继续排除。

未执行旧 runtime_support.py：其 deployment() 会读取供应商凭据文件，不能直接沿用为本轮启动器。后续真实 Java 入口需使用现有系统模型管理/受控配置引用，不能由外部脚本提取或复制 API Key；Java 启动/重启仍单独请求许可。当前没有因这个问题读取任何实际密钥文件。

## 只读复算

- `python3 eval/p2-1c-20261016T155847Z/verify_checks.py --prefix stage4-backend-full- --final stage4-backend-full-02.json`
- `python3 eval/p2-1c-20261016T155847Z/verify_checks.py --prefix stage4-frontend-full- --final stage4-frontend-full-01.json`
- `python3 eval/p2-1c-20261016T155847Z/verify_checks.py --prefix stage4-python-full- --final stage4-python-full-02.json`
- `sha256sum -c eval/p2-1c-20261016T155847Z/SHA256SUMS`
- `sha256sum .data/p2-1c-20261016T155847Z/candidate/backend.jar`

所有原始测试日志/JUnit 位于 .data/p2-1c-20261016T155847Z/checks/，各 JSON 记录精确命令、退出码、路径/hash 和用例计数。没有真实课程耗时、CER、费用、恢复或缓存演示结论。
