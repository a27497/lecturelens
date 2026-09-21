# Phase A：Retrieval Benchmark

**2026-09-21，Phase A 已完成。** 四路真实检索、96次真实读者调用、逐题来源审阅和必要回归均已完成；生产默认检索与 Java authority/permission/revision/deletion 未改，不进入 Phase B/C/D。完成的是固定基准，不是生产质量准入。

## Benchmark

MIT Python／算法两门已见公开课程的4个短片段，**70条真实 Java Evidence，24题（20可回答＋4无答案）**；六类查询各4题：lexical、semantic、multi-condition、cross-section、no-answer、hard negative。英语20题、中文4题。原文、重复翻译和省略均保留；70/70 IDs、正文哈希、时间及权限/版本标识与历史认证导出完全匹配。

复用生产 Dense 的固定多语言 MiniLM、chunker、PostgreSQL/pgvector 与版本围栏。BM25+Dense 为等权归一化分数融合；RRF k=60；Cross-Encoder 为固定多语言 mmarco-mMiniLMv2-L12-H384-v1。使用独立数据库和独立 Qwen2.5-3B Q4_K_M 读者，所有方法同样 top-3 上下文。模型从未看到 gold。参数、源码、依赖和权重哈希在首次评分前冻结：[freeze.json](freeze.json)、[协议](PROTOCOL.md)。

## 四路真实指标

检索质量列均为 **@3**、20题宏平均；GAR 是完整正确＋引用支持的严格 Grounded Answer Rate（分母20）；Refusal Accuracy 包含可回答题与无答案题的分类（分母24），不代表答案正确率。延迟包含 query embedding、PG查询与融合／重排，每路120次真实观测；不含建索引、读者和 Java HTTP／相邻补读。

| 方案 | Recall@3 | MRR@3 | nDCG@3 | Evidence Coverage@3 | 严格 GAR | Refusal Accuracy | P50 / P95 ms |
|---|---:|---:|---:|---:|---:|---:|---:|
| Dense | 46.86% | 0.7833 | 0.6633 | 77.08% | 20%（4/20） | 75%（18/24） | 30.87 / 36.30 |
| BM25 + Dense | 33.27% | 0.7750 | 0.5362 | 74.17% | 35%（7/20） | 70.83%（17/24） | 39.12 / 46.19 |
| Hybrid + RRF | 33.99% | 0.7500 | 0.5424 | 74.17% | **40%（8/20）** | 75%（18/24） | 38.81 / 45.69 |
| Hybrid + RRF + CE | **52.74%** | **0.8417** | **0.7617** | **82.08%** | 25%（5/20） | 70.83%（17/24） | 334.80 / 474.55 |

| 辅助指标 | Dense | BM25 + Dense | RRF | RRF + CE |
|---|---:|---:|---:|---:|
| Recall@8 | 74.90% | 77.24% | 77.77% | 77.77% |
| Evidence Coverage@8 | 88.33% | 92.08% | 93.33% | 93.33% |
| 无答案正确拒答 | 3/4 | 1/4 | 3/4 | 2/4 |
| 可回答题误拒答 | 5 | 3 | 3 | 4 |
| 协议失败（保留分母） | 0 | 2 | 2 | 2 |

K=1/3/5/8完整指标及类别分组：[metrics.json](results-v1/metrics.json)。96个检索结果与480次耗时：[逐题排名](retrieval-v1-retrieval.jsonl)。96个实际答案均由 Codex 逐题对照来源审阅（**非盲评人类金标准**）：[审阅记录](reviews-v1.json)、[逐题得分](results-v1/answer-scores.json)。真实响应与请求尝试账本保留在忽略目录 `.data/retrieval-phase-a/answers-v1/`，不提交凭据或原始provider正文。

## Bad Case

- **`strings-multi-condition`**：四路连 top-8 都未召回拼接／切片 gold；读者2路误拒答、2路输出非法JSON。真实失败未删题。
- **`strings-confusing-evidence-hard-negative`**：前3条偏向“也许可以赋值”的假设，纠正片段排名5或6；四路均误拒答。
- **`bisection-cross-section`**：CE 将较大搜索空间的结论挤出前3，事实覆盖从其他三路100%降至50%。其他三路内容虽正确，却漏引该结论来源，也未通过严格GAR。
- **`strings-cross-section` / Dense**：完整证据已经命中，仍说旧对象保持与变量绑定，属于读者误解，不能靠 Recall 掩盖。
- **`strings-exception-no-answer` / BM25+Dense**：标记 refused=true，却在正文填入课程未给出的 `ValueError`，拒答失败。`interfaces-exception-no-answer` 四路均复述“two main interfaces”，没有拒绝缺失的名称。
- **`amortization-semantic` / CE**：把每次操作的平均成本误写成每次扩容的平均成本；检索有改善，实际答案仍错。

完整失败集合：[检索 Bad Case](retrieval-v1-retrieval-bad-cases.json)、[答案 Bad Case](results-v1/answer-bad-cases.json)。6个协议失败包含缺字段、非法JSON和空答案，全部保存且未重试覆盖。

## Trade-off 与推荐

**本轮离线优先候选为 Hybrid + RRF；线上继续保留 Dense，本 Phase 不部署。** 在固定读者下，RRF严格GAR比Dense高20个百分点（多4题），P95只增加9.39 ms；但其@3 Recall和nDCG明显更差，不能宣称检索全面优胜。它在@8有更高覆盖，短上下文排序仍有问题。

**不推荐本轮 CE 作为默认方案。** 相对RRF，它@3 Recall提高18.76个百分点、覆盖提高7.92个百分点，但严格GAR下降15个百分点（少3题），P95增加428.86 ms、约10.39倍。相对Dense仅多1题严格通过，P95约13.07倍。真实排名增益没有转化为相称的答案收益。

结论仅限这个小基准：cross-section是片段内部相隔步骤，不是跨讲检索；原文/翻译重复会影响ID Recall；无答案仅4题；corpus中的旧split仅是历史来源元数据，本轮没有未见保留集；固定3B单轮读者不是完整Study Agent工具循环。严格GAR还要求冻结的全部事实与准确引用，不能解释为“其余回答全错”。例如接口hard-negative的gold要求补充接口职责，超出题面简短二选一回答；该标注限制已披露，未事后改分。尚不足以证明统计显著性、长课／未见课程泛化或产品教学质量。

## 复现与测试

[完整复现命令](REPRODUCE.md)包含独立PG、锁定依赖、固定模型启动、96次调用、恢复及报表再生成。检索入口：

```bash
BENCHMARK_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_retrieval_benchmark \
uv run --locked --project eval/retrieval-phase-a python -m lecturelens_agent.benchmark.run \
  --dataset eval/retrieval-phase-a --output .data/retrieval-phase-a/my-run --cache .data/agent
```

**564项 Python 全量测试通过，无数据库跳过；62项 Java Study／Evidence／Dense 回归通过。** 新增17项基准机制测试覆盖手算指标、gold归属、冻结、防混合评分、owner/revision/allowlist/window/deletion与重排中删除。Ruff检查／格式及Git whitespace检查通过。实际模型指标与确定性测试分开；前端与Java代码没有变更。[验证记录](verification.json)。

课程来源与字幕派生素材按 corpus 中的 MIT OCW **CC BY-NC-SA 4.0** 署名和条件使用；Python片段署名Ana Bell，算法片段署名Erik Demaine；MIT不为本项目背书。模型说明见 [Cross-Encoder模型卡](https://huggingface.co/cross-encoder/mmarco-mMiniLMv2-L12-H384-v1)。
