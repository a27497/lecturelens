# P2-1b 独立真实验收

正常完整链路 **0/10**；翻译发布 10/10。独立恢复任务另列，不计入正常均值。正常端到端耗时 **213.832 ± 44.533 (n=10) 秒**。

原候选 P2-1 的 1 次 MQ 协议失败保留在独立目录，不并入此候选。P2-1b 仅修复 transport payload 的 v2/epoch 字段；系统 v10 与策略 v2.5 保持原路由和预算。

**恢复演示未完成**：第11个任务在 ASR 第70/71片收到403/AUTHENTICATION，另一在途请求网络结果未知；未进入翻译、SIGKILL为0次。没有将失败改成恢复成功，没有追加试次或供应商探测。403仅保存响应长度178，正文未采集，不能判断密钥、权限或余额等具体原因。

耗时为秒，均值±样本标准差（ddof=1）；未到达阶段为 NA，成功与失败阶段分开。失败终态耗时不等价于成功完成速度。

| 阶段 | 完成样本 | 失败样本 |
| --- | --- | --- |
| ANALYZE_KEYFRAMES | 0.003 ± 0.001 (n=10) | NA (n=0) |
| EXTRACT_AUDIO | 9.439 ± 1.543 (n=10) | NA (n=0) |
| EXTRACT_KEYFRAMES | 0.003 ± 0.001 (n=10) | NA (n=0) |
| FUSE_VIDEO_SEGMENTS | 0.003 ± 0.001 (n=10) | NA (n=0) |
| GENERATE_LEARNING_PACKAGE | NA (n=0) | 0.112 ± 0.050 (n=10) |
| OCR_KEYFRAMES | 0.004 ± 0.001 (n=10) | NA (n=0) |
| PERSIST_SUBTITLES | 0.184 ± 0.091 (n=10) | NA (n=0) |
| RESOLVE_UPLOADED_SOURCE | 0.190 ± 0.237 (n=10) | NA (n=0) |
| TRANSCRIBE | 172.145 ± 41.116 (n=10) | NA (n=0) |
| TRANSLATE_SUBTITLES | 29.428 ± 7.308 (n=10) | NA (n=0) |
| VALIDATE_TASK | 0.004 ± 0.002 (n=10) | NA (n=0) |

正常试次调用与调度汇总：884 次 ASR，527 次翻译；2 个出网前拆分父节点（父批 attempt_count=0），4 个子批，0 次物理重试。ASR HTTP 账本区间并发峰值 2；翻译窗口/在途峰值 4/4，原始有序曲线在各 task 的 scheduler 记录。


| 课程/次 | 终态 | 翻译秒 | ASR CNY | 翻译 USD | ASR/翻译物理调用 | 初始批/拆分节点/重试预留 | 窗口/在途峰值 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| algorithms/1 | FAILED | 27.752 | UNPRICED；目录价参考 0.059673 | 0.007631 | 108/55 | 55/0/0 | 4/4 |
| algorithms/2 | FAILED | 29.889 | UNPRICED；目录价参考 0.059663 | 0.006554 | 108/55 | 55/0/0 | 4/4 |
| calculus/1 | FAILED | 23.419 | UNPRICED；目录价参考 0.043115 | 0.005589 | 79/38 | 38/0/0 | 4/4 |
| calculus/2 | FAILED | 22.322 | UNPRICED；目录价参考 0.043202 | 0.004990 | 79/38 | 38/0/0 | 4/4 |
| economics/1 | FAILED | 28.945 | UNPRICED；目录价参考 0.043578 | 0.006995 | 71/60 | 59/1/0 | 4/4 |
| economics/2 | FAILED | 28.379 | UNPRICED；目录价参考 0.043634 | 0.006225 | 71/60 | 59/1/0 | 4/4 |
| linear/1 | FAILED | 23.682 | UNPRICED；目录价参考 0.044531 | 0.005817 | 81/39 | 39/0/0 | 4/4 |
| linear/2 | FAILED | 25.371 | UNPRICED；目录价参考 0.044528 | 0.005310 | 81/40 | 40/0/0 | 4/4 |
| probability/1 | FAILED | 44.604 | UNPRICED；目录价参考 0.060147 | 0.007287 | 103/71 | 71/0/0 | 4/4 |
| probability/2 | FAILED | 39.913 | UNPRICED；目录价参考 0.060163 | 0.007061 | 103/71 | 71/0/0 | 4/4 |

| 每课两次汇总 | 翻译秒 | ASR 目录价参考 CNY | 翻译已知下界 USD | 翻译已知上界 USD |
| --- | --- | --- | --- | --- |
| algorithms | 28.820 ± 1.511 (n=2) | 0.059668 ± 0.000008 (n=2) | 0.007093 ± 0.000761 (n=2) | 0.007093 ± 0.000761 (n=2) |
| calculus | 22.870 ± 0.776 (n=2) | 0.043158 ± 0.000061 (n=2) | 0.005289 ± 0.000423 (n=2) | 0.005289 ± 0.000423 (n=2) |
| economics | 28.662 ± 0.400 (n=2) | 0.043606 ± 0.000040 (n=2) | 0.006610 ± 0.000545 (n=2) | 0.006610 ± 0.000545 (n=2) |
| linear | 24.526 ± 1.194 (n=2) | 0.044529 ± 0.000002 (n=2) | 0.005564 ± 0.000359 (n=2) | 0.005564 ± 0.000359 (n=2) |
| probability | 42.258 ± 3.317 (n=2) | 0.060155 ± 0.000011 (n=2) | 0.007174 ± 0.000160 (n=2) | 0.007174 ± 0.000160 (n=2) |

费用唯一来自 model_call_attempt，包含失败、截断父批、拆分子批及重试。已知费用为目录价估算；未知调用另列，不把缺失 usage 当零，也不合并 CNY/USD。资料/本地模型等其他调用不冒充 ASR 或翻译费用。

本次 ASR 使用北京工作空间 maas.aliyuncs.com 地址，冻结运行时只为精确 dashscope.aliyuncs.com 主机匹配价卡，因此原账本保持 UNPRICED。ASR 列另给实际账本 usage × [百炼北京同名模型公开价](https://help.aliyun.com/zh/model-studio/model-pricing)（输入0.8/输出2.7 CNY每百万token）的参考估算，不回填运行时账本、不声称该 workspace 的最终账单；缺 usage 的调用另列。翻译按冻结 [DeepSeek 目录](https://api-docs.deepseek.com/quick_start/pricing/) 计费。

| 课程 | 新 ASR 调用均值 | 旧 180s 调用均值 | 调用差分 | 新 ASR 目录价参考均值 CNY |
| --- | --- | --- | --- | --- |
| algorithms | 108 | 19 | 89 | 0.059668 |
| calculus | 79 | 13 | 66 | 0.043158 |
| economics | 71 | 12 | 59 | 0.043606 |
| linear | 81 | 14 | 67 | 0.044529 |
| probability | 103 | 9 | 94 | 0.060155 |

静音切分的全部调用/费用已包含于 ASR 总额，不重复相加。差分还受识别输出、输入、失败重试及旧试次未进入阶段影响，不全部归因于切分策略；旧缺失用量仍未知。

| 候选 | 完整链路 | 观察终态秒 |
| --- | --- | --- |
| P1-3 | 0/10 | 947.324 ± 242.855 (n=10) |
| P1-3b | 0/10 | 167.309 ± 54.228 (n=10) |
| P2-1b | 0/10 | 213.832 ± 44.533 (n=10) |

| 阶段/结果 | P1-3 秒 | P1-3b 秒 | P2-1b 秒 |
| --- | --- | --- | --- |
| EXTRACT_AUDIO/completed | 12.257 ± 4.606 (n=9) | 9.430 ± 2.039 (n=10) | 9.439 ± 1.543 (n=10) |
| EXTRACT_AUDIO/failed | NA (n=0) | NA (n=0) | NA (n=0) |
| TRANSCRIBE/completed | 114.713 ± 22.012 (n=9) | 116.779 ± 26.775 (n=10) | 172.145 ± 41.116 (n=10) |
| TRANSCRIBE/failed | NA (n=0) | NA (n=0) | NA (n=0) |
| TRANSLATE_SUBTITLES/completed | 859.588 ± NA (n=1) | NA (n=0) | 29.428 ± 7.308 (n=10) |
| TRANSLATE_SUBTITLES/failed | 900.019 ± 0.011 (n=8) | 39.413 ± 34.273 (n=10) | NA (n=0) |
| GENERATE_LEARNING_PACKAGE/completed | NA (n=0) | NA (n=0) | NA (n=0) |
| GENERATE_LEARNING_PACKAGE/failed | 0.109 ± NA (n=1) | NA (n=0) | 0.112 ± 0.050 (n=10) |

P1-3：8 翻译超时、1 资料 HTTP400、1 MQ 耗尽；P1-3b：10 次翻译失败。历史阶段观察与缺失 token 不补造；详细各阶段比较和费用缺失在 summary.json.baselines。输入切分、模型与功能完成范围不同，不给虚假同口径加速比。

## 独立恢复

任务 `task_bca24366edcd4e09b38f38b213817485`，终态 FAILED，端到端 159.300 秒；故障注入=False。
ASR：UNPRICED；目录价参考 0.042428 + 2 次未知用量 CNY；翻译：0.000000 USD。

恢复未注入：ASR_AUTHENTICATION_403_BEFORE_TRANSLATION_BARRIER。



本次未进入 barrier，没有中断前/后的批次比对。ASR 403 后取消的在途请求保留 NETWORK_OUTCOME_UNKNOWN；不能据此声称已完成批次或 ASR 在重启后零重跑。

30 对首/中/末源文与译文由 Codex 检查：明显含义冲突 0，术语/表达问题 2（概率课两次将 collectively exhaustive 生硬译作“集体穷尽”）。这不是专家评分或整课教学质量验收，原抽样记录/问题保留在 quality-reviews.json。

候选、原始事件、用量与恢复失败判断均可由本目录文件复算。未 push、未部署；进程关闭、生产配置与保护服务比对见 VERIFY.md。
