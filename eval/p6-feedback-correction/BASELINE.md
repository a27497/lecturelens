# 基线与测量缺口

2026-10-26（服务器UTC）重新`git fetch origin`：main仍为`1b4dc696cc61e4f3828c6f0c6a7eaabab8dd451f`，与用户给定SHA一致，未前进。新worktree `/home/dev/projects/lecturelens-p6-validation`，分支`codex/p6-feedback-correction-validation`，直接从该main创建；未合入PR #47。原工作区保持`codex/p14-system-model-management`及原未提交文件。本轮只读参考`git show 5000180:eval/p5-desktop-learning/evidence/real-postgres-api-checks.json`等格式，不检出该分支，不继承其测试结论，也不修其3个P2。

**代码核对结论：** main的“作答→证据反馈→核对来源→新版作答”已经能持久化：按artifact/question递增的不可变attempt_id/version/answer_text/created_at；独立feedback Run/source_attempt_id及feedback_id/content；精确answer_version/answer_text；包含Evidence ID、原文与合成定位的citations及逐条observation/action；独立且不可变版本的核对disposition/note_text/created_at；新版作答不会改写旧反馈。owner/course/revision/session/run/artifact/question边界通过现有命令核验，课程事实权威仍是Java。缺少条件/随机分配、实际反馈暴露与来源点击、学生具体发现了什么、最终理由与来源映射、等待与阅读用时、评分和人类身份映射；无法仅凭acknowledged或v2内容推断发现错误。用研究sidecar补齐即可，不需要运行时改动。

代码依据：`study/attempts.py`保存版本与幂等冲突；`study/feedback_store.py`将反馈绑定精确attempt并维护核对历史；`study/store.py`提供READ/历史及读授权；`study/results.py`聚合结果；`study/feedback.py`以课程观察驱动受预算反馈图。反馈没有独立的可覆盖“反馈版本号”；每个不可变feedback_id和反馈Run是一次输出身份；note.version属于核对记录，不能当作反馈版本。两种条件只共享出题准备，B才有显式反馈Run。产品尚无研究实验或掌握率模块。

本轮实测：见`evidence/trial-05`及其`checks.json`。实际执行main的StudyRuntime、PostgresSaver、StudyStore、SAVE_ATTEMPT、START_FEEDBACK、SAVE_FEEDBACK_NOTE、READ、ATTEMPT_HISTORY、FEEDBACK_NOTES；确定性Provider与授权Evidence夹具使用本轮开发课程。6个脚本trial、12个不可变作答、5个反馈及5条核对记录；导出后旧反馈仍标v1，新版v2；重建Store、重复读取后Run/调用计数不变。此前`trial-01`缺显式final_evidence侧表；02–04分别验证侧表、来源绑定前的机制与绑定实现，均保留原始记录，不合并成实验样本量。

没有运行浏览器、Java网关、MySQL摄取、真实视频原文定位或真人流程：**BROWSER_NOT_RUN**。夹具来源READ证明读取契约与计数，不证明真实Java来源跳转、鉴权或1440×900/1280×800布局；这两尺寸仍是未来桌面验收范围。未见“阻止可信测量且必须改产品”的缺陷，因此只新增eval资产，不改Java/Python运行时/前端。

本轮参考并遵守根AGENTS、产品契约、L2质量/复核、L3、桌面回顾、feedback-v1、learning-loop和FINAL_AU；历史质量数字不当本轮证据。main缺`docs/LOCAL_CHECK_EXECUTION.md`与`scripts/dev/run_check.py`，只读原工作区已跟踪版本后使用其绝对路径包装新检查，输出显式指向新worktree：

- 指南SHA256：`738e7e694ed17c86182fc17ddcadca4e615cd261c15f320df3a1f3bce8f04537`
- 包装器SHA256：`4c9b291b34003f7d7bf9461c1e0ec76a2295de45b83808cb03fc45fd2a746f5a`

该包装器过滤Provider环境，只放行显式测试库等基础变量；没有读取部署env、生产凭据或个人模型配置。未使用YouLearn观察作为本轮证据。所有检查仅连接新compose项目`lecturelens-p6-validation-20261026`的loopback PostgreSQL 25486；未进入或操作历史容器。`lecturelens_p6_test`存演练，`lecturelens_agent_test`供既有回归，均在本轮新volume；第一次错误命名的`lecturelens_p6_regression_test`也仅在该新实例内。
