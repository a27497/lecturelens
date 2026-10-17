# DeepSeek 真实接入与回滚验收

本轮按用户授权完成少量真实调用。Java 仍为 `13f8fc03d61d608157be1b7c3c0b5d474536acfd`，没有修改应用代码、push 或重新部署。JSON 探测、全文翻译独立绑定、真实小节任务、执行中回滚及回滚后新任务均通过。最终配置版本 **9**，所有功能绑定恢复为空，供应商和模型保留供用户继续使用。

结果时间采用 UTC 原始记录；目录日期为 2026-10-16（Asia/Shanghai）。结构化汇总见 `results.json`，脱敏证据清单见 `SHA256SUMS`，私有原始文件清单见 `RAW_SHA256SUMS`。

## 真实调用与结果

| 检查 | 实测 | 证据 |
| --- | --- | --- |
| JSON 连通性 | OK，663 ms，保存模型 `deepseek-flash`，最终地址 `https://api.deepseek.com/chat/completions` | `json-probe.json` |
| JSON 输出要求 | 管理探测使用已部署的严格 JSON 对象校验与 `response_format: {type: json_object}`；通过后仅返回类别、耗时、版本及最终地址，不保留供应商正文 | 运行代码固定为上述提交；探测 API 与源码说明见上级系统管理 VERIFY.md |
| 独立绑定 | 仅 `TRANSLATION_FULL_TEXT` 绑定模型 1；其他六个已接通功能的路由逐项一致 | `baseline-catalog.json`、三个 bound catalog、`immutable-content-digests.json` |
| 任务 A | `task_70ec3dd6189843979174ed6d32d1237f`，SUCCEEDED；全文翻译为 DeepSeek，学习资料为本机 Qwen | `live-task-a-status.json`、`task-a-results.json` |
| 任务 B | `task_95c8e25dc07944cd82f20d567745738f`，SUCCEEDED；全文翻译和学习资料均为本机 Qwen | `live-task-b-status.json`、`task-b-results.json` |
| A/B 输入一致 | 同一上传文件、同一目标语言 zh-CN；源全文 1,061 字符，SHA256 相同 | `media.json`、两个 task results |
| 快照 | A 冻结版本 6，回滚前后及任务结束查询内容一致；B 在最终回滚后冻结版本 9 | `live-task-*-snapshot-*.json`、`database-execution-snapshots.json` |
| 执行中回滚 | A 正处于 TRANSLATE_SUBTITLES 时完成版本 9 回滚；随后创建 B | `hot-timeline.json`、`task-a-running-before-final-rollback.json`、`final-audit.json` |
| ASR | 两项成功任务均为 embedded-subtitle，真实 ASR 请求为 0 | 两个 task results 的调用记录；`subtitle-precheck.json` |
| 最终状态 | 配置版本 9，绑定为空，所有有效路由与版本 3 的初始状态一致，无未完成分析任务 | `final-catalog.json`、`final-status.json`、`results.json` |

DeepSeek 全文翻译调用记录：6 批，重试 0，输入 1,737 tokens、输出 2,719 tokens，合计 **4,456 tokens**。另有 **1 次 JSON 探测**；探测 API 不暴露 token 用量，因此没有把探测用量记成零，也没有估算总账单。费用以供应商账单为准。没有追加其他 DeepSeek、ASR 或视觉调用。

A 全文译文 395 字符，其中汉字 295；B 为 333 字符，其中汉字 252。两个任务均有 6 个字幕段、6 个翻译段和学习资料。A 翻译阶段 17,055 ms，B 为 184,876 ms；两者共享本机工作负载且模型不同，**这些数字不是性能基准或质量评分**。抽查 A 的坐标、方程和交点表述与源文一致；这是已见公开课程的一次配置/协议与任务冒烟验收，不是独立留出评测或 Study Agent 能力评测。

## 配置与热生效时间线

| 版本 | 动作与观察 |
| --- | --- |
| 3 | 用户已保存 DeepSeek 供应商、密钥和模型，无功能绑定；探测通过 |
| 4 → 5 | 首次只绑定全文翻译，再回滚。两个任务被 RocketMQ 磁盘保护挡住，最终 MQ_DELIVERY_EXHAUSTED；保留失败记录 |
| 6 → 7 | 创建后来成功的 A，冻结版本 6。20 秒内仍排队，启动检查未通过，立即回滚至版本 7；没有删除或重建 A 的快照 |
| 8 → 9 | 经用户批准重启 broker 后，原 A 自动恢复。在 A 正在全文翻译时，再次只绑定同一功能并回滚至初始版本 3 的空绑定，生成版本 9；创建 B，冻结版本 9 |

精确时间：

```text
18:06:23.825Z  A 开始全文翻译（冻结版本 6）
18:06:29.793Z  保存全文翻译绑定，生成版本 8
18:06:29.930Z  回滚全文翻译到版本 3 的绑定，生成版本 9
18:06:40.907Z  A 全文翻译完成，实际模型仍为 deepseek-flash
```

B 的创建时间晚于回滚时间，详见 `hot-timeline.json`。版本 3–9 的 providers、models、defaults 三个完整存储块分别在数据库内计算 SHA256，跨全部版本完全一致；其中含加密凭据的块没有被取出或保存。此检查补充了 API 掩码路由比对，证明其他功能的地址、模型、参数与凭据存储未被改动。逐段翻译仍使用 ENV 且当前模式未激活；视觉维持原部署关闭/缺少密钥状态；FUSION_SUMMARY 仍未接通。本轮没有切换这些功能或把静态配置一致当作它们的真实质量测试。

## 原始失败与消息队列恢复

初始失败任务：

- `task_af2961a5253a4e8dbcb811a3efcbcede`
- `task_fb81356012b143bd9b986fe0dae24c7c`

二者均为 FAILED / MQ_DELIVERY_EXHAUSTED，未进入课程处理；最终成功没有替换或抹除这些失败。`attempt-01-task-*-status.json` 和 `task-events-final.json` 保留原记录。另有两个驱动检查记录：本地 VTT 时间格式解析最初只接受 HH:MM:SS，改为也接受 MM:SS 后通过；第二次启动检查在 20 秒内未等到消息投递，随后同一个 A 经 broker 恢复才开始执行。分别见 `driver-attempt-01.json`、`trial-02-start-checkpoint.json`，不计为模型失败或成功输出。

RocketMQ 5.3.4 在磁盘约 92% 时触发保护，警戒阈值为 90%，自动恢复阈值为 85%。回收了未引用的旧构建镜像、构建/下载缓存和一份与部署 JAR 哈希一致的重复 Maven 构建 JAR；没有删除业务卷、课程媒体、私有验收记录或部署/回滚产物。最后一份可重建 JAR 的删除凭据见 `reproducible-artifact-cache-removed.json`，实际部署文件仍保留原位置。

曾尝试把恢复阈值临时设置为 90，再立即还原为 85；检查现有安装包字节码后确认内部把它硬限制为最高 85，因此该尝试无效，未宣称恢复成功。原字节码与命令日志留在私有目录，参数还原记录为 `broker-recovery-*.json`。

随后用户明确批准仅重启 `lecturelens-demo-l2-rocketmq-broker-1`。重启前无 RUNNING 分析任务，重启后镜像相同、数据保留、保护参数仍为 85/90，Java、agent-service、llama 的 PID 和启动时间完全不变。原 outbox 自动投递 A，之后 A/B 均正常完成。见 `broker-restart-*.json`、`broker-final-protection.json` 和 `other-services-*.json`。

**剩余运维限制：** 收尾时磁盘占用约 89.96%，可用约 15.53 GB，仍紧邻 90% 警戒线。需要在继续上传较大课程前规划释放空间或扩容；这次恢复没有解决长期容量问题，也没有调高警戒阈值。

## 来源与脱敏边界

使用本地已保存的 MIT OpenCourseWare 18.06 线性代数第 1 讲，Gilbert Strang，420–510 秒片段，实际时长 90.023267 秒。来源、原视频/片段/字幕 SHA256 及私有文件路径见 `media.json`。许可为 **CC BY-NC-SA 4.0**，用于非商业工程验收，保留 MIT OCW 署名与相同方式共享要求；MIT 未背书本项目。授权背景及原字幕来源见 `eval/baseline-asr-20261015/SOURCES.md`。不重新发布视频或第三方插图。

原视频页：https://ocw.mit.edu/courses/18-06-linear-algebra-spring-2010/resources/lecture-1-the-geometry-of-linear-equations/

驱动从未读取、接收或保存 DeepSeek API Key；只把保存模型 ID 交给后台，由后台按不可变版本解密。短时本机验证 JWT 只在进程内使用，不保存请求头、令牌、数据库密码、主密钥、供应商原始响应或签名媒体 URL。

公开 JSON 使用管理接口的专用投影，keyLast4 进一步替换为 `****`；只保留 hasKey 和掩码。数据库查询只返回配置块的摘要或快照无凭据检查结果，没有返回版本 JSON/密文。Java 日志只保存指定字段的事件投影；原日志在内存中扫描后未复制，未发现 API Key 前缀或 Bearer 请求头。译文和媒体仅在 Git 忽略的私有目录，公开只保留长度、摘要与调用统计。

私有原始目录：

```text
/home/dev/projects/lecturelens/.data/system-model-management/deepseek-20261016/
```

其中包含片段、字幕、A/B 脱敏结果正文、固定驱动、进度、缓存回收日志和 RocketMQ 字节码观察。失败驱动原件也保留。公开 SHA256SUMS 覆盖本目录证据，RAW_SHA256SUMS 对应私有原件；字节码缓存不纳入封存。

## 复现命令

以下为**离线证据复算**，不发起收费请求、不写数据库、不重启服务：

```bash
cd /home/dev/projects/lecturelens
python3 eval/system-model-management/deepseek-20261016/verify.py
sha256sum -c eval/system-model-management/deepseek-20261016/SHA256SUMS
sha256sum -c eval/system-model-management/deepseek-20261016/RAW_SHA256SUMS
python3 eval/system-model-management/verify.py
```

verify.py 逐项复算任务状态、源/译文长度与摘要、6/9 快照、回滚时序、其他路由及存储块一致性、6 批/0 重试/4,456 tokens、ASR 来源、失败记录和进程未重启证据。媒体元数据命令为 `ffprobe -v error -show_format -show_streams -of json <media.json 中的 clip_private_path>`；源片段生成命令保留在私有驱动中。完整原始记录位置和每个文件摘要都在两个清单内。

不把上述命令改成自动重放真实调用；重新做付费验收需再次明确授权和冻结新的记录目录。本轮未改变应用代码，因此没有重跑整套 Java/前端/Python 测试；原四阶段测试证据由上级 verify.py 重新校验，实际供应商接入证据与确定性机制测试分别报告。
