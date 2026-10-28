# 答错待回看（P10）

未发布的「解释与练习」新增「答错待回看」入口。它只读汇总当前用户、当前课程、当前 revision 内，跨 Session/Run 的已有 P9 选择题程序判分事实。没有新的模型调用、出题路径、表或学习者画像。

## 学生行为

- 每个 artifact/question 先取最新已提交作答版本，再筛选 `choice_result.is_correct === false`。改答正确并提交新版本后，该题退出默认列表；未提交的当前选择不影响已保存结果。重复生成的不同 artifact 是不同题目，不按文本推测合并。
- 每项展示公开题干/选项、已保存版本与选择、该版已揭示的正确项、课程原文和时间定位入口。「打开原题与作答」恢复具体 Session/Run/artifact/question，允许按 P9 原路径修改并重新提交；不生成新题。切换仍遵守未保存输入的确认保护。
- 刷新和其他学习会话均能重新读取。入口不依赖最近 20 个 Session 的 LIST 窗口，原题可以来自更早的 Session。每页最多 20 题，按最近提交时间及 attempt ID 排序；并发修改可能改变分页位置，应刷新列表。
- 计数按每题最新已提交版本区分正确/错误，文案为「已提交程序判分：正确 X · 错误 Y」，同时明确「仅统计已提交的选择题程序判分结果，不是掌握程度」。不是全部历史提交次数，也不显示百分比或能力分数。
- 无错误记录时，空态只说明最新已提交版本没有错误。未选择、未提交、开放题反馈和闪卡自评不计入；加载失败显示错误，不冒充空态。

## 协议与权限

沿用 `POST /api/tasks/{id}/study/command`，新增只读 `operation: "CHOICE_REVIEW"`，可选 `after` 分页偏移（默认 0，范围 0..2147483647），无需 Session 或 request_key。Java 只放行该 operation 和校验偏移，使用认证用户、路径课程及权威 revision 构造签名请求，读取前后核验课程权属/版本。无需新网关字段、MySQL 表或跨服务写入。

Python/PostgreSQL 将 `study_attempt` 经 artifact、Run 连接到 `study_session`，严格按 owner/course/revision 过滤。只统计已发布成功的 practice 产物中的选择题。最新版本选择在判分筛选之前；计数与分页由同一 SQL 快照读取。查询不创建 Session/Run、判分、预算保留或长期记忆。

响应包含 `revision`、`correct_count`、`wrong_count`、`items` 和 `next_after`。每项包含 `session_id/run_id/artifact_id/question_index`、正向字段白名单的 `question`，以及已提交的公开 `attempt`（含 `attempt_id/version/selected_option_id/choice_result`）。题面不复制私有答案键；正确项仅来自该项已提交的 P9 判分结果。引用沿用保存时的权威 Evidence，定位沿用当前版本 Evidence guard；课程更新或删除后旧 revision 不进入列表。

## 身份与验证边界

当前开发身份为 `p10-choice-review-442bb2af75c77ed1`，由 `p10_agent_manifest.json` 登记 63 模块。原 P9 清单保持原字节，并新增 `verify_p9_agent`；P7、P3 和更早 FROZEN 清单不变。只读源码夹具恢复 P9 的 contracts/store，再沿原夹具链重建 P7/FROZEN；正例、篡改和冒充均有机制测试。登记不继承历史质量结论，也不允许真实 Provider 调用。

本阶段不提供掌握度、跨课程记忆、同 Session 自适应后续出题、开放题自动评分或真实模型内容质量结论。Tutor、闪卡、继续练习、P9 保存/判分/隐私语义保持独立。机制检查、变异和真实 loopback 浏览器验收入口见 [P10 本地验证](../eval/p10-review/README.md)；未执行的检查必须标记 NOT_RUN。
