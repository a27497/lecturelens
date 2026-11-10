PHASE1_D_STATUS = PARTIAL

ARCHITECTURE = Python 一次教学生成＋确定性课程检索；复用 Java 权威网关、PG journal 和 Vue Tutor 对话

OFFLINE_REGRESSION = PASS

BROWSER_ACCEPTANCE = PASS

REAL_MODEL_QUALITY = NOT_RUN

NEXT_RECOMMENDATION = FURTHER_INTEGRATION

本轮完成一个独立、可从现有课程页面进入的轻量候选，未启用真实 Provider。下一步仍需把真实 Provider／输出限制与独立一次性费用账本接到这个平面契约，并验证准入与未知发送责任，之后才适合申请新的真实试验授权。本轮不扩大 Tutor 功能，不提高预算，不进入真实 Smoke 或 Phase 2。机械检查不证明教学质量。

工作树 `/home/dev/.codex/worktrees/phase1d-lightweight-tutor-20261108/lecturelens`，分支 `codex/phase1d-lightweight-tutor-20261108`，从 Phase 0 `17d78636cf97fcf55fe642b1ecc30c5e2ea48865` 新建。产品文件散列见 CANDIDATE.json；最终本地提交用 `git log -1 --format=%H -- eval/phase1d-lightweight/REPORT.md` 解析。Phase 0 GitHub CI 始终为 **PENDING**；未 Push、创建 PR、合并或部署。

比较依据和取舍见 COMPARISON.md。Java Course QA 已有可靠单轮证据问答，但不是可取消、可恢复的 Python 多轮状态机；故保留其原功能，借鉴直接检索／回答模式。复用 P8 的授权、版本、持久化、幂等、取消、删除和现有界面，提供 `TUTOR_ENGINE=light` 的 opt-in 执行路径。未移植 v19 或 Phase 1-C 历史；去掉模型选搜索工具、Source/Explanation 层级分块、意图模板、计算器、自动评审和共享修复循环。

每轮最多两次确定性 SEARCH（当前问题及初始／最近主题检索提示，各≤500字符），随后 READ 全部本轮观测 ID；完整学习者问题和六轮内全部原话／已发布回答另行传给模型。模型只返回 `{outcome,text,focus}`，选择讲解、针对性提问或证据不足。一次生成后校验并复核来源，失败直接停止，不修复、不重试、不截断答案。旧会话保留 `engine=p8`、原 ID 与限额；新会话使用独立 light-tutor UUID 名称前缀，并在 LIST/GET 和 worker discovery 上隔离，避免混用协议。Java／MySQL 没有新增 Tutor 状态。

单轮仍为 64,000 保守预留单位、1,200 output-token reserve、20秒、1,600 字符正文和最多4个引用；六轮／六次生成、会话384,000单位。单位为完整 UTF-8 请求/schema 字节加输出预留，**不是实际 tokens 或美元账单**。没有用更高预算掩盖协议问题；超限明确失败。正常请求、响应、来源快照、预留和 provider usage 保存在原 PG journal。无来源时本地拒答，生成调用为0。发送前 reservation 持久化；received 可无调用恢复，reserved 未知结果不重发。失败／取消后保留原始返回与可用 usage，公共失败状态不展示草稿。

教学机制覆盖完整讲解、完整注释代码、多个子问题、索引／计算、显式缺失部分、变式前提、多轮原话和具体提问焦点。历史题目仅在测试私有副本中使用，没有把人名、数值、答案或 ID 写入产品逻辑；另有图算法与合成异步课程流程。纯摘录和无 focus 的泛问会停止，但词法检查不等于语义裁定。测试特意保留一个“有效引用＋错误图算法主张”可通过机械门禁的负例，绝不计作质量成功。详见 QUALITY_BOUNDARY.md。

真实 v19 失败 ZIP SHA256 `832e20a6e066603b57a858a50ddbd2eda355757ba821e4119c6056339299b30d` 不变；旧 runner 的34个执行／wire文件与包内逐字节相同。原题／参考／来源／失败不改写：旧结果仍为2 completed／1 failed，前两回合有明确遗漏，第三回合预算失败；历史9次真实请求及费用不属于本轮。原授权未复用。

实际检查及退出码由 CHECKS.json 和 `.data/phase1d/evidence/` 中的 supervisor 记录核对。Python 使用真实独立 PG，未跳过数据库用例；Java 源码和依赖未改，另跑网关／Authority 相关测试。Vue 全量测试及构建重新执行。未机械重跑无关 Java 全量、全部 Python 模块或完整 GitHub CI，未继承历史成功状态。

| 检查 | 实际结果 |
| --- | --- |
| 首次 Python 组合 | 170 pass／2 fail，退出1；两个测试错误地用 GET 读取已变 stale 的会话。改为直接核对测试 PG 失败记录，未放宽失效历史行为。 |
| 串行组合回归 | 172 passed，0 skipped，退出0；含147项原 Tutor／citation 回归及当时25项新候选测试。 |
| 最终候选专项 | 29 passed，退出0；包含原真实三题原文及 authored 三轮、上下文、来源／版本失效、预算、取消、重启、未知发送、删除。后补真实模式工厂拒绝测试1 passed，退出0。随后复核引擎身份并完成最终组合 **178 passed、0 skipped，退出0，103.07秒**；不是178项教学质量结论。 |
| Java 网关／权威 | 19 passed，0 skipped，退出0；Maven 编译687个生产源文件后通过。 |
| Vue | 338 passed／47文件，退出0，串行约78秒。 |
| 类型与构建 | `npm run build` 退出0；包含 vue-tsc。保留现有大 chunk 警告，未进行性能优化。 |
| 静态 | Ruff、format、Python 内存编译、Node syntax、git diff whitespace 检查退出0。 |
| 依赖 | Python/Vue/Java依赖及锁文件相对 Phase 0 未改；复用本地锁定环境和独立依赖副本，未运行新的 npm audit 或重新安装。 |
| 跨服务／浏览器 | 最终 G **PASS，退出0**；真实 Java→Python→PG＋Chromium/Vue，浏览器旅程约26秒。完整解释／多部分、变式、针对性引导、追问、原文定位、刷新恢复、证据不足、摘录拒绝、六轮停止均通过；排队取消、运行中取消、SIGKILL/恢复、越权404及版本失效409通过。 |

保留全部长检查失败和未完成运行：首次并行检查因主机内存压力导致 Python、Java、前端、构建及首个整栈检查 timeout（124）。已停止仅属于本任务的新容器，串行重新验证；没有修改测试超时断言来掩盖失败。隔离 RocketMQ 的直接内存上限过低又导致一次整栈失败；只调整新测试栈资源配置。中间两次浏览器脚本分别错误期待来源定位隐藏 Tutor、期待详情展开状态跨刷新保留；修正检查方式，产品行为未为此改变。另外修正了两个验收夹具问题：停掉 API 后提交消息不可行，改用独立 PG 会话 advisory lock 暂停执行器；运行中取消的 entered 标记原为零字节，改为与既有验收一致的时间戳。以上原日志和截图均保留。

长检查采用原样复制的 `scripts/dev/run_check.py`，在新 `/dev/shm/lecturelens-phase1d-checks-20261108` 管理日志／临时产物，原门禁实际检查该文件系统且未修改。首轮超时后有自有容器未被上层进程回收，已核验项目标签后按精确 ID 停止并记录。完成的 RAM 证据逐文件校验后复制到持久工作树；只清理这些已验证的本任务 RAM 重复副本，不触碰原资产。

剩余边界：Java 权威返回至多1200字符／Evidence片段，prompt 明示其不一定是完整课程；不能保证检索覆盖所有必要点。1,600字符可能不足以讲清长任务，应说明未覆盖部分并拆问；程序不偷偷裁剪。完整上下文传输不能证明模型遵循变式；合法引用不能证明语义支持。轻量入口目前严格 Mock-only；真实 adapter／美元账本接线、独立语义质量评审、真实多轮教学和远端 CI 均未完成。**本轮新增真实模型／reviewer／付费 embedding 请求0，新增供应商费用 US$0。**

保护核查与测试资源收尾见 PRESERVATION.json。已核对原50个其他工作树无 HEAD／状态变化，原失败资产未改；既有23个运行容器及四个服务保持原身份；没有对业务数据库执行 SQL，也未重启既有服务。所有 SQL 仅指向本轮独立数据库，课程变更仅限新合成课程。测试卷保留以便审计。首轮超时留下的一个测试 schema 保留在已停止的首个独立 PG 卷内；不属于业务库。

复核新增引擎身份时，以合法旧请求键 `s:light` 复现了后缀方案的 UUID 碰撞（专项退出1）；改为独立名称前缀后复测。这是本轮新候选的已修复缺陷，原 P8 UUID 输入和冻结工作树均未改动。失败反例和修复后的完整回归都保留。

原三回合原文＋完整课程证据的 authored 回归：每轮1次请求，保守预留分别17859、18692、19108，均小于64000；三个完整回答均原样保存。完整 Mock 请求、响应、checkpoint、状态、用量和预留在 `.data/phase1d/offline-evidence/0b6aed498fc14fad88e297a82d1e687c/`，不进入 Git，不冒充真实生成。

最终整栈的9个合成回合为6 completed／2 cancelled／1 source-only failed，8次 authored Mock 生成，最大单轮预留6002，自动重试0、真实请求0。原始请求／响应在 `.data/phase1d/evidence/integration-g/authored-requests.jsonl`，完整 PG session/turn/checkpoint/usage 在同目录的 `tutor_session.json`、`tutor_turn.json`。截图 `browser-restored.png`、`browser-stopped.png`、`browser-bound.png` 和 `browser.json` 均已持久保存。源码摘要与 CANDIDATE.json 对应，所有长检查终态和退出码含早期失败均见 CHECKS.json。

最终两个单测 PG 实例均已按精确归属停止，持久卷保留；最终审计 PG 剩余测试 schema 为0。首次压力期间没有采样原服务请求延迟；能确认它们未重启、未退出，不能据此宣称瞬时延迟完全不受影响。没有为了整栈通过修改 Tutor 限额或旧评测判分。
