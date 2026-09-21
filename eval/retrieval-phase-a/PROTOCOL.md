# Phase A 冻结协议

本轮仅完成 Retrieval Benchmark；不发布检索改动，不进入 Phase B/C/D。

## 数据与边界

- 4 个真实 MIT OCW 课程片段，70 个 Java canonical Evidence IDs（原文和翻译全部保留）；来自过去 `evaluate-study.py` 认证导出的 `canonical`，原始归档 SHA-256、课程 ID、owner、revision、内容哈希、来源 URL、时间偏移、许可均在 corpus 中。该历史快照不是当前 Java 授权，也不连接业务 MySQL。
- 24 个新编检索问题，每片段各 6 类：lexical、semantic、multi-condition、cross-section、exception/no-answer、confusing-evidence/hard-negative。20 个可回答、4 个不可回答。英语 20、中文 4；不是语言均衡基准。
- gold 在检索前按全文编写并复查；每个必要事实列出真实 Evidence ID 替代集合，no-answer 列出缺失依据，hard-negative 列出易混淆片段。翻译可能错位或省略，按正文标注，不按时间戳机械配对。不修改字幕错误。
- 这是已见课程短片段的固定诊断集，不是新的独立保留集；不复用 AU 题目或质量结论。标注与语义复核由 Codex 完成，不冒充盲评人工金标准。

## 预先固定的四路

1. Dense：复用生产 LocalEmbedding、240 字符／40 重叠 chunker、真实 PostgreSQL/pgvector cosine 与 Evidence ID max pooling；分支 top-8。
2. BM25 + Dense：BM25 k1=1.2、b=.75，英文小写词／数字／下划线＋中文单字；稀疏 top-8 仅保留正分。各分支分数除以自己的最大正分、负数裁为零，然后 0.5/0.5 加权，缺失贡献为零。检索 ID 并集再排序。
3. Hybrid + RRF：同一两分支，各出现的候选贡献 `1/(60+rank)`，按总和排序。
4. Hybrid + RRF + Cross-Encoder：对 RRF 前 8 个 Evidence 使用固定多语言 mmarco-mMiniLMv2-L12-H384-v1，query/chunk 成对推理、max pooling。不是 LLM 假扮 reranker。输入上限512 tokens、CPU2线程、batch32。模型 revision 和逐文件哈希在 config 中。

所有平分按 Evidence ID 排序。每次分支使用同一课程、revision、allowlist、时间边界；复用生产 ready/version/deletion 检查，重排后再次检查 snapshot。向量只写独立 `_benchmark` PostgreSQL 数据库。生产默认路径、Java authority、数据库所有权不变。

## 指标与分母

- K=1/3/5/8；主比较使用 K=3，对齐固定答案上下文。Recall@K = 命中相关 ID 数／gold ID 并集大小；MRR@K = 前 K 第一个相关 ID 的倒数；nDCG@K 使用二元 relevance、log2 折扣和理想前K排序。主表 MRR/nDCG 也截断于3。
- Evidence Coverage@K = 至少命中一个替代来源的必要事实数／必要事实数。它不同于 ID Recall；相同语义的原文/翻译在 Recall 中仍是两个真实 ID，在事实覆盖中是替代来源。
- 以上指标只在20个可回答问题上宏平均；no-answer 的检索指标是 null，不制造满分。无答案与 hard-negative 的命中记录保留。
- Grounded Answer Rate = 完整正确回答、每项实质断言被所引的实际上下文支持、必要事实齐全、引用有效且未拒答的题数／20。引用 ID 存在不等于语义支持；所有生成结果逐题对照问题、gold和所引原文复核。
- Refusal Accuracy = 正确回答类别的可回答题（未拒答）＋无未支持教学内容的正确拒答题，除以全部24题。另列 no-answer refusal rate（分母4）、可回答题误拒答数、协议错误数。正确分类不等于答案正确；错误、超时、截断不从分母删除。
- 检索 P50/P95：四路轮换执行顺序；每题每路5次、每路120样本。每次重新编码query，计入PG readiness/search、BM25/fusion/reranking，包含所有查询类别；线性插值百分位。权重加载、建索引、固定非评分warmup、答案生成和语义审阅不计入。该延迟不含 Java/HTTP/邻窗扩展，也不是并发生产SLA。

## 统一答案实验与失败保留

- 固定 Qwen2.5-3B-Instruct Q4_K_M，独立 llama.cpp 本地端口，CPU4线程、8192上下文、单槽、temperature0、seed17、512输出tokens。权重与二进制校验，不调用生产端口，不使用付费回退。
- 每题每路一次真实调用，96次；只传问题及 top-3 正文，每条最多1200字符，使用短引用映射回 canonical ID。模型看不到 gold、类别、答案、其他策略结果。不增加相邻片段，不做 Agent 工具修订，避免引入额外变量。
- 公布逐题检索排名、语义判定、失败原因与哈希；原始provider响应/逐题生成留在忽略的0600本地目录。请求前 fsync 持久化尝试；恢复只补未尝试项，中断后不明结果记失败，不重试覆盖。
- freeze 绑定数据、参数、prompt、全部benchmark代码、生产复用模块和依赖版本。完成态拒绝混合冻结或被修改的结果；输出目录独占创建。未通过或被中断的试验原样保留。没有追求漂亮分数的调整轮次。

## 解释限制与选择原则

仅4短片段、70含重复翻译的候选、24题；cross-section指片段内部的相隔教学步骤，不是完整课程跨讲检索。只4道no-answer无法给出稳健拒答率估计。没有并发、长课、未见课程、ASR噪声或统计显著性结论。

先看事实覆盖和真实答案增益，再看延迟；reranker没有净收益或代价明显时如实推荐保留Dense或更轻方案。即使离线胜出，本Phase也不修改线上默认值。
