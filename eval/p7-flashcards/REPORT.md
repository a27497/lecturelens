# P7 离线证据闪卡与 FSRS 验收

结论：**READY_FOR_REVIEW（离线 Mock 候选；未部署，不代表真实生成质量通过）**。

执行日期：2026-10-26 UTC；Compose 项目名按任务指定使用 `20261027`。
开工执行 `git fetch origin` 后 main 未前进：基线与 origin/main 均为
`1b4dc696cc61e4f3828c6f0c6a7eaabab8dd451f`，无需 rebase。
工作分支 `codex/p7-evidence-flashcards`；实现提交 `80d7d19`，随后仅补本报告与脱敏检查摘要。
完整最终 HEAD 与提交列表由交付消息提供，避免在提交内自引用其 SHA。
**未 push、未创建/修改 PR、未合并。**

## 已完成

学习目标、数据/命令、所有权、参数、幂等、版本/删除和只读边界见 [简短设计](../../docs/P7_EVIDENCE_FLASHCARDS.md)。
课程页「闪卡复习」支持显式生成、今日已到期队列、翻面、自评、证据展开、回看视频、取消和持久进度恢复。
生成走原 Run/checkpoint/journal/预算，评分确定性执行。PostgreSQL 新三表，Java 只有网关操作与校验，无 MySQL 表/Flyway 变更。

| 最终检查 | 通过 / 失败 / 跳过 | 证据 |
| --- | --- | --- |
| Python 全量，真实独立 PostgreSQL | **887 / 0 / 0** | `python-full-p7`，pytest 270.28 秒 |
| 其中 FSRS 固定数据 | **14 / 0 / 0** | `tests/test_scheduling.py`，首次四评分、学习/遗忘/重学、UTC、无随机性 |
| 其中闪卡运行与存储 | **22 / 0 / 0** | `tests/test_flashcards.py`，同 key 并发重放/不同 key 冲突、引用解析、跨用户/课程、revision、取消、删除/checkpoint、只读无 Run、Mock socket、持久预算 |
| 其中出处统计入口 | **6 / 0 / 0** | 输入 SHA、缺项、重复、错误引文与 revision 拒绝 |
| Java 受影响模块 | **21 / 0 / 0** | StudyControllerTest 9 + StudyAuthorityTest 12 |
| 前端全量单测 | **265 / 0 / 0** | 42 个测试文件；新增10项，覆盖恢复/评分/重试/冲突/越权/晚到结果/取消 |
| 前端类型检查 / 生产构建 | **通过 / 0 / 0** | `frontend-types`；最终 `frontend-reviewed-build` 内含 vue-tsc |
| 浏览器闭环 | **5 / 0 / 0** | `browser-p7-viewports`；无页面错误/外部请求 |
| Ruff / format / git diff --check | 通过 | 66 个 Python 源码/相关测试格式通过；额外 eval/监督脚本 lint 通过 |

Python 完整回归含此前执行、权限、持久预算、恢复、取消、版本和删除机制测试。
没有将数据库 skip 当作通过，也没有将 Mock 的工具选择当作模型智能。

浏览器使用真实 Chromium、生产 Vue 构建、HMAC Python API、真实 PostgreSQL 及本地产生的 H.264，验证：
初次读取无 Run → 显式生成 → 翻面/来源 → 两页签同卡版本评分冲突 → 刷新恢复 → 原文/播放器定位。
**Java 身份/课程业务接口仍为本地夹具**，不是完整 Java/MySQL 业务栈验收；Java 边界由上述受影响模块测试验证。
没有把固定 API 夹具称为真实业务授权通过。

最后一次 Mock 样本：3 张卡、2 次 Mock 决策、2 次工具；Run 创建至成功 **463.305 ms**，
点击生成至页面显示 **1936.305 ms**（含轮询、浏览器与服务调度）。N=1，不声称 p95 或真实 Provider 延时。
单元测试要求 **100% 卡片引用等于当前快照可解析原文/时间**；这不是语义支持率。

截图为精确的 1440×900 和 1280×800：

- [1440×900](../../.data/p7/browser-1793043259653/1440x900-flipped.png)
- [1280×800](../../.data/p7/browser-1793043259653/1280x800-review.png)

截图、原始日志和视频留在被忽略的 `.data/p7/`，不提交媒体。
[浏览器脱敏摘要与 artifact SHA](browser-summary.json)、[检查命令/耗时/日志 SHA](checks.json) 已提交。

## 实际命令与隔离

```bash
# 开工确认端口空闲后，仅创建本轮项目；全量测试需下面的精确库名。
docker compose -p lecturelens-p7-flashcards-20261027 -f eval/p7-flashcards/compose.yaml up -d
docker compose -p lecturelens-p7-flashcards-20261027 -f eval/p7-flashcards/compose.yaml exec -T postgres createdb -U p7 lecturelens_agent_test
export AGENT_TEST_DATABASE_URL=postgresql://p7:p7-local-only@127.0.0.1:25701/lecturelens_agent_test
python3 scripts/dev/run_check.py --name python-full-p7 --timeout 1200 -- uv run --directory agent-service pytest -q
python3 scripts/dev/run_check.py --name java-p7 --timeout 600 -- mvn -q -f backend/pom.xml -Dtest=StudyControllerTest,StudyAuthorityTest test
export PATH=/opt/node/bin:$PATH
python3 scripts/dev/run_check.py --name frontend-final-tests --timeout 600 -- npm --prefix frontend run test:unit
python3 scripts/dev/run_check.py --name frontend-types --timeout 300 -- npm --prefix frontend run type-check
python3 scripts/dev/run_check.py --name frontend-reviewed-build --timeout 600 -- npm --prefix frontend run build -- --outDir ../.data/p7/dist --emptyOutDir
# 浏览器使用同一新容器的另一个独立测试库；25702/25703 均只绑定 loopback。
AGENT_TEST_DATABASE_URL=postgresql://p7:p7-local-only@127.0.0.1:25701/lecturelens_p7_test python3 scripts/dev/run_check.py --name browser-p7-viewports --timeout 180 -- uv run --directory agent-service python ../eval/p7-flashcards/browser_flow.py
```

浏览器脚本先用 `ffmpeg -nostdin -f lavfi -i testsrc2=size=320x180:rate=12 -t 6 -c:v libx264 -threads 1 -pix_fmt yuv420p -movflags +faststart .data/p7/fixture.mp4` 准备合成媒体。
重复检查使用新的 name，保留失败日志。仓库原先缺少指定的 LOCAL_CHECK_EXECUTION.md/run_check.py，本轮补齐，未从其他工作区复制或借用服务。

唯一新容器：`lecturelens-p7-flashcards-20261027-postgres-1`，已执行本项目 `docker compose ... stop`，当前 **Exited (0)**，独立卷保留。
Python/Node 临时服务均退出；25701/25702/25703 已无监听。
未修改原工作区、其他 worktree、生产配置/数据库、历史容器或其卷；只读查看过容器名称以确认隔离。
P6 与竞品文档仅按授权只读参考。

## 失败记录与身份

- 首轮 P7 测试 **20 passed / 16 failed**：旧 task_kind CHECK 未扩展。修复 Python DDL 后 **35 passed / 1 failed**：夹具 Evidence 时间随读取子集变化。改为稳定 ID→时间映射，最终完整回归通过。
- 首轮全量使用 `lecturelens_p7_test`，旧成本围栏夹具要求精确 `lecturelens_agent_test`，中断且不计为完整通过；随后在同一新容器创建所需独立库。
- 第二轮全量遇到旧 P3 源码身份围栏，诊断 **3 passed / 1 failed**，其余执行中断、不计为完整通过。没有放松校验或改写旧 manifest。
- 本轮新增 `p7_agent_manifest.json`（60模块），身份 `p7-flashcards-56df1f68a682ab00`，SHA `56df1f68a682ab001e3b0f151adf6bcfc0b953aabcf59cf64c9bb7a339e56333`。离线成本机制改用独立 P7 身份，83项独立回归通过；旧 paid/live 许可没有开放。
- 原 `acceptance_agent_manifest.json` SHA `d94e896c768c0bf74c66b11f2105a1e541fe01f1c94ea1f14710d5c1a2777f00`、原 `development_agent_manifest.json` SHA `480fc58639fd4a595fa34f6e3ae6d1e489107094da36a9cc71b9c661821fcb25` 均未变。新增压缩只读基线源片段供历史正例重建；不依赖 Git checkout、不将 P7 冒充旧候选。
- 浏览器早期分别因夹具缺协议 scope、遗漏 Evidence 路由、端口 TIME_WAIT 预检失败而退出；日志保留。修复夹具和可复用本地端口预检，成功后改为精确 viewport 截图再次验收。
- 自审发现网络丢响应后，下一卡的评分按钮可能重试上一卡评分；已增加独立「重试上次评分」操作并禁用新评分，单测和最终浏览器/构建通过。

这些是工程检查失败，不是内容质量 trial；没有删除失败日志、覆盖冻结评测资产或把错误输出改标成功。既有 AnyIO/certifi 弃用及构建包体提示保留，不影响本次检查结果。

## 出处支持入口与未验证项

[离线入口](../source-support/README.md) 与命令：

```bash
python3 eval/source-support/measure.py --candidate eval/source-support/example-candidate.json --ratings eval/source-support/example-ratings.json --output .data/p7/support-example-NEW.json
```

合成 Mock 示例：2/2引用解析、1 supported/1 unsupported，source_support_rate=0.5，`MOCK_NOT_QUALITY`。
统计入口不自动判断语义；它绑定独立判定和精确引文，不把引用存在性当作支持，也不覆盖旧输出。
真实样本/调用上限/费用公式/停止条件见 [NOT_RUN 质量方案](QUALITY_PLAN.md)。

- **已完成**：本轮离线运行/存储/调度/网关/UI/机制检查及本地提交。
- **未验证（NOT_RUN）**：真实生成支持率≥0.90、真实 Provider 适配、未见课程质量、长期复习收益、完整真实 Java/MySQL 业务浏览器链路、生产验收。浏览器本身已运行，不是 BROWSER_NOT_RUN。
- **受阻**：无仍在阻塞本轮离线候选的问题。真实生成入口有意保持 Mock-only。
- **需用户授权**：未来真实模型试验和部署。未来 DeepSeek 累计 US$10 上限不构成本轮调用授权；精确型号/价格待核实。

**真实付费 Provider 调用数：0；生产/历史容器写操作：0。**

## 改动按层

- Python：`agent-service/study/{flashcards,flashcard_graph,scheduling}.py`（实际位于 `src/lecturelens_agent/study/`）；contracts/store/runtime/provider/learning_scope；独立 P7 manifest 与 offline acceptance_cost；pyproject/uv.lock；flashcards/scheduling/source_support 测试、历史身份测试与只读基线片段。
- Java：`StudyController.java` 及 `StudyControllerTest.java`；没有 MySQL/Flyway 文件。
- 前端：`api/study.ts`、`CourseFlashcardsPanel.vue`/测试、WorkspaceNav/workspace/courseLocation、TaskDetailView、`tests/browser/flashcards.mjs`。
- 文档：根/Agent README、P7 设计、LOCAL_CHECK_EXECUTION、产品契约、API、架构、DB_SCHEMA、DEPLOYMENT、L2/L3/蓝图。
- eval/工具：`eval/source-support/`；`eval/p7-flashcards/` 的隔离 Compose、浏览器驱动、质量方案、报告/摘要；`scripts/dev/run_check.py`。
