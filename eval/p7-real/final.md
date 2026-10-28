# P7 真实评测通道交付记录

本地实现与离线验证完成；真实 Provider / DeepSeek 调用 **0 次**，真实费用 **US$0**。没有运行真实评测、发布或部署。真实语义质量仍为 **NOT_RUN**。

## 改动文件

- `agent-service/src/lecturelens_real_eval/{__init__,channel,runner}.py`：独立策略、严格 ChatProvider 闪卡扩展、双持久账本、图适配器、本地只读证据 authority、来源审阅和统计。
- `agent-service/tests/test_p7_real_eval.py`：离线通道、预算、不重试、脱敏、引用、账本、Mock 端到端测试。
- `agent-service/pyproject.toml`：打包独立扩展，不增加依赖。
- `eval/p7-real/{tasks,snapshot,thresholds,frozen}.json`：8 讲、3 门公开课程、24 目标、2 负例及来源/候选 SHA-256 冻结。
- `eval/p7-real/{run,sample}.py`、`compose.yaml`、`README.md` 和本记录：运行入口、固定抽样、独立 PG、审查说明。
- 根 `README.md`、`docs/P7_EVIDENCE_FLASHCARDS.md`：链接独立通道，保留实验和质量边界。

为同时满足原冻结闸门和真实通道需求，新增 `EvalChatProvider(ChatProvider)`，通过只在本评测入口构造的策略适配器接入原图。原图/Store 内的 `mock` 标签仅用于冻结协议兼容；报告的 live/mock 来自独立策略。产品仍 Mock only，没有修改原包的任何源文件、旧 manifest 或旧测试。

## 验证

冻结候选 SHA-256：`ca88083f7b48c15dfc53d84f8dddb6c285395beceb6249d47a6eed65483bb572`。全部检查日志位于 worktree 的 `.data/p7-real/checks/`。

- **最终完整 Python + 隔离 PostgreSQL：938 passed，0 failed，0 skipped；新增通道测试 51 项。** 用时 280.94 秒，日志/报告为 `full-frozen.log`、`full-frozen.xml`、`verification.json`。另有 2 条现有依赖弃用警告。
- 原闪卡/成本冻结闸门定向回归：105 passed。
- 第一轮全量：928 passed，0 skipped，0 failed；后续补强继续独立回归。
- 初次新通道集成的两个 authority 响应契约失败已修复；初始 `new-1.log` 失败记录保留，没有改旧测试、重标错误输出或删除失败日志。
- 最新独立 CLI Mock：`p7-mock-final-20261027`，24 任务，72 次假请求，22 张卡，固定种子抽样 10 张，Mock 机制 PASS；模拟账面 US$0.0108，真实费用 US$0。
- 最终 PG/JSONL 逐条一致性检查：72 calls，10800000 nano-USD（模拟），pending=0；`ledger-final.log`。Ruff 与格式检查通过；固定种子重新导出的 sample.md 字节一致。
- 本任务 PG 已停止，卷 `lecturelens-p7-real-eval-20261027_p7-real-postgres` 保留；见 `compose-stop.log`、`compose-stopped.json`、`container-final.txt`。
- 密钥脱敏覆盖异常原文、响应回显和 JSON 转义回显；所有 live 分支测试仅使用合成 Key 和注入 transport。
- 外部 Python socket 封锁用于所有 pytest 和独立 CLI 检查；Provider 网络传输没有执行。PG 使用显式隔离 DSN。

## 禁止事项自查

1. **真实 Provider 请求：0。** 没有执行文档中的真实命令。所有请求测试使用 `httpx.MockTransport`；独立 CLI 缺 `--live`，即使环境开关为 1 也只走假传输。
2. **未读取或复制真实 secrets.env、任何 .env 或真实 token/密钥文件，未输出真实 Key。** 通道只在 live 分支读取进程环境 `AGENT_LLM_API_KEY`；本轮仅测试合成 Key。文档中的 source 命令留给审查人手动执行。
3. **未 git push、未使用 gh、未开 PR、未部署。** 仅本分支本地提交。
4. **未改原仓库或其他 worktree，未触碰 tmux mea-*。** 所有仓库改动均在 `/home/dev/projects/lecturelens-p7-real-eval`；另仅写本任务运行目录的交付记录和临时测试数据。
5. **未停止/删除/重启任何非本任务容器。** 只创建、使用并停止项目 `lecturelens-p7-real-eval-20261027` 的 PG；保留卷。
6. **未放松旧离线闸门。** `CostPolicy(mode="fake")`、`verify_frozen_agent`、FROZEN/DEVELOPMENT 常量、所有旧 manifest SHA、旧测试语义均未改；原产品 Python 包相对 121ab98 的 diff 为空。
7. **未改 Java、未加 MySQL 表。** 新 PG 表仅 `p7_real_run/p7_real_event` 隔离评测账本；现有图状态使用隔离库中的原 StudyStore/checkpoint 表。
8. **凭据、媒体、私有运行记录未入 Git。** 只提交公开快照和代码/文档；`.data/` 的账本、测试日志、生成/审阅输出保留本地。

## 审查人真实运行命令（本轮未执行）

先按 [README](README.md) 启动本项目的隔离 PG；`eval.env` 需配置 `LECTURELENS_REAL_EVAL=1`，`secrets.env` 注入 `AGENT_LLM_API_KEY`。唯一真实运行入口：

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

同一命令加 `--check-ledger` 只验证本轮 PG/JSONL 逐条一致，不发送请求。run_id 单次使用；未知结果、账本不一致或预算封锁不自动恢复/重发。

## 仍未做

真实 DeepSeek 接口兼容性、来源语义支持率、真实延迟和真实 usage/费用均待审查人手动执行；不保证完整轮次一定能在 US$1 内完成。AU strings/linear 目标未复用；仓库未识别到可逐项比对的 P6 目标集，因此不宣称本批是独立全新 holdout。PDF 的兼容定位字段是明确标记的页码槽，不是真实媒体时间。未验证自动评分、长期记忆、未见课程泛化或长期复习收益。
