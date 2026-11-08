**PHASE1_A_STATUS = READY**，仅表示独立 v19 三回合诊断 Smoke 的零成本工程准备完成；真实调用仍未授权，真实教学质量 NOT_RUN，独立语义裁定 UNRESOLVED。没有进入 Phase 1-B。

准备分支 `codex/phase1a-tutor-readiness-20261108`，工作树 `/home/dev/.codex/worktrees/phase1a-tutor-readiness-20261108/lecturelens`。Phase 0 基线 `17d78636cf97fcf55fe642b1ecc30c5e2ea48865`；重新核实的远端 main 仍为 `300be51515867f7ece4f3a9224a484e825219ee0`，Phase 0 分支未发布，**GitHub CI = PENDING**。本轮实现提交 `debe6e4df2f8801125839b988507919232d57863`；最终交付提交是包含本报告的提交，可用 `git log -1 --format=%H -- eval/phase1a-tutor-readiness-20261108/REPORT.md` 解析（最终 SHA 另记于本地 receipt 和交付消息，避免报告自引用 hash）。

真实 Provider／付费评审／付费 embedding 请求 **0 / 0 / 0**，原 native live CLI 调用 **0**。本轮这些请求费用 US$0；未访问供应商账户，未声称查询到其实际扣款。仅访问公开官方文档、固定公开课程和 npm 审计 registry。未读取、查找、输出或配置任何密钥值；调用环境中所需变量的存在性检查为 absent，不能据此推断主机其他凭据配置状态。

**身份和兼容边界。** 原 Phase 0、原锁定 v19 工作树保持原样。新建独立锁定执行 checkout `/home/dev/.codex/worktrees/phase1a-v19-runner-20261108`，HEAD `2ecf4d52af1084bad405e98a6e78027bf4c5ab5d`；没有把 v19 历史合入 Phase 0。候选 `p8-tutor-selected-v19-development`，实际冻结代码 `ae222cc76ec41aed78072713a9371eaff6000b2e`，manifest SHA256 `16a094317ba06b3c1932280c7dbb15a07d47200dc74ed8e08e25465e10549ae9`，原三回合包 SHA256 `ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e`。全部 18 个候选、22 个父清单绑定及完整源码围栏通过原 verifier。

两条线共同祖先为 main `300be515`，源码范围实际有 65 个不同路径，详见 `COMPATIBILITY.json`。v19 需要 Java `complete-v1` 原文证据接口；Phase 0 仍为旧证据投影，不能直接连接。新增离线反例确认 v19 对旧投影 fail closed。v19 自身 Java gateway→HTTP→ASGI→PG 回归通过，但身份事实／检索／模型为 Mock，不是生产 JWT 或业务数据库验收。实验工厂仍 Mock-only。没有改变 Phase 0 默认、业务代码、部署配置或产品前端；没有声称两条线已整合成真实浏览器链路。

**本轮修改。** 仅新增本目录下的准备工具、测试、规则和证据：

- `prepare.py` 只读核实冻结身份、Phase 0 接口边界、预算公式及变量存在性，永不请求模型。
- `launch.py` 默认验证；未来明确 handoff 前核对两套 clean HEAD、唯一执行路径、新批准／价格回执、账户费用风险和独立评审声明，再交接给未修改的 frozen CLI。缺少运行时变量在 claim／预算预留前拒绝；原生 exec 继承用户提供的运行环境，启动器不读取／复制密钥内容。通用开发 supervisor 会剥离供应商变量，不能充当真实注入渠道。本轮只执行拒绝测试，未发生成功 handoff。
- `QUALITY_RULES.md`、`review-template.json`、`quality_gate.py` 将独立语义评审与机械成功分开；12 个原必要点逐字保留。真实来源不自动支持解释，A03 未关闭；未裁定项保持 UNRESOLVED。汇总程序不是自动语义评审，也不能证明人的独立性。
- `SMOKE_RUNBOOK.md` 给出原 3+1／12 请求／US$0.30 本地上限方案、停止／留证、凭据安全配置及未来命令；未创建真实 grant 或 dispatch receipt。未改 Tutor 协议、题目、原始参考及判分规则。

**费用核实和边界。** 公开官方材料于 2026-11-08 UTC 重新读取并保存响应 hash，见 `PUBLIC_PRICING_REVIEW.json` 和 `EVIDENCE_MANIFEST.json`。Flash 目前公布峰值输入未命中／输出价格 US$0.30／1.20 每百万 token，与冻结账本保守费率一致；公布后端为 DeepSeek-V4.1-Flash-1017，API ID 是移动别名。配置为 thinking disabled、required tools、4096 output tokens；文档未保证 parallel_tool_calls=false 的执行效果。[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)；[Chat API](https://api-docs.deepseek.com/api/create-chat-completion/)。

最大本地预留 US$0.294912，小于 US$0.30；测试证明第 13 次、预留不足、未知未结算、账本镜像不一致会在下一次发送前停止。新增反例同时证明供应商返回异常超额 usage 时，本地结算金额可能超过上限，之后请求被封锁，已有费用无法撤销。wire 字节代理不是供应商 token 化的硬证明，账户／余额／硬限未验证。因此不把 US$0.30 说成账单硬封顶；额外保守上下文敏感性估算、假设及明确不扩大授权均记录在 runbook。一次性 claim 是本路径内的 O_EXCL／fsync 操作门禁，不是跨任意副本的密码学授权。未来批准必须明确接受这些限制或先由用户验证账户级硬限。

**实际检查。** 全部 supervisor 终态、退出码、时间、日志 hash 见 `CHECKS.json`；没有把负例或未运行项写成绿色。

| 检查 | 新结果／退出码 |
| --- | --- |
| 最终 Python：原 v19 协议、完整教学 HTTP、共享纠错、预算／授权／跨版本证据、外层启动、独立评审汇总门禁 | **77 passed，0 skipped，2 deselected；0**。2 项历史原始响应回放因资产缺失明确未运行。 |
| v18 兼容子集 | **27 passed，0 skipped，11 deselected；0**。旧 frozen-entry／旧 grant 项未运行，不称全量通过。 |
| Java v19 真实 HTTP／ASGI／独立 PG 加 gateway／Evidence／controller／transport | **24 passed，0 skipped；0**；同时完成 Maven compile/testCompile。 |
| 原 frozen verifier、新 preflight、默认 launch | **0**；冻结源和模板未改，均无付费路径。 |
| Ruff、格式、Python compileall | **各 0**；7 个新增 Python 文件。compileall 不代表静态类型检查。 |
| 缺少运行时密钥的真实进程门禁负例 | **2（预期拒绝）**，未创建原 live claim、输出目录或预留。 |
| 以 Mock outcomes 和未完成评审表运行质量汇总 | **2（预期 UNRESOLVED）**；机械完成不能自行得到质量 PASS。 |
| Phase 0 当前前端 lock 审计 | **0 项漏洞；0**。 |
| 冻结 v19 当前前端 lock 审计 | **5 项（1 High、4 Moderate）；1**：follow-redirects、glob／minimatch／editorconfig／js-beautify 链。保留失败日志，不修改冻结 lock。未来此方案仅运行不加载 Node 的诊断 CLI；v19 前端不能被当作已经安全整合的产品候选。 |

检查入口可复现：从准备工作树运行其 `scripts/dev/run_check.py`，指定 `--cwd` 为上述独立 v19 checkout，用该 checkout 的 `.venv/bin/python eval/tutor-scale/safe_exec.py NEW_NETWORK_DIR /ABS/.../offline_checks.py --output .data/phase1a/NEW_OUTPUT`；Java 原命令和选定测试见原 closeout 报告，改为新 checkout、独立 PG 和新标签。离线 Python 使用原 socket fence、Mock HTTP、测试内禁止密钥读取／真实 HTTPTransport；SQL 仅指向本任务独立 loopback PG。Python audit 不是 OS 抓包，不能覆盖 libpq C socket；不夸大网络监测保证。依赖按未修改锁文件离线安装，Maven offline，npm 使用显式空配置文件和公开 registry。

初次新 preflight 因 `Path.open(opener=...)` 用法错误退出 1，已修复为标准 `open` 并重新验证，原日志保留。初次依赖安装误用不存在的 `--extra dev` 退出 2，随后标准 frozen offline sync 退出 0；不涉及候选／锁修改。早期 58、70 项通过及单独 11 项门禁检查均保留，不叠加计为最终用例数量。

**未运行和遗留风险。** 没有真实 v19 教学质量结论；v18 原记录仍是 0 completed／1 failed／2 skipped、3 次真实请求的历史 FAIL，旧授权已结束。v19 原预检停止记录仍保留。旧 v18 raw bodies 当前缺失，没有伪造。未运行真实认证／账户／账单 API、真实模型／embedding／付费 reviewer、独立人工评审、full16、SQL holdout、性能／正式压测、部署、完整学习闭环或本轮浏览器验收。本轮没有产品 UI 改动；Phase 0 历史 Python 1234／Java 1702／Vue 336／浏览器结果不冒充本轮执行，也不冒充 GitHub CI。A03、别名变动、语义不能在每个机械回合之间自动停止、独立评审待安排和 v19 前端漏洞均保持可见。

**保护与收尾。** 最终对比 46 个其他／执行工作树的 HEAD 和 Git 状态均一致；原 Phase 0／v19 共 1201 个已跟踪 eval 文件实际 hash 无变化。原 23 个运行容器仍为同 ID／镜像，4 个 live unit 的 PID／启动时间／状态不变。只连接本轮新建验收 PG；测试 schema 最终剩余 0，容器 `lecturelens-phase1a-pg-20261108` 已停止、卷保留。没有读取／修改在线 DB 内容；正常在线业务仍可能自行写入，不声称运行数据库字节冻结。无 push、PR、main 合并、部署、原服务重启、资源租赁或数据删除。

证据位于准备树 `.data/dev-checks/phase1a-*`、`.data/phase1a/` 及独立执行树 `.data/phase1a/`、`.data/tutor-selection-v19/phase1a-cross-service/`。`CHECKS.json`、`COMPATIBILITY.json`、`EVIDENCE_MANIFEST.json` 提供可提交索引与 hash；私有原始输出不入 Git。PG 卷身份、原工作树／冻结材料／服务最终比较及官方公开响应在私有证据中保留。

下一次需要用户额外批准：**这一条隔离路径上的唯一一次原三回合、最多 12 请求试验**，绑定最终两套 SHA／manifest／packet、run ID 与有效期、无重试／扩展及费用风险；由用户安全注入运行时凭据、确认供应商账户计费／硬限、约定独立评审者，并明确解决或接受 Phase 0 远端 CI PENDING 的诊断边界。执行前须刷新价格回执并获准启用新的独立测试 PG。满足前不得发请求；三回合成功也不自动授权后续阶段。
