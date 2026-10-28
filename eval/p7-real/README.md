# P7 闪卡真实评测通道（未执行真实评测）

本目录提供独立、未部署的付费评测入口。当前只完成离线机制验证，Provider 真实请求为 **0**；Mock PASS 不代表模型质量。AU/P6、原 CostPolicy 的 fake 限制及原冻结 manifest 均保持原字节。

`lecturelens_real_eval` 刻意位于冻结 `lecturelens_agent` 包外。`EvalChatProvider(ChatProvider).flashcards()` 实现严格工具协议；`GraphAdapter` 仅在本入口将该实现接入原闪卡图，保留原图/Store 的 `mock` 兼容标签。产物以独立策略的 `live/mock` 标记区分，不使用该兼容标签证明调用真实性。产品工厂不加载适配器，默认仍 Mock only。实际调用必须同时具有 CLI `--live` 和 `LECTURELENS_REAL_EVAL=1`；缺 CLI 始终是假传输，显式 `--live` 缺环境开关则拒绝。

学习目标由模型先选择 `search_card_evidence`，观察本讲检索结果后选择继续搜索、`create_evidence_cards` 或 `stop_cards`。生成最多 3 次请求；每个完成的任务再做 1 次独立来源复核，包括空卡停止任务。复核只能看到卡片正反面和其引用原文，看不到目标、历史或负例标签。保存卡片、逐次工具提案、引用、usage、时延和错误；失败不重标、不付费修复、不重试。引用不存在或不属于该讲立即停止整轮；所有通道/账本错误为 FAIL。普通 schema 失败结束当前生成并计协议失败。

## 冻结数据与边界

从已有 [retrieval-v2/corpus.json](../retrieval-v2/corpus.json) 选取 8 讲：

| 课程 | 快照讲 ID | 来源 |
| --- | --- | --- |
| MIT 6.006 Fall 2011 | algorithms-l1/l2/l3 | BFS、DFS、Dijkstra 讲义 |
| MIT 6.041 Fall 2010 | probability-l1/l2/l3 | 概率模型、条件概率、独立性讲义 |
| MIT 8.04 Spring 2016 | quantum-l1/l2 | Quantum features、Experiments with photons 讲义 |

许可证为 CC BY-NC-SA 4.0；原始 URL、作者归属、原始 PDF SHA-256、页面和文本 hash 保留在 [snapshot.json](snapshot.json)。完整来源快照 SHA-256：`ae78ef07ce91fcc6dbf15959857e55dbdf032675dbee5fe847d302f11e15f09b`。仅选原始英语可检索段落，未使用合成翻译。原快照没有可用媒体时间，传给冻结图的 `start_ms/end_ms` 是 `page*1000/(page+1)*1000` 的兼容页码槽，**不是真实时间戳**；原定位字段保留，人工抽查导出页码和原文。

[24 个目标](tasks.json) 每讲各有定义、条件、易混点一个；algorithms-l3 和 quantum-l2 的易混点替换为本讲不包含的中子星状态方程问题，共 2 个负例。搜索只在本讲文本内作确定性词项排序，不读取 expected_stop；Mock 对负例的固定反应仅用于机制验证。

AU strings/linear holdout 目标未复用。仓库未识别到可用于逐项排除的 P6 目标数据；本次明确属于公开已见课程的新闪卡目标，**不宣称独立新 holdout 或未见课程泛化**。[frozen.json](frozen.json) 冻结任务、证据、判定线、入口/通道代码及候选 SHA-256，运行前同时检查原 P7 manifest；不更改任何旧 manifest。冻结后改动必须形成新候选，失败记录保留。

[thresholds.json](thresholds.json) 固定：引用有效率 1.0，来源 supported 比例 ≥0.90（unclear 失败），负例正确停止率 1.0，生成协议失败率 ≤0.05，最近秩 p95 生成时延 ≤20 秒，≤120 请求、≤US$1。全部达标 PASS；非引用伪造的质量/协议未达标 PARTIAL；引用伪造或通道/账本故障 FAIL。未完成 24 任务不能 PASS。支持率分母是保存的全部卡片，缺失/失败复核贡献 0 个 supported；失败工具提案另行保留，不转换为有效卡片。

## 隔离 PG 与离线验证

只操作项目 `lecturelens-p7-real-eval-20261027` 的 PostgreSQL，监听 `127.0.0.1:25711`。首次创建：

```bash
cd /home/dev/projects/lecturelens-p7-real-eval
COMPOSE_DISABLE_ENV_FILE=1 docker compose -p lecturelens-p7-real-eval-20261027 -f eval/p7-real/compose.yaml up -d
COMPOSE_DISABLE_ENV_FILE=1 docker compose -p lecturelens-p7-real-eval-20261027 -f eval/p7-real/compose.yaml exec -T postgres \
  psql -U p7 -d lecturelens_agent_acceptance -c 'CREATE DATABASE lecturelens_agent_test'
```

已有数据库无需再 CREATE。新账本仅含 `p7_real_run/p7_real_event`；图使用隔离库内已有 StudyStore/checkpoint 表，不修改业务库或 Java。测试连接 `lecturelens_agent_test`；新账本测试另在 `lecturelens_agent_acceptance` 建独立 schema 并清理。

```bash
AGENT_TEST_DATABASE_URL='postgresql://p7:p7-local-only@127.0.0.1:25711/lecturelens_agent_test' \
uv run --project agent-service --offline python scripts/eval/check-study-offline.py \
  --database-port 25711 --network-records .data/p7-real/checks/network-review \
  -- -q --junitxml=../.data/p7-real/checks/review.xml
```

默认 Mock 运行使用本 worktree 的账本路径，**不要**使用真实默认账本：

```bash
uv run --project agent-service --offline python eval/p7-real/run.py \
  --dsn 'postgresql://p7:p7-local-only@127.0.0.1:25711/lecturelens_agent_acceptance' \
  --ledger .data/p7-real/mock-ledger.jsonl --run-id p7-mock-review
```

输出在 `.data/p7-real/<run_id>/`：`generations.jsonl`、`reviews.jsonl`、`summary.json`、`sample.md`。`sample.py <目录>` 用种子 20261027 从全部生成卡片均匀随机抽 10 张（不足则全取）。Mock 默认 72 次假请求、22 张卡；summary 明确 `NOT_RUN_MOCK_MECHANICS_ONLY`。检查日志在 `.data/p7-real/checks/`，不提交运行数据和凭据。

## 给审查人的唯一真实运行命令（本任务没有执行）

审查人先启动上述隔离 PG，再手动执行以下完整命令。`eval.env` 由审查人准备，只配置 `LECTURELENS_REAL_EVAL=1`；`secrets.env` 只需注入 `AGENT_LLM_API_KEY`。程序只从进程环境读取 Key，不读取文件。下面的 source 操作也仅由审查人执行，不应记录 shell trace：

```bash
cd /home/dev/projects/lecturelens-p7-real-eval
(
  set +x
  set -a
  . /home/dev/lecturelens-eval/deepseek-20261027/eval.env
  . /home/dev/lecturelens-eval/deepseek-20261027/secrets.env
  set +a
  uv run --project agent-service --offline python eval/p7-real/run.py \
    --live \
    --dsn 'postgresql://p7:p7-local-only@127.0.0.1:25711/lecturelens_agent_acceptance' \
    --ledger /home/dev/lecturelens-eval/deepseek-20261027/ledger.jsonl \
    --max-calls 120 --max-usd 1.0 --run-id p7-real-review-20261027
)
```

开跑前打印单请求最坏预留 US$0.0211008、120 请求/US$1 上限、本轮账本当前合计。120 次请求的满体积预留为 US$2.532096，因此预算可能在 120 次前先耗尽；真实输入较小时可完成正常约 72 次/最多 96 次，**不保证预算内一定完成**。

唯一网络路由为 `https://api.deepseek.com/chat/completions`，模型 `deepseek-flash`，thinking disabled，max_tokens ≤1200，请求体 ≤65536 字节。输入以整个实际请求体 UTF-8 字节数作为 token 上界，按输入 US$0.30/百万、输出 US$1.20/百万预留；缓存命中同价。每次 PG 和 JSONL 都持久写入相同 call_id 的 reservation 后才发送。成功按 usage 结算；HTTP/超时/解析/schema 错误按预留全额收取；实际 usage 费用超过预留时按实际入账并封锁整轮。

JSONL 使用 O_APPEND、文件锁和 fsync，PG synchronous_commit/on、fsync/on。两库不能原子提交；崩溃造成单边记录时严格阻止发送，不自动补账或退款。单次 run_id 不得重新启动；悬而未决预留继续计全额且禁止重放。检查当前轮全部逐条事件一致性：在相同 source 环境与参数的命令末尾加 `--check-ledger`，该模式不发送请求、不读取 Key。降低预算后检查仍需传回该轮原参数；不能借更改参数重置账本。

审查后仅停本项目 PG，不删除卷：

```bash
COMPOSE_DISABLE_ENV_FILE=1 docker compose -p lecturelens-p7-real-eval-20261027 -f eval/p7-real/compose.yaml stop postgres
```

真实模型语义支持率、延迟和实际费用仍未测；来源复核是模型意见，固定随机样本供人工核对。本通道未验证长期记忆、自动评分或 FSRS 学习收益。
