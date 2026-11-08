本文件是可执行方案，**不是授权**。Phase 1-A 仅测试缺少凭据／批准时拒绝 handoff-live，不执行成功交接，不创建真实 grant、付费账本或一次性 claim。

执行边界：准备分支以 Phase 0 `17d78636cf97fcf55fe642b1ecc30c5e2ea48865` 为父；独立执行 checkout `/home/dev/.codex/worktrees/phase1a-v19-runner-20261108` 必须保持 clean、HEAD `2ecf4d52af1084bad405e98a6e78027bf4c5ab5d`。实际候选代码 commit `ae222cc76ec41aed78072713a9371eaff6000b2e`，身份 `p8-tutor-selected-v19-development`，manifest SHA256 `16a094317ba06b3c1932280c7dbb15a07d47200dc74ed8e08e25465e10549ae9`，三回合包 SHA256 `ade24dceaf2bf50421b88373b68ebb65ba776c0d83754cab350fc06f558ba60e`。实验工厂仍 Mock-only；付费诊断入口不是正式默认、浏览器真实模型入口或 Phase 0 整体验收。

仅使用原三回合顺序：完整循环教学及变式／注释代码／索引；不泄露答案的缩进引导；基于实际前文纠错。已公开的已知课程开发数据，非 SQL、非 holdout、非学习效果试验。不改题目、来源、参考点或提示参数，不补被跳过的回合。

| 参数 | 冻结限制 |
| --- | --- |
| 模型／接口 | `deepseek-flash`，`https://api.deepseek.com/chat/completions` |
| 配置 | thinking disabled，temperature 0，required tools，parallel_tool_calls false |
| 请求 | 每回合 3 次普通决策＋1 次共享 finish correction，最多 4；全程最多 12，串行 1；HTTP retries 0 |
| 输出／时间 | 4096 output tokens／请求；20 秒／回合；请求 65536／响应 131072 字节；回答 4096／反馈 1024 Unicode code points |
| 其他预算 | turn/session proxy 64000/640000；reviewer、embedding、Search/Fetch API 请求均 0 |
| 费用 | 本地 reserved＋settled ≤300000000 nano-USD（US$0.30）；失败／未知请求不退款 |

截至 `PUBLIC_PRICING_REVIEW.json` 时间，官方公布 Flash 输入未命中／输出峰值 US$0.30／1.20 每百万 token，低峰为 US$0.15／0.60，命中价更低。采用峰值无缓存费率 300／1200 nano-USD/token。模型名是移动别名，公布后端 DeepSeek-V4.1-Flash-1017，不是不可变权重快照。[价格](https://api-docs.deepseek.com/quick_start/pricing/)；[Chat 配置](https://api-docs.deepseek.com/api/create-chat-completion/)。当前文档支持非思考 required-tools 和 4096 tokens，但未证明服务端遵守 parallel_tool_calls=false；现有解析器检查全部返回调用，只执行第一个，记录丢弃项，不因此追加请求。

本地理论最大预留 `12×(65536×300+4096×1200)=294912000` nano-USD = **US$0.294912**。这是以 wire 字节代理输入 token 的本地上界，**不是供应商账单保证**。供应商 token 化及协议开销没有独立硬上界证明；新负例证明异常 usage 可在结算时超过本地上限，随后请求被禁止，但已产生的供应商费用无法撤销。仅作额外敏感性估算：若每个请求都按 1,048,576 输入 token、4096 输出 token 和上述价格计费，12 次为 US$3.833856；此估算不是已批准预算，不允许因此提高限制，也不保证供应商遵守该假设。价格变化、并行使用同一账户、汇率及账户计费均不受本地账本控制。账户级硬限／余额／访问权限本轮均未查询；必须由用户在供应商控制台复核，并决定是否接受仅有本地上限的剩余账单风险。

未来执行前需要一次新的明确批准，绑定：本准备分支最终 clean HEAD、上述 v19 clean HEAD／路径／manifest／packet、唯一 `v19-...` run ID、UTC 有效期、全部限制、三回合范围、本地费用与账户风险、独立评审者。不能复用 2026-11-08 已结束的旧授权。先复核 Phase 0 远端 CI（目前 **PENDING**）；未运行不能称全绿。若决定在 CI 仍 PENDING 时做独立诊断，批准须明确接受该边界，不得称主线集成验收。

复制冻结 `authorization-template.json` 仅到私有新目录；由获批操作者填入新授权，另外添加：`preparation_git_head`（本报告最终提交）、`execution_root`（上述唯一新路径）、`supplier_cost_risk_accepted: true`、`independent_reviewer`（已约定的独立评审者）。这些字段不修改冻结协议，只加在外层启动门禁。价格回执必须在执行前 24 小时内重新核实官方事实并使用原 pricing template 格式；本轮 PUBLIC_PRICING_REVIEW 特意不是 live receipt。模型／价格改变则停，不自行替换参数。

凭据由用户在受控本地终端／凭据管理器中注入**实际执行 Python 进程**的 `AGENT_LLM_API_KEY`，并显式设置 `LECTURELENS_REAL_EVAL=1`。不要发到聊天，不放进 argv、JSON、仓库文件或 shell history；关闭 shell tracing。只检查变量是否存在即可，本轮不读取其值、验证其非空性或有效性。通用 `scripts/dev/run_check.py` 和 frozen `safe_exec.py` 刻意剥离供应商变量，适用于本轮零成本检查，不能当作真实凭据注入渠道。

新 `launch.py` 默认只验证。显式 future handoff 先检查变量存在、两套身份／路径、费用风险与评审声明，再调用**原 frozen live_admission**，最终用原生 `execv` 交接到**未修改的** `run_tutor_smoke_v19.py`。它不读取／复制密钥内容，不自动设置凭据、不生成 grant；缺失变量在 claim 和预留前退出。底层真实 Channel 才会在获批执行中读取运行时密钥。启动器不是供应商账户硬限，也不是防止获权操作者伪造 JSON 或复制 checkout 的密码学授权系统；批准只适用于这一条路径与一次运行。

仅在未来用户明确批准且上述门禁全部满足后，才可执行以下形式（本轮未执行）：

```text
timeout --signal=TERM --kill-after=10s 180s \
  /home/dev/.codex/worktrees/phase1a-v19-runner-20261108/agent-service/.venv/bin/python \
  /home/dev/.codex/worktrees/phase1a-tutor-readiness-20261108/lecturelens/eval/phase1a-tutor-readiness-20261108/launch.py \
  --candidate-root /home/dev/.codex/worktrees/phase1a-v19-runner-20261108 \
  --mode handoff-live --output /home/dev/.codex/worktrees/phase1a-v19-runner-20261108/.data/phase1b-UNIQUE \
  --authorization /ABS/PRIVATE/fresh-grant.json --pricing /ABS/PRIVATE/fresh-price.json
```

需先获准启动新的独立 loopback PostgreSQL（端口 25841、库 lecturelens_agent_acceptance）；本轮测试实例结束后停止，不复用在线数据库。不启动产品服务。整体超时只管理这次新 CLI；超时／中断后保留未知责任，禁止自动再跑。每回合 provider／model／usage／协议／引用绑定／权限／source version／deadline／预算／账本／纠错失败均停止整次调用。独占单次 claim 和 fsynced PG＋JSONL 预留先于发送，镜像不一致或未知请求停止，不能自动修复后重发。

证据保存：新私有目录（0700），原始 decoded request/response entity bodies 与 redaction 元数据（不是 TLS 抓包）、execution/owner/outcomes/runtime/summary、calls.jsonl、ledger.jsonl、候选／代码／grant／价格 hash、实际 usage/cache/model、PG schema 和 `.data/tutor-v19-authorizations/<run_id>.used`。0600 文件；保留失败、跳过、未知位置；真实 schema 不自动删除。原 v18 raw bodies 缺失，不伪造其重放。供应商实际扣款由用户独立对账，未取得账单则 UNKNOWN。

执行退出码：原入口 0 是机械完成，1 是失败／跳过，2 是准入拒绝；不是教学质量 PASS。随后按 `QUALITY_RULES.md` 独立评审，保存原始意见再运行 `quality_gate.py`。三回合全部 PASS 也仅是初步开发证据，不能自动进入 full16、上线或 Phase 1 完整学习闭环开发。
