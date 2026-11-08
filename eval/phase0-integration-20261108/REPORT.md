# Phase 0：代码整合与可信基线稳定

日期：2026-11-08。范围仅 Phase 0；没有进入 Phase 1、调用付费模型、推送、创建 PR、合并或部署。

## 身份与来源

| 对象 | 现场确认 |
| --- | --- |
| 最新 main 基线 | `300be51515867f7ece4f3a9224a484e825219ee0`；原远端 CI success，run `40839881691` |
| PR #53 | `b35be79801d9a4480abff8522b52efb23718eda0`，OPEN，58 个独有历史提交；与 main 的 merge base 为 `56bc07ac3f5f57bb71592047baf12befc90e0448` |
| 集成分支 | `codex/phase0-integration-20261108`；新建托管隔离工作树 `/home/dev/.codex/worktrees/phase0-integration-20261108/lecturelens` |
| 代码候选 | `170e8ee5fc36d4a474461d335922fbe461aa8200` |
| Agent 身份 | `phase0-integration-9d6312fd722f6df3`，独立 63 模块清单；P10/P9/P7/P3/AU 的冻结身份和原始证据未改写 |
| Tutor v19 | 原工作树仍为 `2ecf4d52af1084bad405e98a6e78027bf4c5ab5d`，未纳入；无远端分支包含该提交 |
| PR #52 | OPEN/DRAFT，`53387bde0ab30a91f56d9ffa0bbaf3648812dd89`；性能框架及租赁压测保持独立，未运行 |

交付 HEAD 与干净状态记录于本地 `.data/phase0/final-receipt.json`（报告提交后生成，避免提交 hash 自引用）。远端 CI 对本候选为 **PENDING**，不继承 main 或 PR #53 的检查结果。

## 整合决策

逐文件选择，没有 merge/cherry-pick 整条历史。58 个来源提交的决定与实际代码路径见 [PR53_SELECTION.json](PR53_SELECTION.json)。

- 选择 `b82bebf` 的新开发检查监督器、进程回收测试、执行指南和 CI 步骤：取消、超时、孙进程及不可回收异常均保留终态和退出码，不接管既有进程。
- 选择 `37605e62` 的路由诊断修复及测试：冻结路由选择前模型名为 unknown/null，避免空字符串使真实 QA/章节调用在记录 STARTED 时失败。
- 选择 `b35be798` 的官方 DeepSeek 工具调用兼容修复及测试：只对精确官方 HTTPS 地址与两个已知模型关闭 thinking；不改变模型路由、超时、token/工具预算或默认开关。单元测试使用 MockTransport。
- 新增独立 Phase 0 源码身份及只读历史源码夹具；历史 P10/P9/P7/更早候选仍可正向验证，当前源码和篡改样本不能冒充它们。不是重新标记历史评测结果。
- 修复完整 Java 回归发现的取消竞态：FutureTask 先登记再提交；重复 taskId 不覆盖活动取消句柄，拒绝入队释放登记。加入无需依赖调度运气的同步执行回归。
- 更新浏览器 HTTP 夹具和稳定定位，适配 main 已有的 QA 历史、练习进度、折叠导航/来源/Trace/刷新操作；保留来源版本、越界晚到响应、草稿、定位和权限断言。

main 已经以 `7930da4`/`bd14213` 及后续提交整合有界重试、持久指标、审批恢复与模型管理；继续保留 main 的 scoped gateway、权限和传输收敛版本。PR #53 的旧分支树还缺少 main 后续的 QA 历史、学习范围、闪卡、Tutor 协议、判分和错题回顾，不能直接覆盖 main。

媒体切分、翻译调度/检查点/价格账本、ASR 缓存、学习资料 map/reduce 及 V26–V32 流水线迁移留在 PR #53，避免把耦合的新准备流程纳入基线稳定。反馈默认开启、旧网关 rollout 参数规避、部署/TLS/Windows 环境证据及运维脚本也未纳入；main 的引用定位保护已有更完整实现。Tutor v19 未通过真实模型质量验收，保持独立实验身份。

## 前端依赖处置

[PR #53 失败 CI](https://github.com/a27497/lecturelens/actions/runs/42463592368) 确认为 9 项（3 High、6 Moderate），Agent/Backend 成功，Frontend audit 失败，build/E2E 未运行。

main 已保留较新的 Vite `8.1.6`、Vitest `4.1.12`、happy-dom `21.0.4`；本轮不回退它们。main 现场完整 audit 仍为 5 项（1 High、4 Moderate）。

| 依赖链 | 处置与影响 |
| --- | --- |
| Axios → follow-redirects | 锁文件 `1.16.1 → 1.16.2`，消除凭据随重定向泄露的已知问题；属于生产依赖链，未更改 Axios 直接版本 |
| @vue/test-utils → js-beautify → glob | 有范围 override 至 `14.0.4`；仅测试工具链 |
| js-beautify → editorconfig → minimatch | 有范围 override 至 `11.0.5`；仅测试工具链，glob 自身也解析到修复版本 |

来源：[follow-redirects advisory](https://github.com/advisories/GHSA-mrwp-f3q8-3g9p)、[glob advisory](https://github.com/advisories/GHSA-3g3m-2fjr-6pw4)、[minimatch advisory](https://github.com/advisories/GHSA-g3hv-75wg-m249)。保留直接依赖，重新生成锁文件，干净 `npm ci`、`npm ls --all`、完整 audit 和 `--omit=dev` audit 均为退出码 0、已知漏洞 0。没有关闭审计或降低阈值。跨主版本 override 额外通过 js-beautify CLI 通配符展开、EditorConfig 规则和 HTML 格式化实测；上游兼容范围包含修复版本后应重新评估是否移除 override。

## 实际验证

运行日志与监督器终态位于 `.data/dev-checks/<name>/{run.json,output.log}`；汇总含日志 hash 的 [CHECKS.json](CHECKS.json)。测试凭据、公开权重及原始本地记录未进入 Git。

| 检查/记录名 | 实际结果 | 退出码 |
| --- | --- | --- |
| `phase0-npm-ci-v2` | 干净安装、锁文件一致 | 0 |
| `phase0-frontend-v2` | Vue 336 项；TypeScript、Vite build、完整/生产 audit、npm ls 全部通过 | 0 |
| `phase0-audit-final` | `npm audit --json`：High/Moderate/总数均 0 | 0 |
| `phase0-dependency-compat-v2` | 跨主版本传递依赖真实 CLI 兼容性检查通过 | 0 |
| `phase0-python-clean-baseline` | Python 3.12.14；`ruff check src tests`、`ruff format --check src tests`、`pytest -q -ra --durations=15`：1234 passed，0 skipped；pytest 734.53 秒 | 0 |
| `phase0-agent-build` | `uv build --offline`：sdist/wheel；新旧身份及 provider 原字节入包 | 0 |
| `phase0-backend-final` | Java 21 编译与 `mvnw -B test`：1702 项、0 skipped，独立 MySQL 8.4 | 0 |
| `phase0-backend-scope-it-isolated` | `-Dtest=LearningScopeMySqlIT test`：权属/版本/删除及迁移通过，1 项 | 0 |
| `phase0-executor-final` | 最终取消竞态测试及中断隔离：14 项 | 0 |
| `phase0-backend-package` | `-DskipTests package`；已先完成全套测试，897 个打包 class 与当前编译结果逐字节一致 | 0 |
| `phase0-supervisor-tests` | 14 项合成进程/回收回归 | 0 |
| `phase0-ci-harness-unit` / `phase0-hold-factory-tests` | 17 项隔离框架、4 项 Mock hold factory 回归 | 0 / 0 |
| `phase0-browser-default-final` / `phase0-browser-version-final-serial` / `phase0-browser-models-v2` | Chromium 155：10 + 9 + 6 场景；desktop/mobile、真实合成媒体、业务接口夹具 | 0 / 0 / 0 |
| `phase0-legacy-e2e` | 原始 HTTP E2E：上传→MQ→FFmpeg→Mock ASR/翻译/资料→QA 引用→权限/删除；清理通过 | 0 |
| `phase0-offline-embedding-preflight` | 固定公开 ONNX 权重、纯离线 384 维 embedding 自检 | 0 |
| `phase0-learning-e2e-verified` | 实际 Java/MySQL→Python/PG/pgvector/本地 embedding；Tutor 完成/两类取消/强杀恢复、闪卡；两版作答与反馈/核对、幂等保存、私有键判分/错题回顾、强杀后历史相同、11 个越权请求精确 404、0 真实模型调用；清理通过 | 0 |

复现扩展的 Mock 学习流程（需同一固定版本的完整公开离线缓存元数据，按原 [框架说明](../../scripts/ci/mock-study-tutor-e2e.md) 准备；新输出目录）：

```bash
python3 scripts/dev/run_check.py --name NEW_UNIQUE_NAME --timeout 900 -- \
  python3 eval/phase0-integration-20261108/learning_smoke.py \
  --output-dir .data/phase0/NEW_OUTPUT_DIRECTORY \
  --embedding-cache-source /absolute/path/to/prepared/public-cache
```

该脚本复用原有安全框架，只在本轮新建 Mock 栈内显式设置 `STUDY_FEEDBACK_ENABLED=true` 以验收已有反馈协议；默认配置未修改。源码/构建指纹见 `.data/phase0/code-identity.json`、`jar-class-consistency.json`、`agent-wheel-check.json`。原始 E2E 的 `Vue/Playwright FOLLOW_UP` 字段保留，浏览器结果由上表独立记录补充。


机制/协议与质量严格分开：没有真实模型任务质量、新鲜 holdout、Tutor v19 验收、长期记忆/自动评分泛化结论。本轮选择题仍为 main 的 Mock 课程原文识别与私有键程序判分，开放题没有新增自动判分。

## 保留的失败与资源处理

- main 初始 audit 退出 1；常规 `audit fix --package-lock-only` 只消除 High 后仍退出 1。随后用有范围 override 完成修复，失败记录保留。
- Python 首轮检测到新 provider 与 P10 身份不符；登记独立身份并新增历史夹具后，历史正例/篡改/冒充回归通过。一次未传数据库的定向检查产生 12 个 skip，不计为验收；补传真实隔离 PG 后 12 项通过。
- Java 首轮 1700 项有 1 项取消竞态失败，修复后全套通过。额外 scope IT 首次被专用数据库名门禁拒绝，改用同一新容器中新建的 `lecturelens_pr2_test` 后通过，没有放宽门禁。
- 浏览器首轮保留旧夹具/旧折叠操作定位失败和错误模式调用；修复脚本后重新完成原功能、模型与版本保护场景。一次手工依赖探针对 inline HTML 换行的假设不成立，改用本应换行的 block 元素后验证实际兼容性。
- Python 600 秒上限退出 124；后续并行准备时本地 85%/2 GiB 磁盘门禁退出 88。监督器未隐藏失败。Tutor E2E 被磁盘门禁 TERM 中止时，原 harness 的信号诊断统一写作 720 秒超时；以外层 `run.json` 的 DISK_GATE/实际耗时为准。其首次清理没有完成，随后按容器标签、工作目录及本轮 preflight 归属核验，清理了 8 个新容器及其新建合成数据卷，记录于 `.data/phase0/owned-cleanup-before.json` 和 `failed-*-cleanup.log`。
- 替换单元 PG 时，就绪/执行准备脚本未实际创建 acceptance 库，定向诊断发现 `database does not exist`；没有修改产品代码或跳过 fixture。随后经真实 TCP 连接确认两个空业务库和 vector 0.8.6，再完整重跑并通过 1234 项。中断数据库保留为另名，未删除。
- 只对本轮生成的公开权重和 MQ 探测依赖副本做字节一致的硬链接去重。两份已停止的临时测试库完整 tar 归档、核验 SHA 后释放对应临时卷占用，数据保留于 `.data/phase0/db-archives/`；原有工作树、冻结文件、日志和数据库未作为释放空间的对象，监督器门禁保持开启。
- 首次精简离线缓存漏带 Hugging Face 文件树元数据，Agent 启动按离线保护失败；保留该轮目录并补齐同版本公共 metadata，纯离线 ONNX 预检通过。附加学习检查首次使用旧环境变量名使反馈仍为默认关闭；保留 FAIL，修正测试脚本为现有 `STUDY_FEEDBACK_ENABLED` 并增加有界协议观察后重跑通过。没有将任何失败轮重写成成功。

## 未运行项与边界

- 本候选 GitHub CI：**PENDING**，本轮禁止 Push。本机完整 Python 检查用时约 12 分钟，超过本地首轮 600 秒；最终采用 2400 秒监督上限。CI 原有 10 分钟 job 上限未更改，远端硬件/时限表现尚未验证。
- CI 中 MinIO 的 Go 官方源码无缓存重编译未在本机重复：本轮未修改镜像/构建文件；本地 E2E 使用 compose 中原有、摘要固定的同版本官方 MinIO/mc 发行镜像。远端 source-build/bootstrap 仍需实际 CI 确认。
- Python/Java 的依赖版本及 Python 锁文件未修改；未额外运行仓库未配置的 SCA 扫描器。前端完整安全审计已运行。
- 未运行真实 Provider、真实 AI Tutor 质量、正式性能矩阵/租赁压测、生产部署、服务重启或生产数据迁移。

最终复核：原有 **44 个工作树** HEAD/状态不变；原树与 v19 的 **1921 个冻结/eval/fixture 文件**字节 hash 不变；**23 个既有运行容器**身份/启动时间/重启计数不变且无 OOM 标记；4 个 live systemd 单元状态及 PID 不变，其启动均早于本轮；原 **43 个监听地址**完整保留。没有对原数据库执行写入。两套 E2E 项目的容器/卷/网络已清理；本轮单元 PG 已停止并保留数据卷。原始证明见 `.data/phase0/preservation-final.json`、`frozen-before.json`、`worktrees-before.json`、`live-systemd-state.json` 及各清理日志。


**PHASE0_STATUS = PASS（本地集成验收）**；**GitHub CI = PENDING**。

具备进入 Phase 1 真实 AI Tutor 验收准备的代码与机制基线。真实模型教学质量、独立新鲜 holdout 和远端 CI 仍需各自验收；本轮没有启动 Phase 1。
