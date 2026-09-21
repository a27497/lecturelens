# Evidence RAG 评测准备：pilot-v1

当前阶段是**素材准备**：真实视频、官方字幕、来源与哈希、课程划分、标注协议。尚未完成 50 题人工标注，也没有 keyword/RAG 分数。没有调用付费模型，没有把官方字幕当成实际 ASR 输出。

2026-09-11 已完成首轮下载与核验，具体文件规格、解码和画面抽查见 [准备记录](PREPARATION.md)。

## 本地素材与复现

仓库根目录执行（Python 3.11+、curl、ffprobe）：

```bash
python3 scripts/eval/prepare_corpus.py
python3 scripts/eval/prepare_corpus.py --verify-only
```

首个命令按 `sources.json` 下载并核对 `assets.lock.json`；第二个命令完全离线。脚本拒绝覆盖与锁文件不符的既有文件。新素材集初次登记才使用 `--write-lock`，已有锁文件不可用此选项覆盖。下载中断只留下 `.part`，重试从头下载。完整性包括 SHA-256、大小、音视频轨道、字幕非空/顺序/时间边界；**不等于逐帧解码或人工确认音画字幕同步**。

资源位于 `.data/eval/pilot-v1/<source_id>/`，不进入 Git：

- `video.mp4`：官方下载的整节视频，没有剪辑或重编码，源时间偏移为 0。
- `captions.en.vtt`：官方英文字幕，保留原文件。
- `reference-captions.jsonl`：本地转换的逐条字幕，稳定 `reference_id` 与毫秒时间戳，供标注定位。
- `source-page.html`：本次选材时保存的来源页快照；不是运行评测的输入，复现脚本不重新下载此快照。
- 上层 `verification.json`：最近一次本地验证结果。

视频与字幕可从 `sources.json` 中的官方资源页追溯。视频文件来自该页面明确链接的 Internet Archive 下载地址；旧地址仅改为 HTTPS。不要直接将几十至几百 MB 的原片提交到 Git。

## 选材与划分

| source_id | 内容 | 预期视觉场景（需逐题确认） | 集合 | 题数计划 |
| --- | --- | --- | --- | --- |
| mit-60001-f16-lec01 | Python 入门：What is Computation? | 课件、代码 | dev | 18 |
| mit-1806-s10-lec01 | 线性方程的几何意义 | 黑板、公式 | dev | 16 |
| mit-1401sc-f11-lec01 | 微观经济学导论 | 课堂、图表 | holdout | 16 |

这里的数学课是检索评测素材，不改变项目面向 Agent 应用开发、非算法岗位的定位。18.06 网站课程标为 Spring 2010，但页面说明录像摄于 1999 年秋季；不能把课程页面年份当成录像年份。

这是一批 3 门课、50 题的 pilot；蓝图中的至少 5 门课、约 100 题仍是后续目标。全部视频为英文，计划 35 道中文问题、15 道英文问题。中文问题考察跨语言检索，**不覆盖中文语音识别质量**。同一课程之后新增的讲次/裁剪片段必须沿用课程集合；holdout 不能参与改 prompt、调权重或选择 rerank 参数。只有一门保留课程，不能据此宣称跨领域泛化已充分验证。

## 标注协议

配额见 `annotation-plan.json`：原词事实 10、术语改写 10、时间定位 8、仅视觉 8、跨片段综合 6、无法回答 8，共 50。额外 5 类权限用例单独作为 API 测试，不混入检索命中率。

从 `question.template.json` 复制真实样本，填完后去掉 `evidence_group_template`，写入后续的 `questions.jsonl`；当前模板不能用于计分。字段规则：

1. `id` 稳定唯一；`source_id`、`allowed_source_ids` 来自素材清单；`split` 与课程一致。category 使用配额中的枚举。
2. `expected_behavior` 为 `answer` 或 `abstain`。可回答题写答案要点和必要证据；无法回答题写清缺少的证据，不把模型常识当作课程事实。
3. `required_evidence_groups` 的组之间是 **AND**（综合题需全部覆盖），每组 `alternatives` 内是 **OR**（可替代的正确证据）。`modality` 为 `subtitle`、`ocr` 或 `visual`；时间使用原片绝对毫秒，字幕 ID 来自本地 reference 文件。
4. 视觉题必须实际看帧，记录板书/课件位置及内容，并检查字幕无法独立回答；仅凭“视频有 PPT”不能标成视觉题。低清画面无法辨认时换题，冻结前调整配额并记录原因。
5. 每题检查问题歧义、答案支持、时间对齐和允许课程范围；由人工填写 reviewer、时间和 alignment_checked 后，才能将 status 设为 `reviewed`。AI 草稿不得伪造人工签名。
6. 冻结题集和源哈希后才比较不同方案；保留题只用于最终报告，不能为提高分数反复改题。

## 下一阶段如何接现有项目

先标注并冻结参考答案，再导入真实视频、生成/导出实际 `CourseEvidence`，最后运行当前 keyword QA 的 baseline。**本次没有启动长视频处理、执行真实 ASR/OCR/VLM，也没有注入 mock 字幕冒充实际解析结果。**

需要区分两个可独立报告的实验：

- **检索隔离实验**：固定人工复核的官方字幕语料，比较 keyword/dense/hybrid/rerank，排除 ASR 的影响。当前尚无这一路的 corpus loader 或 runner。
- **端到端实验**：输入原始视频，用真实流水线输出的 evidence 计分，把 ASR/OCR/视觉缺失也算入失败。不能用 Demo provider 的固定输出计算质量分数。

本地 `reference_id` 不是数据库 `evidenceId`。未来导入时保存 `source_id → taskId/courseId + ownerId + revision + video SHA-256`，分页读取 `GET /api/tasks/{taskId}/evidence`，按来源模态、时间重叠及内容复核映射。不能把某次运行的 task ID 写死在金标准中，也不能仅靠时间重叠认定答案被支持。重跑或重建后更新映射，保留题集源标注。

Recall@K/MRR 仅统计可回答题；综合题同时报告“任一证据命中”和“所有必要组覆盖”。不可回答题单独报告拒答率，并同时报告可回答误拒率。跨用户任务/删除任务用固定身份与状态夹具验证 HTTP 与响应内容，不能依赖模型口头拒绝。

## 来源与许可

作者、课程页、视频/字幕下载地址和许可链接逐项保存在 `sources.json`。MIT OCW 当前页面使用 [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)，要求署名、非商业、相同方式共享，参见 [MIT OCW 使用条款](https://ocw.mit.edu/pages/privacy-and-terms-of-use/)。这批用于本地非商业学习与评测；源码许可不会覆盖原始课程素材。对外分发课程片段、字幕或改编资料时须保留各自许可、署名和改动说明，不暗示 MIT 认可本项目。

字幕 JSONL 是对原始 VTT 的格式转换：合并同一 cue 的换行、移除标签、解码 HTML 实体，未更改起止时间。其内容及从课程改编的标注资料沿用 CC BY-NC-SA 4.0。商业产品展示或商业使用应另备相应授权素材；本批没有进行模型训练。
