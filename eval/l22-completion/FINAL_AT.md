# AT 正式配对验收：未通过

2026-09-19。冻结候选之后编写十道新保留题，与十道原开发题组成二十题；两门 MIT 课程、四个真实视频片段，Java 鉴权/Evidence→Agent→PostgreSQL 完整入口。两版均为隔离 qwen3-max 生成与复核；线上 C 与个人配置未变。

| 指标 | 旧 C | AT | 门槛 |
|---|---:|---:|---:|
| 正确类型/结构 | 19/20 | 16/20 | ≥18/20 |
| 支持题完整语义 | 3/16 | 9/16 | ≥15/16 |
| 正确拒答 | 4/4 | 4/4 | 4/4 |
| 原90秒内正确类型 | 19/20 | 16/20 | ≥18/20 |
| P50，含失败 | 9.916s | 11.69s | 报告 |
| P95，含失败 | 12.913s | 25.934s | 报告 |
| 真实模型调用 | 62 | 72 | 原每Run6次 |

全部成功产物的规范引用正文/时间戳/来源均与权威 Evidence 对得上；这不代表其逐题引用语义支持正确。分位数为全部结果的 nearest rank。所有失败均计入分母，未合并多轮产物。逐题判定为 **AI 来源复核，非盲评人工金标准**。

AT 原开发部分内容合格5/8，新保留部分4/8；此前单独开发回归8/8不能替代正式运行结果。问题包括无据范围/效率扩写、复核误拒已核算端点、内部拒绝引用容量不足导致格式失败、输出截断、工具选择偏离查询复杂度目标，以及选择排序中间状态算错。参考答案与评分依据同源消除了两者独立生成的矛盾，但不能保证同源答案本身正确。

323项 Python/独立 PostgreSQL 测试通过，无跳过。正式AT的16份成功产物已跨同一冻结源重启验证内容、私有答案、事件游标及START幂等重放一致，调用数未增加；取消验证通过。真实浏览器验证选择排序练习刷新恢复、答案按需显示、手机宽度无横向溢出。以上仅证明机制；AT质量门槛未通过。最终删除验收暂未执行，隔离课程仍供后续开发使用；删除前将私有备份历史失败的完整数据库。

这十道保留题现已消费，后继候选必须冻结后再编写新的保留题。Phase保持进行中，不进入L3，不部署。

- [冻结身份](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-at-freeze.json)与[任务](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-at-cases.json)
- [C报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-at-baseline-c-report.json)与[逐题复核](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-at-baseline-c-reviews.json)
- [AT报告](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-at-candidate-report.json)与[逐题复核](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/final-at-candidate-reviews.json)
- [浏览器](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/at-formal-browser-report.json)、[重启恢复](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/at-formal-verify-report.json)、[取消](https://github.com/a27497/lecturelens/blob/study-agent-au-evidence-2026-09-20/eval/l22-completion/at-formal-cancel-report.json)
