# Phase A 复现

从仓库根目录执行。此基准使用提交的公开课程快照，不需要私人账号、API Key、业务 MySQL 或生产 Agent。不要重新上传课程来替换相同ID：重新入库的 ID/revision 不属于该冻结基准。

## 环境与只读冻结校验

```bash
uv sync --python 3.12.14 --locked --project eval/retrieval-phase-a
uv run --locked --project eval/retrieval-phase-a python -c \
  'from pathlib import Path; from lecturelens_agent.benchmark.core import verify_freeze; print(verify_freeze(Path("eval/retrieval-phase-a"))["id"])'
docker compose -f compose.agent.yml up -d
# 仅首次创建。若已存在，直接使用，不要删除其他数据库。
docker compose -f compose.agent.yml exec -T postgres \
  createdb -U lecturelens lecturelens_retrieval_benchmark
export BENCHMARK_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_retrieval_benchmark
```

Torch/Transformers 只在此独立环境安装，未加入生产 Agent 的 dependencies。Dense 与 Cross-Encoder 使用 config 中的固定 revision，首次运行从 Hugging Face 下载并逐文件校验哈希；已缓存时可设置 `HF_HUB_OFFLINE=1`。本轮环境见 [environment.json](environment.json)。

## 四路真实检索

```bash
uv run --locked --project eval/retrieval-phase-a python -m lecturelens_agent.benchmark.run \
  --dataset eval/retrieval-phase-a \
  --output .data/retrieval-phase-a/my-run \
  --cache .data/agent
```

每次使用新输出目录；已有目录会拒绝覆盖。只有全部24题×4路×5次完成、重复排名一致才写 complete.json。输出包括逐题真实 ID 排名、每次耗时、K=1/3/5/8 指标、按类别聚合和检索 Bad Case。检索期间不要同时运行测试、编译或答案推理。延迟依赖硬件与负载，不保证重复得到相同毫秒数。

## 固定真实读者

准备 `config.json.reader.provenance` 指定 revision 的 Qwen GGUF 与 llama.cpp b10977 Linux 二进制；下载地址和文件SHA均已提供。将权重放在忽略目录，不提交Git。本机文件已缓存，启动独立端口：

```bash
uv run --locked --project eval/retrieval-phase-a python -m lecturelens_agent.benchmark.serve_reader \
  --dataset eval/retrieval-phase-a \
  --server .data/l1-acceptance/llama/llama-b10977/llama-server \
  --model-file .data/l1-acceptance/qwen2.5-3b-instruct-q4_k_m.gguf \
  --port 8096
```

另一个终端执行：

```bash
uv run --locked --project eval/retrieval-phase-a python -m lecturelens_agent.benchmark.answers \
  --dataset eval/retrieval-phase-a --retrieval .data/retrieval-phase-a/my-run \
  --output .data/retrieval-phase-a/my-answers --base-url http://127.0.0.1:8096/v1
```

96次真实调用，包含失败不重试。若进程被中断，用同一命令加 `--resume`；已经预约但结果未知的调用计为 InterruptedError，只有从未尝试的项才发新请求。读者看不到 gold。结束后在模型终端 Ctrl-C，仅停止本轮8096实例，不触碰生产8091。

## 语义审阅与报表

逐题对照实际输出、所引原文和必要事实，填写 review 中的三个独立布尔值：answer_correct、all_claims_supported、all_required_aspects，并写具体理由。每条必须绑定该次 response_sha256。错误引用、遗漏条件、凭常识补全和把误解当结论都保留为失败。历史审阅文件只能用于哈希匹配的历史输出，不能直接给新生成结果套分；模型seed不能消除跨硬件数值差异。

```bash
uv run --locked --project eval/retrieval-phase-a python -m lecturelens_agent.benchmark.report \
  --dataset eval/retrieval-phase-a --retrieval .data/retrieval-phase-a/my-run \
  --answers .data/retrieval-phase-a/my-answers --reviews /path/to/my-source-reviews.json \
  --output .data/retrieval-phase-a/my-report
```

本机历史结果保留在 `.data/retrieval-phase-a/run-v1`、`answers-v1`，可用随报告提交的 reviews-v1.json 重新聚合到一个新目录。原始provider响应、请求尝试记录和日志始终留在忽略目录；安全的逐题得分、检索排名及其哈希随公开报告保留。审核人员若不同意语义判定，应另建更正记录，不覆盖本轮评分。

## 测试与回归

```bash
# 首次需要创建独立测试数据库 lecturelens_agent_test，不能使用运行库。
AGENT_TEST_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_agent_test \
  uv run --directory agent-service pytest -q
uv run --directory agent-service ruff check src tests
uv run --directory agent-service ruff format --check src tests
(cd backend && ./mvnw -q \
  -Dtest=StudyControllerTest,StudyAuthorityTest,DenseEvidenceClientTest,DenseRetrievalRoutingTest,CourseQaEvidenceRetrieverTest test)
```

修改冻结文件会被拒绝，必须另建版本并保留原试验；不要为了重新运行删除 freeze.json。本轮结果只属于 [PROTOCOL.md](PROTOCOL.md) 定义的 Phase A 范围。
