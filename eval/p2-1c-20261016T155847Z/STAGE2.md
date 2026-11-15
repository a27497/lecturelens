# 阶段 2：B/D/F/G 机制完成，未跑真实课程

B：新任务可选冻结 ASR 2→4 AIMD、成功阈值与主机内共享速率/并发限制；窗口、冷却、分片 attempt_count、未知网络结果与 epoch 持久化。429 收缩，401/403 不重试。状态派发预留不冒充物理 HTTP 计数；费用/实际并发仍来自 model_call_attempt。

D：基于同一旧静音计划合并相邻区间，目标参数 60/90/120 秒，保留夹入静音的原时轴和所有原片来源；记录合并前后片数，文件上限/尾片有原因。原文段落校验按该任务的冻结合并上限处理，旧策略的 60 秒限制不变。

F：沿用原先已有的 16000 Hz/mono 默认，一次抽取显式 PCM s16le，增加抽取实际耗时与输入/输出 bytes。真实 FFmpeg 合成媒体测试验证格式转换；MIT 课程抽取耗时/大小变化未测。

G：同所有者命名空间中 audio SHA256 + 冻结 ASR 配置身份缓存成功结果；显式配置/语言变化失效，原任务删除、过期、损坏失效，容量有界。默认 OFF，同时禁用缓存读写；同任务合法 checkpoint 恢复另记。生产转写步骤联通测试用真实独立 MySQL 和确定性适配器，证明重复执行同任务不会再次调用适配器；不是真实供应商演示。

参数默认关闭新 ASR 扩展、合并和缓存，不改在线配置。V32 为新表与不可变约束，已在独立测试 schema 验证，不迁移业务或 P2-1b 运行库。新 ASR 配置中 maximum 支持独立 8 的实验身份；真实并发 4/8 均未测。

## 实际检查

- stage2-checks-01.json：179 项，4 failures、2 errors、0 skipped；失败完整保留。原因包括数据库状态类放错层、MySQL JSON 规范化导致内容 hash 不匹配、HTTP 夹具 headers 空值和旧超时断言。
- stage2-checks-02.json：187 项通过，失败/错误/跳过均 0。
- stage2-checks-final.json：191 项通过，失败/错误/跳过均 0；包含等待共享许可时的关闭取消、旧 epoch 完成围栏和缓存 OFF 行为。
- stage2-checks-final-02.json：192 项通过，失败/错误/跳过均 0；补充生产转写步骤与独立 MySQL 的联通检查。
- stage2-merged-integration.json：合并开关明确开启后的 7 项复核全部通过，失败/错误/跳过均 0；这些与上轮重复，不累加为 199 个独立测试。

复算：`python3 eval/p2-1c-20261016T155847Z/verify_checks.py --prefix stage2- --final stage2-merged-integration.json`。每轮原始命令、日志路径/hash、JUnit 归档/hash、磁盘门禁与退出码保存在对应 JSON；原始记录在 `.data/p2-1c-20261016T155847Z/checks/`。没有供应商调用、正式测速、CER、费用或缓存命中演示的真实验收结论。
