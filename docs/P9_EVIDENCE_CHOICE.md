# 课程证据选择题与程序判分（P9）

「解释与练习」默认仍为开放题。选择「课程证据选择题 + 开放题（Mock）」并提交目标，才创建新的学习 Run；当前 Mock 生成一题课程原文识别单选题和一题开放文本题。题目引用本课程、当前版本内实际检索到的 Evidence。当前仅验证机制，不支持真实 Provider 的选择题生成，也不继承 AU、P7 或 Tutor 的教学质量结论。

## 学生行为

- 选择题列出选项；未选择时不能提交，不写作答或对错记录。点击「提交并判分」后，程序对照本题私有答案键返回正确或错误，同时展示正确项、课程原文和时间定位入口。
- 更换选项需要再次提交，产生不可变的新版本。当前未提交选择不会改变上一版结果；历史和刷新均按已保存版本展示。
- 开放题继续保存 `answer_text`，不生成程序判分结果。证据反馈仍需显式请求且 `STUDY_FEEDBACK_ENABLED` 默认关闭；核对记录不变。
- 「继续本次练习」跳过已有程序判分的选择题，继续处理其余未完成记录；仍可手动回看选择题。[P10](P10_CHOICE_REVIEW.md) 另提供同课程当前版本的跨会话答错回看；没有正确率或掌握程度统计。
- 原有开放题发布审批保留。当前 Mock 选择题生成不支持发布前审批；界面明确提示并禁用该组合，服务端也拒绝该组合。

## 协议与私有数据

沿用 `POST /api/tasks/{id}/study/command`；带学习范围的生成仍走 `scoped-command`。Java 只转发必要字段并在前后检查认证用户、课程与 revision，不判分、不写 Agent 表。

| operation | 新字段 / 行为 |
| --- | --- |
| `START` | 可选 `practice_format: "choice"`；省略或 `"open"` 保持原路径。模式随 Run 持久化、参与幂等比对且不可更改；真实模式和选择题审批组合被拒绝。 |
| `READ` | 选择题公开 `kind: "choice"`、`options: [{id,text}]`；题目投影不包含私有 `correct_option_id`。 |
| `ANSWERS` | 开放题保留显式参考答案；选择题仍只返回公共题面和选项，不能绕过提交获取答案键。 |
| `SAVE_ATTEMPT` | 开放题传 `answer_text`；选择题只传 `selected_option_id`，不可混传。两者都需要 request_key、expected_version 和显式 Session/Run/artifact/question。 |
| `ATTEMPT_HISTORY` | 返回按不可变作答版本保存的选择与对应判分；沿用分页和所有权围栏。 |

Python 将正确选项身份保存在 PostgreSQL 私有 `study_artifact.content.questions`。选项文字本身是公开题面；公开之前隐藏的是哪项正确的身份/标记，不限制学生阅读原课程。

`study_attempt` 增加可空 `selected_option_id` 与 `choice_result` JSONB。有效选择必须属于该题选项；服务器从选项生成保存的 answer_text，不信任客户端提供的选项文字或对错。`is_correct = selected_option_id == correct_option_id` 是全部判分规则，没有额外模型调用。结果中包含私有键和该题引用，仅随已提交的作答结果下发。开放题的两个字段为空，公共响应保持原形状。

保存作答、判分及事件在同一事务完成。原 Session/Run 锁、expected_version、重试 request_key 和删除级联继续生效。同 key 同正文返回原记录，即使已有更新版本；不同正文或竞争旧版本返回冲突，不另写结果。新字段有配对约束，空选择不会形成错误记录。

## 生成与执行边界

Mock 决策先选择 `search_choice_evidence` 并观察课程片段，再选择 `create_evidence_practice` 或 `stop_choice`。当前题型仅辨认精确课程原文：生成器选取实际片段，程序验证正确项等于引用原文及 Evidence 集合，非法 key 或引用在发布前失败。证据不足时保存明确的不足产物，不生成可判分题。

该路径使用原有 Run 预算、模型/工具保留、私有调用日志和 PostgreSQL checkpoint；恢复不重复生成产物，取消后的晚到响应不得发布。`queued_choice_v1` / `running_choice_v1` 防止旧 worker 误消费该协议；一个 Session 的活动执行约束同时覆盖开放题、选择题、反馈和闪卡。没有增加预算或 worker 数量。

模型响应、私有答案键和工具参数不进入公开 EVENTS；READ/ANSWERS 使用正向字段列表。评分读取绑定在当前权属/课程版本的产物，不跨服务写表。回滚应先停止新选择题生成并取消/排空对应 Run，保留新增字段与已有学习记录，不把新状态改名交给旧 worker。

机制验收与命令见 [P9 本地验收说明](../eval/p9-choice/README.md)。跨会话答错回看见 [P10](P10_CHOICE_REVIEW.md)；通用选择题内容质量、真实模型、未见课程泛化、掌握度和自适应后续练习均未验收或未实现。
