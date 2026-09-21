# L2.2：真实课程质量与延迟评测

**2026-09-19 当前验收状态：** 冻结BC在隔离qwen3-max生成／复核下完成L2.2既定Phase验收：20/20类型结构、16/16内容、4/4拒答；391项Python／独立PostgreSQL测试、20份产物重启与幂等恢复、浏览器、取消及删除检查通过。范围为两门已见课程、四段视频上的10道开发与10道新目标，AI来源核查，不代表未见媒体泛化。候选未发布，线上C及个人模型配置不变；L3未启动。 见 [最终报告](../eval/l22-completion/FINAL_BC.md)。

以下保留按日期与候选记录的历史过程；旧轮次失败不被覆盖。

日期：2026-09-15。顺序：Evidence 同步 → L2.1 执行闭环 → **L2.2 质量门槛** → L3 作答、评分与薄弱点记录。

## 结论与边界

本轮实现了可复现评测、证据上下文修复、证据不足终态和实际模型耗时统计。当前本地 Qwen2.5-3B-Instruct Q4 / CPU 配置仍有答案错误，**不能进入 L3 自动反馈与学习记忆**。可恢复执行、有效引用 ID 和正确的接口返回，不等于教学内容正确。

L3 尚未实现作答持久化、rubric 反馈或薄弱点记录；页面中的作答仍只保留在当前页。不能把本轮未通过审核的参考答案用于判断用户能力。

## 真实课程与固定任务

自行检索 MIT OCW 官方资料并下载完整视频、官方字幕，再制作四个带字幕短视频，通过正式上传与处理链路建立四门独立验收课程：

| 原课程 | 片段（原视频时间） | 用途 |
| --- | --- | --- |
| [MIT 6.0001，Lecture 3，Ana Bell](https://ocw.mit.edu/courses/6-0001-introduction-to-computer-science-and-programming-in-python-fall-2016/resources/lecture-3-string-manipulation-guess-and-check-approximations-bisection/) | 11:00–12:57 字符串；38:50–40:08 二分查找 | 开发集 10 题 |
| [MIT 6.006，Lecture 2，Erik Demaine](https://ocw.mit.edu/courses/6-006-introduction-to-algorithms-spring-2020/resources/lecture-2-data-structures-and-dynamic-arrays/) | 01:05–03:35 接口/实现；45:10–48:00 摊还分析 | 保留集 10 题 |

每个片段有解释、比较、应用、错误观念纠正、课程外问题各一题：共 16 个可回答目标和 4 个证据不足目标，覆盖中英文。题目及要求在运行前冻结；最终候选冻结后才查看保留集产物，未根据其输出修改候选。

来源 URL、下载 SHA-256、署名和裁剪偏移见 [sources.json](../eval/study-v1/sources.json)，模型与二进制固定版本见 [runtime.json](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/study-v1/runtime.json)。素材与其派生评测材料按 [MIT OCW 条款](https://ocw.mit.edu/pages/privacy-and-terms-of-use/) 使用 CC BY-NC-SA 4.0；本地非商业开发，视频不提交仓库，MIT 不为本项目背书。

未使用 HTTP mock、固定答案或付费模型。视频使用真实官方嵌入字幕，OCR/VLM 关闭；本轮不是 ASR 或多模态准确率评测。接口片段字幕覆盖率为 78.2%，仅本次验收环境将嵌入字幕门槛设为 75%，未更改产品默认 80%。原失败课程与重试新课程均纳入清理。处理链路中已有的翻译/学习资料降级可能发生；Study 直接读取权威 Evidence，课程处理时长不计入 Study 生成延迟。

## 比较方法

- 同一个本地模型进程、4 CPU 推理线程、8192 context、单槽串行运行；温度 0.2，默认 90 秒执行预算。课程在第一次提问之前已经 READY。
- 基线为本轮优化前冻结的 L2.1 源码；最终候选包含 Python 上下文/工具约束优化及 Java 相邻证据补全。未更换模型或增加 deadline。
- 不在实际推理评测期间运行编译和重型测试。每题独立 Session；所有失败保留，没有重跑覆盖失败项。
- 延迟以数据库 `finished_at - created_at` 为准，包含排队；执行/排队时间另存。P50/P95 用 nearest rank，包含全部成功与失败，不能视为成功请求的响应时间。
- 逐题检查解释、私有答案、rubric 与实际引用的原始片段，检查概念题和应用题是否不同。所有复核由 AI 完成，**不是人工金标准**。报告不以结构/ID 检查替代语义复核。
- 每个候选只运行一轮，未固定采样 seed；不提供统计显著性或生产吞吐量结论。仅有两门课、四个短片段，不能推广至完整长课、并发负载、ASR 错误或视觉证据。
- 预先固定的门槛见 [评测约定](../eval/study-v1/README.md)：至少 90% 结构正确、90% 支持题语义合格、90% 全部请求在 90 秒内完成正确类型产物；4 个课程外目标全部正确停止；没有严重无据断言。

## 已落实的修复

1. 增加 `report_insufficient_evidence`：检索后可明确保存证据不足结果，无练习、引用及答案按钮。是否正确选择该工具仍要语义验收。
2. 第一次决策仅暴露检索工具；仅在用户目标含时间表达时提供时间过滤字段，并删除模型自行添加的非请求时间限制。
3. 使用标准工具调用消息；压缩 schema 的说明性元数据时保留业务属性名，修复误删 `PracticeArgs.title` 的缺陷。
4. Java 检索命中优先用同时间原始字幕，去除重复翻译；补入同来源的相邻片段，总计最多 8 条。窗口按来源和时间排序，修复跨字幕/翻译分组取错相邻项的问题，保持显式时间范围。
5. 每条可见正文最多 600 字符，使用本次决策内的短引用编号，返回时恢复并校验 canonical ID。输出上限 900 tokens；提示要求简短解释和同一知识点的两种题型。
6. 记录每次模型开始/完成、耗时及实际返回的 token usage。保守预算预留与 provider usage 分开；失败调用缺失的 usage 保持未知，不能当作零成本。

这些修复改善了执行与证据输入，未实现自动事实验证器。更完整的证据输入仍不能保证小模型正确使用它。

## 最终结果

完整逐题记录：[基线](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/study-v1/baseline-report.json)、[最终候选](../eval/study-v1/final-report.json)。

| 指标 | 冻结基线 | 最终候选 |
| --- | ---: | ---: |
| 观察任务数 | 20/20 | 20/20 |
| Run 成功结束 | 6/20 | 20/20 |
| 正确类型与结构 | 5/20 | 19/20 |
| 90 秒内得到正确类型产物 | 5/20 | 19/20 |
| P50，全部结果 | 74.449 秒 | 46.382 秒 |
| P95，全部结果 | 90.967 秒 | 62.160 秒 |
| 证据不足正确停止 | 0/4 | 3/4 |
| 支持题完整语义验收 | 0/16 | 1/16 |
| 严重错误或无据断言 | 3 | 6 |
| 总模型调用 / 工具调用 | 43 / 32 | 40 / 40 |

最终每题均为 2 次模型决策、2 次工具执行。实际 provider usage 合计 39,578 输入 / 5,661 输出 tokens，40 次调用均有记录。基线没有实际 usage 埋点，不能据此宣称 token 成本下降；基线有 8 次预算耗尽、6 次其他失败，严重错误绝对数也不能直接当作准确率比较。

“完整语义验收”要求解释/答案、引用支持、题型区别同时通过，**不是单独的答案正确率**。最终支持题的分项复核：引用支持 6/16，解释/答案正确与完整 9/16，题型区别 7/16；三项交集为 1/16。AI 复核理由随每题保留，允许后续人工复审更正。

| 分组 | 基线：正确类型 / 语义 | 最终：正确类型 / 语义 | 最终 P50 / P95 |
| --- | --- | --- | --- |
| 开发 10 题，其中支持题 8 道 | 1/10；0/8 | 10/10；0/8 | 46.382 / 67.624 秒 |
| 保留 10 题，其中支持题 8 道 | 4/10；0/8 | 9/10；1/8 | 44.745 / 61.491 秒 |

最终类型/结构、引用来源真实性及延迟门槛通过；**语义、全部课程外拒答、无严重无据断言三项门槛失败**。来源真实性只代表这些片段确实来自当前课程，不代表片段支持所生成的断言。

代表性残留问题：

- `strings-03`：把在 `hello` 前添加 `y` 当成得到 `yello` 的步骤，遗漏切片操作。
- `bisection-03`：将用户的区间更新问题改成对已知目标直接除二，给出错误答案。
- `amortization-01/02`：把平均常数成本混为每次或整段操作序列都为常数。
- `amortization-05`：将几何级数片段错误嫁接为 SHA-256 常数推导，没有选择证据不足终态。
- 其他部分产物解释正确，但两题重复，或题目自己的引用未覆盖答案所需的关键片段。

## 验证与清理

- Java **1,362 项**通过；Python **74 项**通过；前端 **48 项**通过、生产构建通过。Python 有一条既有 Starlette/AnyIO 弃用提示。
- Java 新增原始字幕优先、相邻窗口来源/排序、显式时间范围验证；已有身份、课程版本和索引就绪保护继续通过。
- Python 检查 schema 必填业务属性、错误时间过滤、短引用可见性、证据不足终态、实际 usage 事件，以及禁止混合候选/数据集拼成一次验收。
- 真实 Chromium 检查了证据不足产物、刷新后恢复、没有空练习/答案控件；390px 手机视口无横向溢出。浏览器结果仅证明界面与数据流，不替代内容评测。
- 删除本轮创建的 4 门成功课程与 1 门失败重试前课程后，Study/Evidence 立即返回 404。5 个索引留下 DELETED tombstone；55 个 Session/Run 的向量、indexed Evidence、产物、工具结果、事件和三个 checkpoint 表关联行均为 0。原视频、片段与评测记录仍保留在本地。
- 本轮自建服务已停止，数据卷及其他项目服务保留。公开的 [验证摘要](../eval/study-v1/verification.json) 不含测试凭据或会话 ID。

## 保留的开发试验

- [第一次开发试验，5 题](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/study-v1/development-v1-report.json)：schema 删除业务字段导致工具参数失败；模型自造时间过滤导致错误拒答。保留部分队列结果，未混入最终成绩。
- [第二次开发试验，10 题](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/study-v1/development-v2-report.json)：可运行性提高，但出现将 50 与 100 的中点算成 63、把排除一半说成排除全部、编造课程外 transformer 学习率等错误。由开发题定位后修复证据输入，最终候选另用新 label 完整运行。
- [冻结基线，20 题](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/study-v1/baseline-report.json)：6 次运行成功；运行成功的内容也有无据断言、错误或重复题型，因此不能用这 6 次当作品质合格。

## 下一轮进入 L3 的条件

先在目标推理资源上验证更可靠的模型配置，并增加解释/答案一致性与引用支持检查。新候选需要新的、未用于调参的保留任务；这轮保留集一旦公开分析，不能继续当作未见测试集。沿用当前质量/延迟门槛，不以扩大超时或降低评分标准放行。

通过后再实现最小 L3.1：先保存用户实际作答，再保存独立的模型反馈；薄弱点必须能追溯至作答、题目和证据，支持更正/删除，不将空白答案或模型推测当作学习事实。

## 复现入口

```bash
python3 scripts/eval/prepare-study-courses.py
# 正式上传四个 clip；索引 READY 后才运行。服务配置与私有运行文件见评测约定。
uv run --directory agent-service python ../scripts/eval/evaluate-study.py --label my-candidate
python3 scripts/eval/report-study.py --results .data/l22-eval/my-candidate.jsonl \
  --reviews .data/l22-eval/my-reviews.json --output /tmp/my-study-report.json
uv run --no-project --with playwright python scripts/eval/check-study-eval-browser.py \
  --results .data/l22-eval/my-candidate.jsonl --clip strings
```

完整原始产物、引用正文、实际调用日志与源码快照保留在本地忽略目录 `.data/l22-eval/`；凭据文件 0600，不入库。公开报告仅保留聚合指标和逐题复核结论。运行相同 label 只恢复未记录任务，不替换任何失败记录；变更源码、模型、预算、Java 包或数据集后必须使用新 label。

## 后续草稿复核试验

本报告及 Study v1 结果保留为历史记录。后续新增独立上下文的草稿模型复核和反馈修订循环，沿用原有预算；使用新的 MIT 第 4 讲六题保留试验，见 [实现与边界](L2_QUALITY_REVIEW.md)。小规模回放试验不替代这里定义的 L3 准入门槛。
