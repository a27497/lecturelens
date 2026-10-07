# 百炼同步 ASR

百炼实现既有 `SpeechToTextProvider`，用于确定性课程媒体准备。Task State、取消、恢复、重试预算和字幕持久化沿用原链路；它不证明 Study Agent 的模型任务质量。

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

激活 `asr-bailian` Spring profile 可选择百炼并使用推荐的 `180s / concurrency=2 / raw limit=7MB / chunk limit=6MB`。可通过 `ASR_CHUNK_DURATION`、`ASR_CHUNK_CONCURRENCY`、`ASR_MAX_AUDIO_FILE_SIZE`、`ASR_CHUNK_MAX_FILE_SIZE` 覆盖；其他 provider 的默认分片参数保持兼容。180 秒 16 kHz 单声道 PCM WAV 约 5.76 MB，需同时放宽原有 chunk 限制。

408、429、5xx、网络和超时可重试；其他 HTTP 错误及无效协议响应不可重试。异常不保留远端正文、凭据、音频 body 或不安全 cause。不要开启 HTTP wire/header 日志或请求体采集。

无凭据协议验证：在 `backend/` 运行 `mvn -q -Dtest='*Asr*Test,SpeechToTextProviderTest,TranscribeAudioStepTest' test`，随后运行 backend 回归。这些测试不证明真实云服务可用。

真实验收须上传无合格内嵌字幕的课程，并检查 `ai_call_record` 中 `provider=bailian、status=SUCCEEDED` 和 TRANSCRIBE 完成日志，再继续观察翻译与后续 Pipeline 终态。内嵌字幕成功不能替代真实 ASR 验收；完整课程处理成功也不代表人工识别质量、未见课程泛化或最佳长课吞吐已验证。
