当前开发诊断采用确定性检查、外部 AI 交叉评审、HUMAN_NOT_RUN 三层。没有真人评审者不会阻塞诊断准入；没有完成 AI 交叉评审会阻止 AI_REVIEW_PASS。此流程只替代 Phase 1-A 的外层真人评审要求，不改变任何冻结 v19 文件、题目、参考、协议、预算或历史结果。

准备代码分支基于 `de6b156567bc7a47f6aec6a2161f3b36a5537c5a`。原 Phase 1-A 目录和测试按历史身份保留；本分支新增 `admission.py` 是当前入口，不能继续用旧 `launch.py` 的真人及风险布尔字段作为本轮准入依据。

固定执行身份仍是 `/home/dev/.codex/worktrees/phase1a-v19-runner-20261108`、clean HEAD `2ecf4d52af1084bad405e98a6e78027bf4c5ab5d`，候选代码 `ae222cc76ec41aed78072713a9371eaff6000b2e`、manifest `16a094317ba06b3c1932280c7dbb15a07d47200dc74ed8e08e25465e10549ae9`、三回合包 `ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e`。另一个已附加 v19 checkout 仅保护、不用作替代执行身份。保留 Phase 0 CI PENDING、v19 原文接口与 Phase 0 gateway 不直接兼容及独立诊断非产品验收的边界。

`admission.py` 默认只读 preflight，返回 2 和当前未满足的准入条件，不发送请求。仅未来明确的 `--mode handoff-live` 才可能交接原 frozen CLI，顺序为：冻结身份→完整分层评审计划→新非秘密批准与费用保障→运行时凭据存在→两套 clean HEAD／路径／短有效期绑定→原 live_admission（精确模型、预算、价格、scope、开关等）→独立 durable PG 只读检查→原生 exec。仍由 frozen CLI 独占创建单次 claim、持久化预算预留、发送与停止；没有重新实现 Tutor 或放宽 3+1 修正额度。

本轮用户已条件同意一次原三回合生成，最多 12 请求、并发 1、HTTP retries 0、4096 output tokens／请求、本地费用上限 US$0.30；**没有同意潜在超过 US$0.30 的供应商账单**。所有真实流程必须保持该边界。当前没有可核验的供应商账户硬限，因此本轮在 native live CLI／claim／预留／真实发送之前结束。不能把本地最坏预留 US$0.294912 说成供应商保证，也不能自动填 risk_accepted=true。

公开资料只说明价格、余额和并发，并不证明这次运行的账户硬限。[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)峰值 Flash 输入未命中／输出仍为 US$0.30／1.20 每百万 token；[余额接口文档](https://api-docs.deepseek.com/api/get-user-balance/)的 availability／余额不是 hard cap；[限流文档](https://api-docs.deepseek.com/quick_start/rate_limit/)讲并发，不能限制美元责任。未调用任何账户、余额或模型 API。

未来若有真实账户硬限证明，外层可验证非秘密 receipt 的 scope、run ID、执行路径、USD 最大新增责任 ≤300000000 nano-USD、在途／延迟计费及共享活动覆盖、自动充值／信用关闭、1 小时内核验时间，以及脱敏证据文件 hash。模板全部为未验证状态，不能直接执行。程序校验的是记录结构与一致性，**不能自行证明供应商实际执行了硬限**；必须先有人依据供应商账户证据核验事实。不要求 Python 教学专家参与这个账户事实核查。余额、告警、低充值额和旧风险布尔字段均不能替代这些条件。本轮没有这类证明，也没有可用的 DeepSeek 账户连接工具，不搜查凭据或其他私有配置来猜测。

若用户以后明确改变超额风险授权，须按新批准复核门禁和执行方案；当前代码有意没有仅设置 true 就能绕过费用保障的分支。本轮条件授权不保留为后台任务或自动重试，下一次决策需新短期 run ID／回执。`preparation_git_head` 绑定本分支最终提交，`review_plan_sha256` 绑定本目录 review-plan，`cost_assurance_sha256` 绑定真实非秘密账户证明；原 frozen grant 的全部字段继续由原入口检查，外层期限另限制为最多 15 分钟。

运行时 `AGENT_LLM_API_KEY` 只由用户在受控本地终端或凭据管理器注入实际 Python 进程，不在聊天中提供、不放进 argv／仓库／回执，也不修改部署配置。外层只查存在性，不读值；这不证明值非空或有效。真实交接使用原生 exec 继承环境，最终 frozen provider 才能在获准请求中使用凭据。当前开发 supervisor 和 frozen safe_exec 剥离供应商变量，继续仅用于零成本检查。

质量流程按原 5／3／4 个必要点和所有实质性主张判定。固定参考执行核实初值 2、Ada／Grace、轨迹 2→3→4、内打印 3／4、外打印一次 4，以及索引；不执行模型生成代码。获得真实结果后 `review.py --execution /ABS/NEW_REAL_OUTPUT` 收集完整原始实体、outcomes、calls、账本、runtime 及 frozen 源码身份，检查协议参数、调用／状态／预算、原始请求 hash、规范来源绑定、长度、可解析 Python 代码。引用存在性和语法不证明解释或代码语义；PG 镜像一致性是 frozen 运行器报告，导出器不重新连接生产或验收数据库验证。

`review.py --export /ABS/NEW_PACKET --candidate-root /ABS/V19` 可以在无真实输出时先生成完整待审包：固定课程原文、仅开发课程的完整 evidence、原题／原参考、可信计算、三位置状态、逐点响应模板和审阅提示。没有真实执行目录时全为 SKIPPED／NOT_RUN，不伪造教学答案；Mock 目录被明确拒绝作为真实教学证据。`--execution` 仅接受绑定候选的 live 输出，原始文件另存 execution/，评审的 outcomes JSON 重新编码不截断字段，二者 hash 分别保存。不带入其他课程或 holdout。

可将整个包手动交给 ChatGPT 等外部 AI 的独立新上下文。读取 `REVIEW_PROMPT.md` 后逐项审查必要解释、正确性、代码与条件、每个 claim→source 的语义支持、连续追问和苏格拉底式引导。不得让同一实现会话自评冒充交叉评审。每个已裁定点需理由和可定位回答／来源片段；程序检查逐字存在、原包／outcomes／bundle hash、全部必要点、完整主张声明和置信度，不假装自动判断语义。任何未知、低置信度、遗漏或未安排的 AI 评审保留 UNRESOLVED。A03 真实引文支持错误解释必须 FAIL，不能因绑定正确而通过。

外部 AI provenance 是可审计披露声明，不是密码学独立性证明，也不能消除模型相关错误。只有机械 PASS 且全部原必要点与所有主张经独立上下文 AI 高置信度通过才汇总 AI_REVIEW_PASS；HUMAN_NOT_RUN、expert_verified=false 始终单独输出。无真实回答则 QUALITY=NOT_RUN。工程失败与语义错误分开；任一语义 FAIL 保留失败，未观察位置不补跑。即使 AI_REVIEW_PASS 也不授权 full16、Phase 2、发布或正式 Tutor。

复现零成本验证：使用准备树 `scripts/dev/run_check.py`，`--cwd` 指向固定 v19 runner，其 Python 执行原 `eval/tutor-scale/safe_exec.py NEW_NETWORK_DIR /ABS/NEW_WORKFLOW/checks.py --output .data/phase1b/NEW_OUTPUT`。检查全部是外层 unit／Mock，不需数据库。原 frozen 预算／一次性 claim／回执用例复用明确 node IDs；本轮未运行的数据库、Java、Vue、浏览器或真实模型测试不继承历史成功。

质量汇总使用 `review.py --bundle /ABS/PACKET --response /ABS/EXTERNAL_AI_JSON`。0 仅表示 AI_REVIEW_PASS；2 表示 NOT_RUN／UNRESOLVED／FAIL。格式或绑定错误拒绝处理，原证据保留。没有自动调用任何外部评审模型的代码。
