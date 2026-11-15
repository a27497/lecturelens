# ASR 403 诊断：只查不修

旧试次 task_bca24366edcd4e09b38f38b213817485 在2026-10-16 21:09:20（Asia/Shanghai）第70/71片收到HTTP403，响应长度178字符；第71片在途请求被失败清理中断，结果未知，并非已确认的第二次403。69片HTTP200，之前凭据可用。旧403正文及供应商Request ID未被保存。

`backend/src/main/java/com/example/courselingo/ai/llm/ObservedModelCall.java:33` 和 `backend/src/main/java/com/example/courselingo/ai/asr/AsrCallFailure.java:36` 将所有401/403归类AUTHENTICATION。这是本地粗分类，不能说明具体原因。ObservedModelCall.java:46仅对400保存脱敏私有正文，所以无法从旧记录恢复供应商错误码。BailianAsrProvider.java:66也只把状态码传给上层，没有保留正文。

本次使用同一现有部署引用的端点、模型qwen-audio-3.1-asr-flash和凭据，对仓库既有tone.wav发起且仅发起一次独立诊断请求，不启动worker，不写数据库，不重试，不计入新10+1。请求和响应摘要见 asr-diagnostic-intent.json、asr-diagnostic.json；响应原文仅本地.data私有文件（0600），Git中仅摘要和SHA256。

实际返回HTTP403，供应商错误码 **AccessDenied.Unpurchased**，响应178字符，含供应商Request ID。当前故障属于模型访问资格/服务开通权限拒绝；本次响应没有返回限流或内容审核错误码。官方错误码说明将AccessDenied.Unpurchased列为服务开通/使用资格问题；频率限制另有429错误码、内容审核通常为400 DataInspectionFailed。不能从Unpurchased进一步认定具体账户状态变化、余额或免费额度耗尽。

来源（2026-10-16查询）：[阿里云百炼错误码](https://help.aliyun.com/zh/model-studio/error-code)，403 AccessDenied.Unpurchased、429 Throttling、400 DataInspectionFailed条目。

同端点/模型/凭据、相同状态及长度，并且短音频同样被拒绝，支持旧试次遭遇同类访问资格故障的推断；**旧响应正文缺失，不能证明旧第70片的确切错误码就是Unpurchased**。精确历史归因仍需有权限的账户侧历史推理日志（若事前已开通）。

没有更换凭据、切换ASR模型/端点、购买/开通服务、充值、改变额度或权限。当前拒绝状态仍在，新的完整链路会受此阻碍；未以反复调用消耗新的10次验收试次。
