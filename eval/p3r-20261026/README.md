# P3-R 修复与复核边界

修复基线：PR #45 `df01dd278791565852ead6cf6e89dba16e6c197f`；main 基线 `702b2f8dc030144cd5f8955ad0149dc8545dbffd`。原 P3 候选、两份独立审查所述发现及旧评测结果继续作为历史输入，不改写旧验收结论。本次仅处理桌面读取与状态同步，不产生新的模型质量成绩。

## 可重复回归

- `frontend/src/components/task-detail/P3Regression.test.ts` 挂载真实 CourseAgentPanel 及结果、作答、反馈子组件，覆盖 Tutor 引用刷新、执行中新旧反馈查看、重复打开核对记录、父子作答同步（无草稿/有草稿）以及历史并发与失败恢复。
- 四项原缺陷的五个场景在原组件源码上全部失败；修复后对应场景通过。另有反馈同记录迟到读取及取消后迟到轮询测试，不用仅发出事件的断言替代实际子组件显示。
- `CourseQaHistoryMySqlTest` 用独立真实 MySQL、实际 MyBatis mapper 和 JdbcTemplate，50条×8个不同来源：原服务观察400次Evidence读取，批量实现观察1次；同时验证游标、UTC Instant、跨用户、revision与软删除边界。单测另校验payload身份、旧revision、缺失、损坏与重复来源。
- `test_acceptance_cost.py` 在真实隔离PostgreSQL的完整机制套件内验证费用、恢复、取消和身份边界。没有数据库的跳过不计通过。

## 冻结身份

原56模块清单逐字恢复，固定摘要 `d94e896c768c0bf74c66b11f2105a1e541fe01f1c94ea1f14710d5c1a2777f00`。全部56源码可由原 `e34d8c596d74d4320ce6a224359190374520e4d3` 提交重建并匹配；测试中历史store fixture也来自原main。历史校验拒绝P3或混合模块集合。

P3另有57模块开发清单，独立身份 `p3-read-review-480fc58639fd4a59`，无质量成绩继承。开发入口只接受该身份及Fake模式；旧身份、真实Provider模式和非空费用授权字段仍拒绝。费用硬限未提高，未执行付费评测。详见[读取契约与身份](../../docs/DESKTOP_LEARNING_REVIEW.md)。

## 实际服务验收与证据

验收使用新建的 `lecturelens-p3r-desktop-20261026` 命名空间和新数据卷，服务共享独立无外网路由的loopback网络；不挂载生产数据、配置、凭据或Docker socket。应用库与测试库分别建立，真实Java/MySQL与Python/PostgreSQL使用合成数据、确定性Mock及离线embedding。

最终精确提交的实际服务结果、两种桌面视口（1440×900、1280×800）的截图、API/SQL、失败与成功日志、源码摘要及最新Push/PR CI记录存于本次独立交付目录，并由PR描述给出索引；原P3目录不覆盖。浏览器既覆盖正常B1学习旅程，也覆盖两标签页通过真实Vue表单保存作答和核对记录。原始记录可能含合成登录能力，仅公开脱敏汇总。

这些机制检查不证明真实模型教学质量。移动端、真实Provider、未见课程质量、自动评分、长期记忆与调度均不在本轮。

## 依赖审计限制

npm审计无告警。额外的完整Python锁文件审计报告7个既有包共53条漏洞告警（certifi、cryptography、filelock、langgraph-checkpoint-postgres、pillow、pyjwt、urllib3）。锁文件与原P3逐字相同；本轮未升级依赖，也未做这些告警的可达性评估。保留原始审计及失败状态，不能将其计作无漏洞通过；最终人工合并审查需处理这项既有风险。
