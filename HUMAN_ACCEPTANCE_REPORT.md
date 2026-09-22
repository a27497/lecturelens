# LectureLens 模拟真人黑盒验收报告

验收日期：2026-09-22（UTC）。浏览器交互约 06:31–06:52；随后核对、封存证据并停止本轮环境。

**结论：从新用户上传开始的 Recruiter 主链路完整跑通；当前 `/demo` 的 Sample Course 不能完整演示视频 Evidence。36 个验收 Case：27 PASS、9 FAIL。发现 0 Blocker、4 Major、5 Minor。当前不建议直接以现成 Sample Course 做无准备的求职 Demo。**

这是 Playwright 操作真实 Chromium 的模拟真人验收，不是独立真人盲评。没有直接调用 API、数据库、注入登录 token、替换响应或修改业务代码来代替操作；网络响应仅被动记录。故障注入只使用浏览器离线开关。问题出现后才只读查看源码和服务日志定位。

## 1. 冻结身份与实际环境

| 项目 | 实际值 |
| --- | --- |
| Git SHA | `f0c07a61261d143ef48ffc0b32ace37950eb793c` |
| 工作树 | 开始时干净；结束仅新增本报告，测试材料在被忽略的 `.data/` |
| Python 源码 SHA-256 | `85f7fd56959c837428384a7d7a6d7bbff5be75f39e1935cc480312698cd93bef` |
| 后端 JAR SHA-256 | `c6cef6e658e4d61a89e4de044b3e900c25c1dccf710724641b6eb6910aaae9d2` |
| 构建口径 | 使用现有 `backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar`（9月21日构建），未重新构建；Frontend 为当前源码 Vite，Agent 为当前源码 |
| 浏览器 | Chromium `153.0.8010.12`，Playwright `1.63.0`，headless 真浏览器 |
| 运行时 | Ubuntu Linux；Java 21.0.12、Node 24.18.1、Python 3.12.14 |
| 测试入口 | `http://127.0.0.1:5184/demo`、`/register`、`/upload`、`/tasks` |
| 隔离服务 | Java8084 / Agent8094 / Frontend5184 / Redis16381；按仓库 `serve.py` 启动 |
| 存储范围 | 既有隔离 MySQL `lecturelens_learning_loop`、独立 Agent PG、隔离 Redis/bucket/topic；不使用线上业务库 |
| Agent | real / qwen3-max；决策、复核为服务器默认；反馈启用；90秒 Run 预算 |
| 课程准备、翻译、普通 QA | `lecturelens-local-qwen`，既有本机8091服务；与 Agent qwen3-max 分开记录 |
| 视口 | 桌面1440×1000、移动390×844和320×740；移动结论为 Chromium 窄屏模拟，不代表真机Safari/软键盘验证 |

当前 Git 已包含 AU 后的 Trace/Recruiter Demo 等改动，**不是历史 AU 的相同源码指纹**；本轮结果不覆盖、重新计分或提升 AU 的质量结论。具体环境见 [environment.json](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/environment.json)。

输入为既有公开 MIT 6.0001 字符串片段 `strings.mp4`，时长约117秒，5,438,854 bytes，SHA-256 `912abfda246ad20d6f35b1c9ef4237bd0f8a68eac3fe871563584f735770f342`。只复用媒体，不把历史通过记录当作本轮成功证据；不是 fresh holdout 评测。

| 本轮对象 | ID / 用途 |
| --- | --- |
| 用户A、B | 均经 UI 新注册；后端 owner_id 57、58；凭据仅保存在私有证据目录 |
| A桌面课程 | `task_0c850bdd54784c829c8fcba13406bd39` |
| B桌面课程 | `task_e9766cbf34c549cbb420f5aed6f3c69c` |
| A / 390px上传课程 | `task_36b73e6d8b8a4f46a156e1ed95e1e9bf` |
| B / 320px上传课程 | `task_e76ec366bd844116b547e3685b9f718a` |
| 已有 Sample Course | `task_9530f04391b94c84b1ffc6a49228cecc`；仅新增本轮 Session/Run/合成作答，没有编辑旧 Run/Artifact |

## 2. Recruiter 主链路

| 步骤 | 本轮状态 | 关键证据 |
| --- | --- | --- |
| 1. 进入、注册、登录 | 健康 | [05-file-selected](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/05-file-selected.png) |
| 2. 上传课程 | 健康；5.2MB上传成功，可播放原视频 | [06-uploaded](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/06-uploaded.png) |
| 3. 处理课程 | 成功；A耗时4分53秒，之后需等待/刷新索引状态 | [46-own-course-ready](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/46-own-course-ready.png) |
| 4. Agent提问 | 成功；真实工具循环、解释和两道练习 | [59-main-agent-result](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/59-main-agent-result.png) |
| 5. 查看Evidence、跳视频 | 新上传课程成功；Sample Course失败 | [61-main-evidence-seek](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/61-main-evidence-seek.png) / [123-sample-missing-media-confirmed](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/123-sample-missing-media-confirmed.png) |
| 6. 多轮追问 | 同一Session成功；多条件 train→brain 也通过 | [80-followup-result](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/80-followup-result.png) / [92-multi-requirement-answers](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/92-multi-requirement-answers.png) |
| 7. History、恢复、Trace | 成功；作答版本与历史反馈可恢复 | [140-feedback-history-final](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/140-feedback-history-final.png) |

主 Session：`284563d4-5401-5eb4-9eb6-caa3f67d1fbe`。首轮 Run `f8b8de7f-8d52-4cbd-a3e6-33861e946cb1`；追问 `bd6decb1-e97f-468a-9fe3-05dd64c56ce6`；多条件 `9e29266e-1539-43a0-a315-167afef66689`。多条件任务经历一次草稿复核拒绝后修订，最终代码与参考答案符合要求。

## 3. Case 与 PASS / FAIL

PASS 只对应本行断言。鉴权正确和错误提示有缺陷分别记录；运输/持久化成功不自动代表所有教学内容正确。Case 可共享一份证据，Case 数不是模型题目数。

| Case | 场景 | 结果 | 实际观察 | 证据 |
| --- | --- | --- | --- | --- |
| R01 | 入口、创建新账号、登录 | **PASS** | A/B 均走注册与登录表单；无 token 注入。 | [05](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/05-file-selected.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-031a-bootstrap.zip) |
| R02 | 桌面上传课程并处理 | **PASS** | 117 秒 / 5.2 MB 的真实课程片段；A 4分53秒、B 5分03秒处理完成。 | [46](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/46-own-course-ready.png) |
| R03 | Agent 提问并生成学习产物 | **PASS** | 新课程生成解释、概念题和代码题；真实 qwen3-max 工具循环。 | [59](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/59-main-agent-result.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-031a-bootstrap.zip) |
| R04 | Evidence 原文与跳回视频 | **PASS** | 主课程可读引文、Evidence ID；跳转后播放器 readyState=4、currentTime≈19.05s。 | [61](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/61-main-evidence-seek.png) |
| R05 | 同 Session 多轮追问 | **PASS** | “接着刚才的第二题…”得到重新绑定解释与两题；Session ID 保持一致。 | [80](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/80-followup-result.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-031a-bootstrap.zip) |
| R06 | History、重新进入 Session | **PASS** | 可选择历史 Session/Run，恢复先前题目、作答和反馈。 | [140](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/140-feedback-history-final.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-046.zip) |
| R07 | 当前及历史 Trace | **PASS** | 展示 Run、模型、工具、事件及终态；刷新可恢复。 | [67](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/67-main-trace.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/Mobile390-037.zip) |
| R08 | 现成 Sample Course 的视频/Evidence 链路 | **FAIL** | 原视频与内嵌字幕 404，跳到视频无播放器可用。MAJ-01。 | [123](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/123-sample-missing-media-confirmed.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/DemoReadback-042.zip) |
| N01 | 重复上传同一文件 | **PASS** | 同账号重复上传成功；再次“开始处理”创建新的课程任务，原课程保留。 | [11](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/11-duplicate-upload.png) |
| N02 | 处理中刷新 | **PASS** | 任务、进度和视频恢复，没有新建任务。 | [12](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/12-processing-refresh.png) |
| N03 | 完成后刷新/关闭浏览器重登 | **PASS** | 恢复同一 Run、题目与已保存作答；参考答案仍需显式展开。 | [65](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/65-main-refresh-restored.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-031a-bootstrap.zip) |
| N04 | 课程外问题 | **PASS** | 独立 B trial 的 Kubernetes 请求输出中性证据不足，0 道题。另一个主动取消 trial 不算拒答成功。 | [138](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/138-refusal-history.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-046.zip) |
| N05 | 多要求问题 | **PASS** | 两句话解释、概念题+代码题、train→b+s[1:]、两次打印均保留；答案 train/brain；无循环或方法。 | [92](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/92-multi-requirement-answers.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-035.zip) |
| N06 | 作答→反馈→修改→再次反馈 | **PASS** | 新课程三版作答：正确 retain、错误 revise、修正 retain；历史和核对意见持久化。 | [143](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/143-feedback-review-persisted.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-047.zip) |
| N07 | Sample Course 首次反馈可靠完成 | **FAIL** | 独立首次反馈 RUN_BUDGET_EXCEEDED；保存的作答保留。MAJ-04。 | [141](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/141-demo-first-feedback-terminal.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/DemoReadback-047.zip) |
| N08 | 英文课程文本可读性 | **FAIL** | 原字幕换行处单词粘连，如 wordin、isthat、bindmy。MIN-01。 | [18](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/18-content-during-processing.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-043.zip) |
| N09 | 中文段落与原文时间对齐 | **FAIL** | 91.330–107.210 秒重新绑定原文被配成结尾提醒；QA 亦引用该错位中文。MAJ-02。 | [132](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/132-misaligned-subtitle-segment.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-044.zip) |
| N10 | 学习资料摘要/重点 | **FAIL** | A 摘要和重点复用空泛过渡句，漏掉变量重新绑定这一主要区别。MIN-05。 | [78](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/78-learning-materials.png) |
| A01 | 双击提交 | **PASS** | 两次独立 dblclick 测试，各仅观察到一条成功 START 和一个 Run。 | [112](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/112-doubleclick-active.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-039.zip) |
| A02 | 运行中 Cancel 后刷新 | **PASS** | 取消时已有模型调用；刷新及约4分钟后 History 均 cancelled，未发布产物。 | [137](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/137-cancelled-history-no-late.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-046.zip) |
| A03 | 浏览器 Back/Forward | **PASS** | 课程列表与详情往返，正在执行的同一 Run 可恢复。 | [86](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/86-back-to-active-run.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-032.zip) |
| A04 | 断网与恢复 | **PASS** | 真实 Chromium context 离线；恢复后同一 Run 成功，刷新保留结果，无再次 START。 | [131](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/131-offline-run-refresh-restored.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-043.zip) |
| A05 | 两个 Tab 并发提交 | **PASS** | 同一 Session 第一条 START=200，另一条=409 STUDY_CONFLICT / SESSION_BUSY；仅首个目标生成产物。 | [85](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/85-concurrent-submit-second.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-032.zip) |
| A06 | 并发冲突的用户提示 | **FAIL** | 409 被显示为“执行未能确认，可重试同一请求”，未说明另一标签页已有执行。MIN-04。 | [85](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/85-concurrent-submit-second.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-032.zip) |
| A07 | 两个 Tab 切换账号后的界面隔离 | **FAIL** | 旧 Tab 继续显示旧账号身份、课程和练习；新请求实际使用新账号凭据。MAJ-03。 | [95](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/95-old-a-tab-after-switch.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-035.zip) |
| P01 | A/B 双向访问他人 Course | **PASS** | 真实课程详情/results/playback 等请求返回404；没有返回他人课程数据。 | [13](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/13-b-foreign-course.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-045.zip) |
| P02 | A/B 双向访问他人 Session | **PASS** | 旧标签页使用他人 session_id 的 READ 被后端404拒绝；重开历史也被课程授权拒绝。 | [106](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/106-a-denied-b-session.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-038.zip) |
| P03 | A/B 双向访问他人 Run | **PASS** | 携带旧 Session/Run 的 READ、EVENTS 均404，Trace 不返回新数据。 | [105](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/105-a-denied-b-run-events.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-036.zip) |
| P04 | A/B 双向访问/写入他人 Artifact | **PASS** | ANSWERS 与含 artifact_id 的 SAVE_ATTEMPT 均404；未创建越权作答。 | [104](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/104-a-denied-b-artifact-write.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-036.zip) |
| P05 | 越权事件流正确拒绝并停止重试 | **FAIL** | Course events 实际500，前端反复重连；内容未泄露。MIN-02。 | [136](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/136-foreign-course-reconnect-loop.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-045.zip) |
| M01 | 390px 完整核心链路 | **PASS** | 上传→处理→出题→Evidence视频→保存→刷新→History/Trace；scrollWidth=390。 | [118](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/118-mobile390-viewport.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/Mobile390-037.zip) |
| M02 | 320px 完整核心链路 | **PASS** | 同上；独立课程，scrollWidth=320；控件可实际操作。 | [124](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/124-mobile320-answer-viewport.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/Mobile320-037.zip) |
| M03 | 代码题排版 | **FAIL** | 桌面和移动端直接显示 ```python 围栏，未渲染代码块。MIN-03。 | [124](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/124-mobile320-answer-viewport.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/Mobile320-042.zip) |
| X01 | 独立普通课程 QA | **PASS** | 提问返回“字符串是不可变的”及可点击证据；中文证据准确性另在 N09 判 FAIL。 | [127](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/127-standard-qa-after-network.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-042.zip) |
| X02 | 导出 Markdown / JSON | **PASS** | 通过可见下载按钮取得非空真实文件；JSON 同样保留字幕错位，排除仅前端显示问题。 | [79](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/79-downloads.png) / [Trace](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-044.zip) |
| X03 | 模型管理入口与默认路由 | **PASS** | 可见决策/复核均服务器默认 qwen3-max；未填写/更改任何模型密钥或路由。 | [83](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/83-model-management.png) |

## 4. 问题分类与复现

分级：Blocker 指没有可行替代路径、无法继续核心验收；Major 指关键演示功能、隐私界面隔离或证据正确性受损；Minor 指可继续使用但明确影响理解、呈现或错误处理。下列问题均保留首次记录，未实施修复。

### Major（4）

**MAJ-01：Sample Course 原视频缺失，Evidence 不能回到视频。**

复现：打开 `/demo` → 进入 Sample Course → 点击“刷新播放链接”；进入课程内练习的“查看课程证据”→“跳到视频”。结果：页面一直“未找到原视频文件”，playback-token 与 embedded-subtitles 均404，没有可用播放器；课程却标为“已完成”。新上传课程播放器正常，故更像当前演示数据/媒体状态问题，不能直接推断所有课程失效。只读定位到 [MediaPlaybackServiceImpl.java:66](/home/dev/projects/lecturelens/backend/src/main/java/com/example/courselingo/media/MediaPlaybackServiceImpl.java:66) 的课程→上传源检查及 `ensurePlayable`；未查数据库/对象存储，尚未区分缺失上传记录还是媒体对象。

证据：[123-sample-missing-media-confirmed](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/123-sample-missing-media-confirmed.png)；[DemoReadback-042](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/DemoReadback-042.zip)；[33-demo-evidence-seek-fail](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/33-demo-evidence-seek-fail.png)。

**MAJ-02：中文字幕内容错配原文段落，污染带时间的 Evidence。**

复现：打开 B桌面课程 → 课程内容 → 时间轴，查看 `#6`、`00:01:31–00:01:47`；再在“课程问答”问“为什么字符串不能通过索引赋值修改字符？”。英文讲将变量 s 绑定到新对象 yello、旧对象仍存在；同段中文却是下一段“再次，现在可能还什么意义都没有，但请记住这一点，字符串是不可变的”。普通QA将该中文作为对应时间的证据显示。JSON导出也有相同错配，排除仅UI错位。

定位：[SubtitleTranslationServiceImpl.java:580](/home/dev/projects/lecturelens/backend/src/main/java/com/example/courselingo/subtitle/service/SubtitleTranslationServiceImpl.java:580) 按模型返回的 segmentIndex 关联；[SubtitleTranslationServiceImpl.java:704](/home/dev/projects/lecturelens/backend/src/main/java/com/example/courselingo/subtitle/service/SubtitleTranslationServiceImpl.java:704) 主要验证语种/未翻译等，不证明逐段语义对应。已确认输出关联错误，未取得本轮翻译模型原始响应，不能断定是模型标签还是解析映射的唯一根因。此项是当前本机翻译配置的真实质量失败，不能借 Agent 原文回答正确抵消。

证据：[132-misaligned-subtitle-segment](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/132-misaligned-subtitle-segment.png)；[129-bilingual-timeline](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/129-bilingual-timeline.png)；[128-qa-citation-alignment](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/128-qa-citation-alignment.png)；`downloads/task-task_e9766cbf34c549cbb420f5aed6f3c69c-zh-CN-learning-package.json`（subtitles[6]）；[B-044](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-044.zip)。

**MAJ-03：另一 Tab 切换账号后，旧 Tab 不清除旧账号内容。**

复现：A在Tab1打开有练习的课程 → Tab2退出A并登录B → 回Tab1。Tab1仍显示A的邮箱、视频、完整练习/历史，可编辑其作答框；实际发出的请求已使用B身份并404。反方向同样复现。后端隔离有效，但同一浏览器交接账号后的旧页面残留私有内容，且身份展示与请求身份不一致。

定位：[auth.ts:19](/home/dev/projects/lecturelens/frontend/src/stores/auth.ts:19) 仅初始化读取本地状态，logout只更新当前Tab；源码未见跨Tab storage同步及课程状态清理。没有把缓存残留误报成后端越权读取。

证据：[94-account-switched-to-b](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/94-account-switched-to-b.png) → [95-old-a-tab-after-switch](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/95-old-a-tab-after-switch.png) → [96-b-denied-a-answers](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/96-b-denied-a-answers.png)；反向 [102-old-b-tab-after-switch](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/102-old-b-tab-after-switch.png)；[A-035](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-035.zip) / [B-036](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/B-036.zip)。

**MAJ-04：Sample Course 一次真实证据反馈预算耗尽，演示可靠性不足。**

本轮触发：在 Sample Course 新建目标“解释字符串不可变与变量重新绑定的区别，并给我一道概念题和一道代码输出题。” → 第一题填“因为字符串对象不可变，但变量可以重新绑定到另一个字符串对象。” → 保存 → 获取证据反馈。Run `8aa3c34a-d44b-4b00-822f-e1d87b1d646e` 最终 `budget_exceeded / RUN_BUDGET_EXCEEDED`，UI显示“本次未完成可靠反馈，可以重试”。本轮未重试这条失败，后续从History读取确认终态；失败作答仍保存。

定位边界：环境配置90秒Run预算，响应确认预算耗尽；仅凭本轮UI响应未能区分触发的是时间、token还是调用数上限，未确定外部模型调用耗时/复核路径的最终原因。它是单次真实执行失败，不能保证按步骤每次复现，也不能据1次样本推算总体失败率。新课程的三次反馈成功另列，不覆盖此失败。

证据：[141-demo-first-feedback-terminal](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/141-demo-first-feedback-terminal.png)；[DemoReadback-047](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/DemoReadback-047.zip)；`network-analysis.json` / `browser-events.jsonl` 的反馈 Run 与 READ.feedback_runs。

### Minor（5）

| ID | 问题、复现与影响 | 定位 / 证据 |
| --- | --- | --- |
| MIN-01 | 课程内容→原文/Evidence，出现 `wordin`、`isthat`、`bindmy`。输入视频字幕本来在两词间有换行；文本归一化丢掉分隔，影响阅读/检索。 | [AsrTextNormalizer.java:34](/home/dev/projects/lecturelens/backend/src/main/java/com/example/courselingo/ai/asr/AsrTextNormalizer.java:34) 删除ISO控制字符，换行在后续空白替换前被移除；[18-content-during-processing](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/18-content-during-processing.png) / 导出JSON。 |
| MIN-02 | 用A打开B课程或反向；详情404，但 `/events` 500并自动反复重连，页面混合“等待处理/处理已结束/不存在”。没有数据泄露。 | [TaskEventController.java:20](/home/dev/projects/lecturelens/backend/src/main/java/com/example/courselingo/task/controller/TaskEventController.java:20) + [TaskEventStreamServiceImpl.java:62](/home/dev/projects/lecturelens/backend/src/main/java/com/example/courselingo/task/events/TaskEventStreamServiceImpl.java:62)；后台 `HttpMediaTypeNotAcceptableException: No acceptable representation`，业务404在SSE异常序列化中变500。[136-foreign-course-reconnect-loop](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/136-foreign-course-reconnect-loop.png) / `backend.log:2644`。 |
| MIN-03 | 生成代码题后，桌面/390/320均直接展示Markdown围栏 ` ```python `；代码以普通题干文本呈现，影响Demo观感与阅读。 | [CourseAgentPanel.vue:226](/home/dev/projects/lecturelens/frontend/src/components/task-detail/CourseAgentPanel.vue:226) 字符串插值；[124-mobile320-answer-viewport](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/124-mobile320-answer-viewport.png)。 |
| MIN-04 | 两Tab先打开同一空闲Session，先后提交不同目标；第二个409仅提示“执行未能确认，可重试同一请求”。没有说明已有运行，易误导重复点击。 | 后端实际 `STUDY_CONFLICT / SESSION_BUSY`；[CourseAgentPanel.vue:122](/home/dev/projects/lecturelens/frontend/src/components/task-detail/CourseAgentPanel.vue:122) 走通用错误文案；[85-concurrent-submit-second](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/85-concurrent-submit-second.png) / [A-032](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/traces/A-032.zip)。 |
| MIN-05 | A课程→学习资料→摘要与重点，摘要和重点反复使用“把这句话放在心里/如果尝试这样做会给你一个错误/字符串不可变”，未概括变量重新绑定。此为可见内容质量问题，不是技术失败。 | [78-learning-materials](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/78-learning-materials.png)；[LearningPackageFallbackFactory.java:55](/home/dev/projects/lecturelens/backend/src/main/java/com/example/courselingo/learning/service/LearningPackageFallbackFactory.java:55) 有分布取句的fallback路径，与输出表现一致，但未以内部调用记录确认本次命中该路径。 |

## 5. 权限与真实后端拒绝证据

所有权限操作都由浏览器自身UI发出，没有构造API请求、手改资源ID、拦截改包或数据库查验。方法是两个独立新账号的正向访问，加上同浏览器第二Tab正常退出/登录后，在旧Tab点击历史、Trace、参考答案与保存作答。该方法既保留了真实UI状态，又让请求携带另一个账号的凭据。

| 资源 | B→A | A→B | 判断范围 |
| --- | --- | --- | --- |
| Course | 详情/results/playback 404 | 同左 | 未返回他人课程；SSE500单列MIN-02 |
| Session | READ携带A session_id →404 | READ携带B session_id →404 | 旧Session不能读取；History重开被授权拒绝 |
| Run | READ/EVENTS →404 | READ/EVENTS →404 | 无新Trace/Run数据 |
| Artifact | ANSWERS/SAVE_ATTEMPT →404 | 同左 | 参考答案拒绝，越权作答没有保存 |

原始请求中的Session/Run/Artifact ID、响应码和页面别名在 `browser-events.jsonl`；摘录见 `authorization-evidence.json`。**拒绝发生在真实课程授权边界。本轮没有“自有Course + 他人Run/Artifact”ID替换测试，因此不宣称已经完成所有独立IDOR排列或全面安全审计。** 已加载DOM残留另计MAJ-03。

## 6. 执行机制与模型质量分开看

- 本轮实际新增11个practice Run：9个成功终态、2个主动取消；两次取消都不是模型质量失败，也不算正确拒答。
- 新增4个feedback Run：3个成功、1个预算耗尽。所有 trial 保留。主课程三版反馈分别正确保留、纠错、再次保留；只证明这几份合成作答的本轮结果。
- 双击的两次场景各只有一个成功START；同Session双Tab竞争为一条200、一条409，没有第二份成功产物。
- 主课程解释、代码结果及多条件要求经本轮可见原文核查；课程外成功trial中性拒答、0题。字幕翻译错位仍是失败，不因Agent使用英文原文成功而豁免。
- 未运行单元/机制测试套件、未使用确定性Provider代替真实模型。没有把该样本验收换算为未见课程泛化、自动评分或统计可靠性。

完整Run身份与终态：`network-analysis.json`；对应操作脚本：`commands/`，每步实际输出：`results/`。

## 7. 证据、采集限制与收尾

证据根目录：`/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630`。

| 类型 | 路径 / 说明 |
| --- | --- |
| Case机器可读结果 | `cases.json` |
| 截图与可检索DOM | `screenshots/`、`dom/`；关键截图已打开核对，报告只引用对应真实状态 |
| 视频 | `videos/`（A/B/Demo/两种移动宽度及round2）；13个WebM均可被ffprobe读取 |
| Playwright Trace | `traces/*.zip`，以账号/宽度及命令号分段；`trace-validation.json`记录ZIP校验 |
| Console / 网络失败 | `browser-events.jsonl`，含console error/warning、pageerror、requestfailed及业务HTTP状态；`network-analysis.json`分类 |
| 权限原始证据摘要 | `authorization-evidence.json`，不包含Authorization头或登录凭据 |
| UI下载产物 | `downloads/`；均由下载按钮取得 |
| 定位日志 | `backend.log`、`agent.log`、`frontend.log`；只读用于说明现象，不作为代替UI的功能通过依据 |
| 原冻结证据完整性 | `frozen-evidence-before.json` / `frozen-evidence-verification.json`：25,046个既有eval文件无改变、无删除、无新增 |
| 环境停止记录 | `cleanup.json`；只停止本轮启动的8084/8094/5184与恢复Redis16381原先停止状态；线上8080/8090/8091仍监听 |

采集限制：第一段浏览器进程被终端时限结束，未成功导出该段Trace；截图、DOM、网络日志及WebM已保留。重启后全部通过正常登录恢复，没有token注入；后续采用分段Trace，重现了关键失败、并发/权限/取消/移动端/历史恢复。第一段上传过程的证据为视频、截图与网络日志，不冒充拥有完整Trace。

保留的采集脚本失败也没有算作产品失败：登录框需先聚焦、移动导航折叠、Evidence按钮全名带时间、短暂索引未就绪、历史面板折叠导致定位等待；一次命令文件写入竞争未执行，已改为原子投递并重新执行。`04-upload-empty` 是路由稳定前截图，`100-b-owned-artifact` 截错Tab，均未作为报告结论证据。

浏览器未捕获未处理JavaScript pageerror；HTTP404包含预期越权/缺失媒体，409包含准备阶段/并发冲突，离线和导航abort单独保留，不能把所有console红字都算成独立产品缺陷。

Trace、视频和配置可能含专用测试账号凭据或会话令牌，仅保存在被Git忽略、限制访问的`.data/`，不提交原始私有证据。新测试账号/课程/Run保留供复现；既有冻结证据文件未覆盖。**本轮止于测试、定位和记录；未修业务代码、未部署、未提交或推送。**

## 8. 关键截图

Sample Course 媒体缺失：

![Sample Course原视频缺失](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/123-sample-missing-media-confirmed.png)

同一时间片的英文与中文含义不对应：

![字幕错位的原始UI截图](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/132-misaligned-subtitle-segment.png)

320px核心操作可用，代码围栏仍作为文字显示：

![320px作答与代码显示](/home/dev/projects/lecturelens/.data/human-acceptance-20260922-0630/screenshots/124-mobile320-answer-viewport.png)

---

## 追加：4 个 Major 修复与定向回归（2026-09-22）

**修复后结论：MAJ-01～MAJ-04 的定向回归均 PASS；Recruiter 主链路完整跑通。** 上文原始 36 Case、27 PASS / 9 FAIL、首次失败截图与失败 Run 全部保留，不重计原验收成绩。本轮未重跑全部 36 Case，未处理 5 个 Minor，未新增产品功能。

### 候选身份与环境

- Git 基线：`f0c07a61261d143ef48ffc0b32ace37950eb793c`；本轮验证的是该 SHA 上的未提交修复工作树。具体文件 SHA-256、构建产物身份见 [environment.json](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/environment.json)。这不是重新冻结 AU，也不是新 holdout 评测。
- 真实 Chromium `153.0.8010.12` / Playwright，通过浏览器登录、上传、处理、提问、保存作答、反馈、Evidence、History 和下载；前端 `5184`、Java `8084`、Agent `8094`。Java 业务库仍为隔离的 `lecturelens_learning_loop`，浏览器使用的 Agent 数据库为 `lecturelens_agent_loop_test`。
- Agent 决策及复核仍使用真实 `qwen3-max`；课程处理与普通 QA 仍使用本机 `lecturelens-local-qwen`。没有切换为 mock 或修改线上模型配置。
- PostgreSQL 机制测试单独使用 `lecturelens_agent_test`。只读检查原失败 Run 和媒体记录用于定位；浏览器验收没有用 API/数据库写入代替用户操作。
- 新证据独立保存在 [.data/human-major-fixes-20260922](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922)。录像和 trace 含合成测试账号会话，仅留在忽略目录。

### 修复后 Case

| 原 Case / 范围 | 结果 | 实际执行与证据 |
| --- | --- | --- |
| A07 / MAJ-03：跨 Tab 账号切换 | **PASS** | 双向切换后旧账号身份、练习、课程和播放器清空；退出后稳定回到登录表单。新账号访问对方课程由真实后端拒绝，自有课程正常。[退出](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/41-logout-stable-login-screen.png)、[切换后](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/21-other-tab-new-account-no-old-content.png)、[反向切换](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/29-reverse-switch-no-main-content.png)、[拒绝对方课程](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/30-sample-account-denied-main-course.png)、[Trace](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/traces/A-012.zip)。 |
| N09 / MAJ-02：中文字幕时间对齐 | **PASS** | 新上传同一视频，8 段原文和毫秒时间戳完全不变。#4～#7 分别翻译自己的内容；#6 的 91.330–107.210 秒正确对应变量绑定到新对象，结尾提醒留在 #7。UI 与 JSON 一致。原 QA 问题也正确回答并引用对齐字幕。[#6 截图](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/14-segment6-detail.png)、[全时间轴](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/13-aligned-timeline.png)、[原 QA 问题](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/40-original-n09-question-result.png)、[导出对比](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/subtitle-alignment-comparison.json)、[Trace](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/traces/Main-017.zip)。 |
| N07 / MAJ-04：首次证据反馈 | **PASS** | Sample Course 使用原失败目标、同一第一题和同一作答；保存第 1 版后首次反馈成功，刷新仍恢复对应作答与反馈。Run `dc488910-10b2-4add-bee7-0e53dcb99a58`：4 次模型、2 次工具，15.74 秒，保留正确表述。[反馈及刷新](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/10-sample-feedback-reloaded.png)、[Trace](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/traces/A-004.zip)。 |
| R08 / MAJ-01：Sample Course 视频 Evidence | **PASS** | `/demo` → 进入 Sample Course → 原视频、内嵌字幕加载 → Agent 练习 → Evidence 跳视频 → 作答反馈与 Trace。视频时长 117.0169 秒、`readyState=4`、无媒体错误，点击引用后时间跳转成功。[视频恢复](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/02-sample-restored.png)、[Evidence 跳转](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/09-sample-evidence-seek.png)、[执行链路](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/16-sample-trace.png)。 |
| Recruiter 主链路 R01～R07 | **PASS** | 新账号进入 → 上传同一真实课程片段 → 处理完成（UI 3:07）→ Agent 首轮成功 → Evidence 视频跳转 → 同 Session 追问成功 → 刷新 → History 选择首轮并查看答案。新 Course `task_9fd4844108d74db79bad0167b864e763`。[上传](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/04-main-uploaded.png)、[首轮](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/25-main-agent-result.png)、[Evidence](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/26-main-evidence-seek.png)、[追问](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/32-main-followup-result.png)、[History 回读](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/34-main-history-original-run.png)、[Trace](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/traces/Main-014.zip)。 |

### 根因、修复边界和复现结论

**MAJ-03：存在真实的旧账号页面内容残留；未发现新账号通过后端授权读取旧账号数据。** Pinia 只在初始化时读取身份，但请求每次读取 localStorage；另一 Tab 切换账号后，两者不一致。已签发的旧视频链接也会继续留在页面，它是旧账号取得的播放能力，不能据此认定新账号获得了后端授权。

在 [authToken.ts](/home/dev/projects/lecturelens/frontend/src/api/authToken.ts) 建立文档级账号边界：监听 storage、页面恢复、焦点与可见性变化；请求、响应及凭据写入/清除之前再次检查，防止事件尚未处理时的竞态。身份变化后立即卸载页面并重新载入，统一丢弃课程缓存、播放器、流连接和旧异步工作；不清除新账号凭据。[http.ts](/home/dev/projects/lecturelens/frontend/src/api/http.ts) 丢弃旧响应并避免旧 401 清除新登录。登录、退出与已登录状态进入共享 Demo 都保留可用。

本项按 [codex-security:fix-finding](/home/dev/.codex/plugins/cache/openai-curated-remote/codex-security/0.1.24/skills/fix-finding/SKILL.md) 做了独立修复前调查和一次候选审查。审查发现的“旧 Tab 退出早于 storage 事件，误删新凭据”已在共享清除入口修正并加测试。没有放宽 Java/Python 任何授权条件。定向浏览器回归中双方 Course、results、playback-token、embedded-subtitles、study/status 均返回 404；自己的课程仍可读。原验收的 Session/Run/Artifact 拒绝证据继续保留；本轮未声称完成所有独立 IDOR 排列。

**MAJ-02：多段模型输出只保证结构完整，不能保证内容未跨段合并。** 原导出中 #4 中文包含 #5 的内容，后续译文向前错位，索引仍完整，语种检查无法发现。这支持“相邻内容合并后结构校验仍通过”的定位；原失败没有保存供应商原始响应，不将某一次模型输出或解析分支断言为唯一原因。

在 [SubtitleTranslationProperties.java](/home/dev/projects/lecturelens/backend/src/main/java/com/example/courselingo/subtitle/service/SubtitleTranslationProperties.java) 和应用/示例配置中，将默认批次改为一个来源时间段。每次请求只看到对应段落，避免把下一段内容借到当前时间；现有并发、分段重试、语言验证及原子保存继续工作。显式配置的多段批次兼容保留，**本次通过结论针对默认单段配置**。原已生成课程及冻结译文未回写；回归通过正常上传同一视频重新生成。个别不自然译词和英文粘连未扩展修复。

**MAJ-04：原失败耗尽的是墙钟时间，不是模型次数。** 持久化记录确认：模型 2 次、工具 1 次、预留 token 11,467；独立依据推导调用从 `06:37:34.838835Z` 开始后未完成，Run 于约 90 秒总期限终止。见 [原失败诊断](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/failed-feedback-diagnostic.json)。

[feedback.py](/home/dev/projects/lecturelens/agent-service/src/lecturelens_agent/study/feedback.py) 将单次供应商请求超时上限设为 20 秒（同时受剩余 Run 时间限制）；对瞬时 timeout/unavailable 最多重试一次。每次尝试仍经持久化预算扣减，保持 6 次模型、64,000 预留 token、总期限、取消、版本约束、checkpoint 和独立反馈复核。不重试内容错误或审查拒绝。真实反馈本次正常完成；原供应商长时间无响应路径由 PostgreSQL 针对性测试验证恢复，未对真实供应商人为注入长超时。持续供应商故障仍会如实失败，不保证任意故障下都生成反馈。

**MAJ-01：隔离数据库和媒体根目录不配套，原媒体没有丢失。** Sample 上传记录属于 owner 6，状态 STORED；原视频位于 `.data/interview-demo/tmp/chunks/6/up_2150d229f8084f85991374666f4c08fd/assembled/source.mp4`。冻结启动配置和上轮验收配置分别使用其他媒体根目录，所以课程完成记录存在而播放路径不存在。

将原视频按相同 owner/upload 目录结构复制到稳定的 `.data/recruiter-demo/media/chunks`，SHA-256 仍为 `912abfda246ad20d6f35b1c9ef4237bd0f8a68eac3fe871563584f735770f342`。恢复配置保存在私有 `.data/recruiter-demo/runtime.local.json`；没有修改数据库记录、课程 Evidence 或授权，没有伪造播放链接。[恢复记录](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/sample-media-restoration.json)。[README](/home/dev/projects/lecturelens/README.md) 已说明：启动原 `serve.py` 的三个组件时显式传入该 runtime；不能只复用数据库而换成空媒体目录。冻结启动脚本和原配置未覆盖。

### 验证命令与边界

| 验证 | 结果 |
| --- | --- |
| `git diff --check` | PASS |
| 前端 `npm run type-check`、`npm run build` | PASS；构建仍有依赖注释警告，无构建错误。 |
| `npm run test:unit -- src/api/authToken.test.ts src/api/authSessionHttp.test.ts src/views/RecruiterDemoView.test.ts src/api/study.test.ts src/components/task-detail/CourseAgentPanel.test.ts` | **24 PASS**；含 legacy token 键、storage clear、旧回调/401、旧退出/登录写入、正常 guest 登录和 Demo 切换。[日志](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/frontend-tests.log) |
| Java `./mvnw -q -Dtest=SubtitleTranslationServiceTest,SubtitleTranslationPropertiesTest,SubtitleTranslationPromptFactoryTest,SubtitleTranslationResponseParserTest test`；`./mvnw -q -DskipTests package` | **88 PASS，0 skipped**；新测试确认相邻来源不能进入同一个默认模型输入，并保持原索引关联。[结果](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/java-test-summary.json) |
| 独立 PG：`python -m pytest -q agent-service/tests/test_study_feedback.py agent-service/tests/test_study.py` | **80 PASS，0 skipped**；含超时后重试仍需独立复核、重复故障有界失败，以及原取消、预算、版本、checkpoint 与所有权检查。[日志](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/python-tests.log) |
| `python -m pytest -q agent-service/tests/test_study_provider.py -k timeout_preserves_run_deadline_classification` | **2 PASS，49 deselected**；仅运行相关超时分类测试。[日志](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/provider-timeout-tests.log) |
| 修改 Python 文件的 `ruff check` | PASS |
| Playwright / Chromium | 上述 4 个失败 Case + Recruiter 主链路 PASS；新产生 3 个 practice Run、1 个 feedback Run，均 succeeded。机制测试与真实模型结果分别报告。[网络与 Run 记录](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/network-analysis.json) |

保留的限制和非通过记录：

- 字幕核对中额外问“变量 s 重新绑定到 yello 后，原来的 hello 字符串对象是否被修改”时，普通 QA 返回“当前课程内容中没有找到明确依据”。该次不计作正确回答或正向引用验证，[截图](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/screenshots/38-qa-citations-result.png)。随后按原 N09 的准确问题执行，答案和引用均正常。本轮不据此宣称普通 QA 整体质量提升。
- 原 MIN-02 仍存在：打开对方课程时 events 返回 500 并重连；其他数据入口返回 404。未将该既有 Minor 偷改成 PASS，也未顺便修复。
- 浏览器录制中一次脚本在未填写目标时等待“解释并出题”变为可用而超时；填写目标后正常提交。原脚本错误与 trace 均保留，未把它当作应用故障或抹去。
- 本轮未重跑移动端、全部异常操作和原 36 Case，也未进行新的泛化/holdout 质量评测。

### Evidence 保留与停止

原 `eval/` 下 **25,046 个文件无改动、无新增或删除**：[校验](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/frozen-evidence-verification.json)。原验收 manifest 中 **568 个证据文件全部不变**：[校验](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/original-evidence-verification.json)。原 `8aa3c34a-d44b-4b00-822f-e1d87b1d646e` 仍保留 `budget_exceeded` 和原时间/计数：[校验](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/original-failed-run-preserved.json)。

截图、DOM、完整 browser console/network 记录、视频和 Playwright traces 都在本轮独立证据目录。封存数量与校验见 [final-verification.json](/home/dev/projects/lecturelens/.data/human-major-fixes-20260922/final-verification.json)。验证后停止本轮隔离服务，保留测试数据、恢复配置及媒体，不变更线上服务，不继续新增功能。


---

<a id="job-search-freeze"></a>

## 追加：求职版最终收口（2026-09-22）

**冻结范围：保留本轮 4 个 Major 修复，停止功能开发。当前验收范围内无 Blocker；5 个 Minor 保留，不重新标为通过。** Recruiter 主链路及 4 个失败 Case 的真实浏览器回归结果见上一节。本轮只审查、最终验证、整理提交和核对远端 CI，不新增或改变产品行为。

### 最终审查与提交边界

- 审查账号切换时的状态/请求边界、单段翻译默认配置、反馈超时与持久化预算，以及 Sample Course 媒体恢复配置；与报告、截图、Run 终态和网络记录一致，未发现新的阻断问题。
- 按现有 CI 要求对两个 Python 文件做格式整理；整理前后 AST 完全一致。其他已回归业务实现没有再改动，因此不重复执行全部 36 个浏览器 Case。
- 提交内容限于修复源码、测试、示例配置、README 和本报告。对候选文件进行了凭据模式、已知本机 secret 字面值、私有/生成路径、二进制与大小检查，未发现应排除的内容。此结论针对本次提交，不冒充全仓库历史安全扫描。
- 原始媒体、截图、video、trace、console/network 日志、测试账号及运行配置继续留在被忽略的 `.data/`。本报告中的绝对证据路径供原验收机器核验，**不会随 Git 提交发布，也不是 GitHub 上可公开下载的附件**；不能因为包含本地链接就认定原始私有 evidence 已发布。
- 原失败报告仍为逐字节前缀；原验收 manifest 的 568 个文件、修复 manifest 的 203 个文件，以及冻结 `eval/` 的 25,046 个文件校验不变。旧失败 Run 与原不通过记录均保留。

### 最终本地验证

| 项目 | 命令 / 范围 | 结果 |
| --- | --- | --- |
| Agent | 全量 `ruff check src tests`、`ruff format --check src tests`；全量 `pytest -q`，独立 PostgreSQL `lecturelens_agent_test` | **607 PASS，0 skipped**；lint/格式通过。 |
| Java | `./mvnw -B test` | **1,367 PASS，0 skipped**。 |
| Frontend | 全量 `npm run test:unit`、`npm audit`、`npm run build`（含 vue-tsc） | **93 PASS**；0 已知依赖漏洞；类型检查和构建通过。 |
| 提交差异 | `git diff --check`；文件范围、凭据、私有数据与大文件检查 | PASS。 |
| 既有真实模型/UI evidence | 核对 41 张截图、35 份 trace、3 段有效视频、4 个新 Run 的成功终态和对应报告 | 4 个 Major 定向回归与 Recruiter 主链路结论保持；0 未处理 pageerror。 |

合计 **2,067 个本地测试通过**。已知非失败告警为 Python 依赖弃用提示和前端依赖注释警告。普通 QA 曾对一条重新绑定问题拒答的观察仍保留，不将机制测试解释成模型全面可靠，也不提升历史 AU/holdout 结论。

最终验证日志及只读审计摘要保存在本机 `.data/job-search-freeze-20260922/`，不纳入 Git。远端结果以本次提交 SHA 对应的 [GitHub Actions CI](https://github.com/a27497/lecturelens/actions/workflows/ci.yml) 为准；最终交付消息记录实际 commit、push、CI 与工作区状态，不用旧基线的绿色 CI 代替本次验证。

### 仍保留的 5 个 Minor

| ID | 剩余问题 |
| --- | --- |
| MIN-01 | 原字幕换行归一化后英文单词粘连。 |
| MIN-02 | 越权课程的 SSE events 返回 500 并重连，错误页面状态混杂；数据入口仍拒绝访问。 |
| MIN-03 | 代码题直接展示 Markdown 围栏，未按代码块排版。 |
| MIN-04 | 两 Tab 同 Session 并发冲突提示过于笼统。 |
| MIN-05 | 部分学习资料摘要/重点质量偏弱，未充分概括重新绑定。 |

这些是保留的演示限制，不在本轮继续修复。求职冻结不等于公开发布：线上配置不变，本机 Sample Course 仍依赖已恢复且不提交的私有配置与媒体目录。
