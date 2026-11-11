# 百炼同步 ASR

百炼实现既有 `SpeechToTextProvider`，用于确定性课程媒体准备。Task State、取消、恢复、重试预算和字幕持久化沿用原链路；它不证明 Study Agent 的模型任务质量。

启用[系统模型管理](SYSTEM_MODEL_MANAGEMENT.md)后，可把 `ASR_TRANSCRIPTION` 绑定到 BAILIAN_ASR 模型，`baseUrl` 使用下表的完整同步 HTTPS 端点。每个任务冻结供应商、模型、凭据版本及非密钥选项，后续更改绑定只影响新任务；全部分片与重试保持原快照。没有绑定时仍按原 provider/enabled/Mock 规则选择；数据库绑定出错不会回退 Mock。分片大小与时长继续受部署参数约束，切换到 SiliconFlow 时也需要满足其输入上限。

显式 `ASR_PROVIDER=bailian|siliconflow|mock|none` 优先于旧 `*_ENABLED` 开关。未指定时保留单一旧开关兼容；多个启用开关冲突会拒绝启动，不自动降级到 Mock。

| 环境变量 | 默认 / 含义 |
| --- | --- |
| `ASR_PROVIDER` | 无默认选择；百炼运行显式设置 `bailian` |
| `BAILIAN_ASR_API_KEY` | 无默认值；通过运行环境或既有安全凭据机制注入 |
| `BAILIAN_ASR_MODEL` | `qwen-audio-3.1-asr-flash` |
| `BAILIAN_ASR_ENDPOINT` | `https://dashscope.aliyuncs.com/api/v1/services/aigc/multimodal-generation/generation`；可使用匹配凭据地域的 workspace 专属完整 HTTPS 地址 |
| `BAILIAN_ASR_CONNECT_TIMEOUT` / `BAILIAN_ASR_REQUEST_TIMEOUT` | `5s` / `180s` |
| `BAILIAN_ASR_MAX_AUDIO_FILE_SIZE` | `7MB`，另受 Base64 大小限制 |
| `BAILIAN_ASR_LANGUAGE_HINT_ENABLED` | `false`；开启后映射课程语言为支持的语言代码 |
| `BAILIAN_ASR_CONTEXT` | 空；可选 user `input_text`，最多 400 Unicode 字符 |

同步 JSON POST 使用 WAV Base64 Data URI，关闭 SSE，不创建公网音频 URL。拒绝单片达到 300 秒或编码后超过 10,000,000 字节的输入；不接受 filetrans 或 OpenAI-compatible endpoint。优先解析累计 `output.text`，兼容 `output.output.sentence.text` 和 `output.sentence.text`。协议字段缺失或无效时失败。

激活 `asr-bailian` Spring profile 可选择百炼并使用推荐的 `180s / concurrency=4 / raw limit=7MB / chunk limit=6MB`。可通过 `ASR_CHUNK_DURATION`、`ASR_CHUNK_CONCURRENCY`、`ASR_MAX_AUDIO_FILE_SIZE`、`ASR_CHUNK_MAX_FILE_SIZE` 覆盖；`ASR_CHUNK_MAX_CONCURRENCY` 仍将有效并发钳制在 4。其他 provider 的默认分片参数保持兼容。180 秒 16 kHz 单声道 PCM WAV 约 5.76 MB，需同时放宽原有 chunk 限制。

408、429、5xx、网络和超时可重试；其他 HTTP 错误及无效协议响应不可重试。异常不保留远端正文、凭据、音频 body 或不安全 cause。不要开启 HTTP wire/header 日志或请求体采集。

无凭据协议验证：在 `backend/` 运行 `mvn -q -Dtest='*Asr*Test,SpeechToTextProviderTest,TranscribeAudioStepTest' test`，随后运行 backend 回归。这些测试不证明真实云服务可用。

真实验收须上传无合格内嵌字幕的课程，并检查 `ai_call_record` 中 `provider=bailian、status=SUCCEEDED` 和 TRANSCRIBE 完成日志，再继续观察翻译与后续 Pipeline 终态。内嵌字幕成功不能替代真实 ASR 验收；完整课程处理成功也不代表人工识别质量、未见课程泛化或最佳长课吞吐已验证。

## 可选持久化调度（实验实现）

`PIPELINE_ASR_ADAPTIVE_ENABLED=false` 仍为默认。启用需同时具备静音切分和 v2 checkpoint；新任务冻结 ASR 初始/最大窗口、成功阈值、速率、冷却、合并和缓存参数，旧任务不随配置变化。为把转写峰值并发从 2 提到供应商安全上限，`ASR_CHUNK_CONCURRENCY` 与 ASR 最大并发默认均为 4；自适应窗口仍从初始并发 2 起步，连续成功后再升到 4，连续成功阈值 3；429 将窗口减半，冷却期及分片尝试次数持久化，恢复不重置。分片路径上的 `ASR_CHUNK_CONCURRENCY` 默认值同步为 4，并仍受最大 4 的硬上限约束。不把峰值提高到 8：目录未给出同步模型的并发额度，既有代码硬上限与设计验收都以 4 为可实施上限。相同非敏感供应商/模型身份共享进程名额与平滑速率；这不保证主账号其他进程的总用量。默认 10 requests/s 来自[限流目录](https://help.aliyun.com/zh/model-studio/rate-limit)对 `qwen-audio-3.1-asr-flash` 的 600 RPM 换算（2026-11-11 复核仍为 600 RPM），账户实际配额未测。

百炼 HTTP 超时取供应商配置与单次请求剩余期限的较小值；429 保留安全的 Retry-After 时长，超过 30 秒的重试等待上限则结束试次，不提前重发。401/403 不重试或自动换供应商。真实试次仍遇 403 时按验收约束停止后续派发。

合并由 `PIPELINE_ASR_MERGE_ENABLED=true` 默认打开，缓存仍由 `PIPELINE_ASR_CACHE_ENABLED=false` 默认关闭。合并已从自适应调度中拆出：只要翻译 v2 与静音切分开启，新任务就会把 60/90/120 秒合并参数冻结进策略，不必打开 `PIPELINE_ASR_ADAPTIVE_ENABLED`。`PIPELINE_TRANSLATION_V2_ENABLED` 仍默认关闭。合并把相邻短片拼到目标约 90 秒，保留夹入静音的原时轴和所有旧子区间；文件限制和尾片例外有原因标注。固定时长分片路径（例如百炼推荐的 180 秒片）已达到或超过合并上限，不会再合并，只享受并发 4。单片转写失败仍会使整步失败，不会留下部分成功字幕。缓存使用同所有者命名空间中的音频 SHA256 和冻结 ASR 配置身份，只保存成功结果，按原始任务删除状态、TTL、容量和当前执行围栏校验。测速必须关闭缓存读写；同任务 checkpoint 复用与跨任务缓存命中分开记录。`PIPELINE_EARLY_LEARNING_ENABLED` 保持默认关闭，与本次转写提速无关。

WAV 抽取显式使用 PCM s16le，现有默认采样率/声道已是 16000/1；新增抽取耗时、输入/输出 bytes 指标，不能预先宣称文件缩小或提速。真实课程、CER、并发 8、恢复与缓存演示的状态见[本轮验证](../eval/p2-1c-20261016T155847Z/VERIFY.md)。
