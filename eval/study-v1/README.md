# Study v1 小型评测

本评测用于本地非商业开发。20 个固定任务，来自两门 MIT OCW 课程的四个真实视频片段；源视频和官方字幕的下载地址、署名、许可、裁剪范围及 SHA-256 见 `sources.json`。视频不入库；派生评测材料采用 CC BY-NC-SA 4.0，项目源码许可不变。MIT 不为本项目或输出背书。

`cases.json` 在运行前编写并冻结。Python 编程课程的 10 题用于开发，算法课程的 10 题为保留测试，不根据其输出调参。每组含 8 个可回答任务和 2 个证据不足任务，覆盖中英文、解释、比较、应用和错误观念纠正。答案要点由 AI 阅读官方字幕后编写；不是人工金标准，也不是完整课程质量证明。

## 预先固定的进入 L3 条件

- 完成全部 20 个任务，不剔除超时或失败；开发/保留测试分别报告。
- 正确产物类型与结构通过率至少 90%；所有已完成练习的引用来源、正文和时间戳正确。
- 四个课程外任务均明确证据不足，不编造答案或无关练习。
- 对解释、私有答案和两题区别逐条进行来源复核，无严重无据断言；至少 90% 可回答任务通过这三项。
- 默认 90 秒执行预算保持不变；至少 90% 全部请求在 90 秒内成功，报告含失败的 P50/P95。排队时间另列，不以增加 deadline 宣称性能达标。
- 与同模型、同课程、同任务、同硬件的旧实现比较。开发试验单独保留，不能混入最终保留成绩。

逐条复核记录必须标注 AI/人工身份；自动 ID/格式检查不能替代语义复核。这个小样本只作为是否推进最小作答闭环的工程门槛，不提供教学有效性或能力测量结论。

## 复现

1. `python3 scripts/eval/prepare-study-courses.py` 下载、校验并制作四个字幕片段。
2. 配套启动真实 Java/Python/PostgreSQL 与支持工具调用的模型；将四个视频通过 `accept-study-agent.py --phase prepare --video ... --output .data/l22-eval/courses/<clip>` 上传。
3. 私有 `.data/l22-eval/runtime.local.json` 保存本次环境（包括 `AGENT_DATABASE_URL`）；不要提交凭据。
4. `uv run --directory agent-service python ../scripts/eval/evaluate-study.py --label baseline` 执行冻结基线，切换实现后以新 label 执行。重复使用 label 只恢复未完成项，不替换失败项。
5. 复核每条实际产物与 `canonical`，写入有 reviewer 和理由的 review JSON，再运行报告脚本。

各 label 的完整结果在 `.data/l22-eval/<label>.jsonl`；其中包含真实派生产物和测试用户信息，默认 0600 且被 Git 忽略。对外报告仅提交汇总指标、逐条结论和必要的短摘要。

`review` 每项含 `reviewer`、`reason`、`grounded`、`answers_correct`、`questions_distinct` 与 `serious_unsupported`；没有完成语义复核不能通过。严重无据断言为单独门槛，不能隐藏在 90% 汇总通过率中。报告中的 usage 只统计 provider 实际返回的部分，并列出未知调用数。

本轮实现、测量条件、失败分析和 L3 状态见 [L2.2 评测记录](../../docs/L2_QUALITY_EVALUATION.md)。源视频和片段保留在本地忽略目录。浏览器检查结束后可运行 `uv run --directory agent-service python ../scripts/eval/cleanup-study-eval.py`，仅删除 manifest 及验收账号关联的课程，并检查其向量、学习产物与 checkpoint 清理。
