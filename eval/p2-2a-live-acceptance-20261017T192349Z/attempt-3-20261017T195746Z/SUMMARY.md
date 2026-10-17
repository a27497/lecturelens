# P2-2a 尝试 3：课程准备成功，G1 请求受阻，未发布

task_id：`task_38372ad3617f4a91b6c1f864429b5966`。

**通过目标 0/5；G1 首次提交 BLOCKED，G2–G5 NOT_RUN。未达到默认开启发布门槛，保持“未发布”。** 上传预览和课程处理成功；G1 未生成解释、练习或反馈，后续引用跳秒、作答、双版本反馈绑定、刷新恢复均未执行。本次只是只读回填，没有重新提交处理/学习请求、修改配置、启动或重启服务。

## 历史与本次尝试

| 北京时间 | 尝试/事实 | 结果 |
| --- | --- | --- |
| 10-18 03:38:52 | 李毅斐确认完整观看，冻结窗口 v1 无修改 | 只确认事前窗口，不代表后续结果通过 |
| 03:39:47 落盘 | 尝试 1：首次 fileChooser.setFiles 缺少 ChatGPT 扩展文件 URL 权限 | 文件未选入、未建 task；原错误保留 |
| 03:48:03 落盘 | 尝试 2：获限定权限授权后，chrome://extensions 被浏览器工具 URL 策略阻止 | 未改权限、未第二次选择文件、未建 task；原错误保留 |
| 03:51:32 起 | 尝试 3：用户已说明手动开启权限；原窗口不变；素材哈希再次核对 | 此为继续流程第 3 次，实际 setFiles 为第 2 次；不是三次课程处理 |
| 03:51:55 / 03:51:58 | 选入素材 / 点击一次开始上传 | 后续网页显示 100%；精确完成时间未知 |
| 至 03:52:22 | 视频预览实际播放；日志暂停读数 6.924179 秒，duration 117.0169 秒 | 已审阅预览截图可见播放器 0:03/1:57；这不是引用跳秒测试 |
| 03:52:25 | 点击一次开始处理 | 新 task 建立，无处理重试 |
| 03:52:28.250–03:54:58.817 | MySQL 权威处理时间，SUCCEEDED / DONE | 耗时 150.567 秒；网页显示 00:02:30 是其秒级展示 |
| 03:55:01.525907 | PostgreSQL 索引更新为 READY | revision 2、sequence 43；MySQL 同步亦 READY |
| 03:55:42 | G1 原文首次点击“解释并出题” | 默认审批未勾选，未修改 |
| 03:55:44.161625 | PostgreSQL 创建 Study Session | Session 见下；未发现持久化 Run |
| 03:55:44.258528 | 同时间段 Agent command 日志出现 HTTP 422 | 日志无 task/请求关联字段与错误正文；不能单凭此断言具体拒绝原因 |
| 03:55:50 / 03:56:01 | 页面显示“学习助手暂不可用，请稍后重试” / 停止汇总 | 无解释、练习、反馈；未点重新连接、未重试、未改模型配置 |

已审阅 `07-upload-preview.png`、`24-g1-blocked.png` 及对应页面文本：预览有实际课程画面，G1 目标与清单原文一致，报错可见。图片含登录账号，仍留本机，不提交图片。人工日志的先前 NOT_RUN、两次阻塞与本次追加均保留；[上次回填](../SUMMARY.md) 也保持原样，不用此次处理成功覆盖首次失败。

完整自动日志另记：首次 AX 根节点滚动 detached 后重新观察再滚动；FILE_MANIFEST 自枚举文件占用后重新生成；尝试 3 初次 PowerShell 追加因中文引号解析失败后补记；旧 browser4 不可用后重新连接 browser5。这些是本机操作/记录恢复，不算额外产品处理或模型重试；原文保留在本地来源副本。

## 只读数据库结论

MySQL 容器 `lecturelens-demo-l2-mysql-1`（13306），实际 schema **courselingo**。使用容器既有非 root 应用身份，在 `START TRANSACTION READ ONLY` 内 SELECT。PostgreSQL 容器 `lecturelens-agent-postgres-1`，库 **lecturelens_agent**，使用既有应用身份，在 `BEGIN READ ONLY` 内 SELECT，读到 transaction_read_only=on。未读凭据文件，不输出密码，不做 DML/DDL/GRANT；没有连接旧 loop_test 做测试，也没有重跑任何迁移。

- `analysis_task`：SUCCEEDED / DONE、100%、revision 2、retry_count 0、error_code NULL、未删除。
- `course_evidence`：源字幕 8 条、译文 8 条，共 16 条；范围 0–112590 ms，全部 retrievable，owner 与该 task 一致。8 组源字幕时间与事前冻结 E1–E8 相同；新实例 Evidence ID 与旧设计实例不同，不套用旧 ID。
- `evidence_index_sync` 与 PostgreSQL `evidence_index`：均 READY、revision 2、sequence 43；派生索引 16 条。两端 evidence_id、start/end、content_hash、revision 逐条匹配 16/16；见 [EVIDENCE.csv](EVIDENCE.csv)。MySQL normalized_text 已只读核对，PostgreSQL 仅存内容哈希，不能将元数据匹配冒充模型引用文本/语义验收。
- `study_session`：1 行，session_id=`4b7782ab-b66b-5787-a990-1a09760357c3`，revision 2。
- 通过该课程 Session 关联查询：`study_run` 0 行、`study_event` 0 行、`study_tool_result` 0 行、`study_artifact` 0 行。这些 0 是实际 SELECT 结果，**不是**用未知值代填 0。
- 线上 public schema 没有 `study_attempt`、`study_feedback`、`study_feedback_note`、`study_model_call` 表；这些关联 ID、调用数/token/延迟不能查得，记未知。该事实不证明 HTTP 422 的具体原因；没有据此执行初始化、迁移或修复。

G1 请求时段 19:55:40–19:56:05 UTC 的 Agent 日志精选结果为 command HTTP 200、422、200；对应时间分别 19:55:44.165447、.258528、.370017。此时段没有选出数据库异常类型。HTTP 422 与 G1 提交、Session 创建时间吻合，可作为请求受阻的时间相关证据，但没有可关联的请求 ID、错误正文，**具体校验字段或配置原因仍未知**。当前工作树 Java `StudyTransport.java:79` 对未专门映射的非 200 响应会给出 STUDY_UNAVAILABLE；这只是与页面表现相容的源码路径，不是已证明运行二进制的精确根因。未读取模型配置或凭据，也未调用接口复现。

## 阶段、模型用量与成本

| 处理链记录 | 来源/模型 | 已记录时长 | prompt / completion / total tokens | 口径 |
| --- | --- | --- | --- | --- |
| TRANSCRIPTION | embedded-subtitle | duration_millis=200 | 未知 / 未知 / 未知 | ai_call_record 名为 ASR 类型，但 provider 及 8 条 subtitle_segment 均为内嵌字幕；不是外部 ASR 成功证据 |
| TRANSLATION | openai-compatible / deepseek-flash | 聚合 13,992 ms；provider_duration 13,794 ms | 2354 / 2003 / 4357 | 1 条聚合记录；8 条翻译诊断均 HTTP 200/PASSED、provider_attempt=1；诊断时长合计 13,758 ms，保留不同口径不强行对齐 |
| LEARNING_PACKAGE | openai-compatible / lecturelens-local-qwen | 63,345 ms | 1086 / 111 / 1197 | 1 条处理链聚合记录；底层 provider 调用次数未知，不能算作 G1 Study Run |

两条处理链 LLM 聚合记录合计 prompt 3440、completion 2114、total **5554 tokens**，与翻译诊断不重复相加。三个聚合记录均 SUCCEEDED；翻译诊断时间 19:52:31.227–19:52:43.087 UTC。表中 model 是记录名称，未验证供应商的底层真实模型身份。

`ai_call_record.started_at/finished_at` 集中在处理结束附近（19:54:58.745–.787），与 duration_millis 不同口径；当前源码 WriteAiCallRecordStep 会对积累记录调用 startCall/completeCall。因此保留两个字段，不把记录写入时间差伪装为模型耗时。task_log 只查到 QUEUED、EXTRACT_AUDIO、DONE 三条时间；其余阶段精确开始/结束与未覆盖的耗时为未知。页面曾显示“暂无模型调用记录”是处理中观察，不能覆盖现在查到的已落盘记录。

本次转录走 embedded-subtitle，**没有完成真实外部 ASR 验收**。原 ¥0.00325 只是给定费率下全长 ASR 条件估算，不是账单。查询的用量表无费用字段，未取得供应商账单，ASR、翻译、学习资料、G1 的实际金额均记“未知”，不填 0，也不根据模型名称猜价格。G1 无持久化 Run，不能把处理链 5554 tokens 算给 G1。

## 目标判定与发布门槛

| 目标 | 数据库/自动观察结论 | 用户人工判定 |
| --- | --- | --- |
| G1 | BLOCKED：首次提交报不可用；只有 Session，没有 Run 或学习产物；引用、反馈条件未成立 | 未判定 |
| G2–G4 | NOT_RUN：按 G1 阻塞停止；未提交后续目标、未作答/反馈 | 未判定 |
| G5 | NOT_RUN：未请求，不能算正确拒答 | 未判定 |

新版 MANUAL_LOG 共 43 行，pass_by_user 全空；[RESULTS.csv](RESULTS.csv) 分列 database_verdict/human_verdict，reviewer 与 review_mode 均为“模型辅助，待人工”。窗口确认人仍是李毅斐，但不扩展为任何目标的人工通过。当前数据库观察与页面受阻记录相容；没有人工判定可比较，不声称双方一致通过。

没有学习引用，所以尚不能判其 ID/文本/revision 权威一致性、冻结窗口语义、实际跳秒 ≤1 秒、每条建议支持引用；不能用 Evidence 准备成功代替。G4 双版本绑定、刷新恢复、G5 拒答，以及关闭新反馈后历史可读均未通过。既定 DESIGN 第 6 节门槛保持不变，**未发布**。未部署的本地提交及精确运行代码身份未知的限制仍保留。

本次回填在独立 attempt-3 子目录追加，不改原失败记录、冻结窗口、DESIGN、FREEZE 或线上代码。后续排查/修复须另行明确范围；本轮本地提交后停止，不 push。
