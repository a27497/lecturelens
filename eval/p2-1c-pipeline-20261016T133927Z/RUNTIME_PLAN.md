# P2-1c 冻结候选运行计划

用户已确认方案a，并允许Redis DB15的12个已知历史进度key原样保留。授权仅扩展这些key，不允许未知key、清空或换库。运行前只读gate见runtime-gates.json；ASR账户、凭据、模型、端点、权限均只查不修。

## 已冻结

candidate-artifact.json固定新JAR、源码base commit、candidate.patch和各源文件SHA256。上下文默认8192，输入估算≤70%，另扣输出及256预留；map输出512、最终4096；全次生成含质量修复最多64次物理请求、6层归并、900秒。无部署、无在线绑定变化。运行辅助类单独保存，不修改候选JAR。

## 独立完整链路10+1（当前未启动）

1. df可用至少2GiB，精确使用率≤85%；只读核查Redis15仅有显式允许的12个已知key或其中未过期的子集。新增本轮任务key仅在有本轮提交日志证明后纳入允许范围；出现未知key立即停。运行时每2秒检查磁盘，超过85%立即停止本轮进程。
2. 复用隔离127.0.0.1:18091、lecturelens_p21_20261016 schema及lecturelens-p21-20261016T073754Z topic/group，不重置/改写旧任务或候选证据。模型系统配置v10，与现有部署捕获指纹保持一致；翻译仍是DATABASE deepseek-flash，资料仍是ENV lecturelens-local-qwen。Python Agent/索引写入关闭。
3. ASR端点具备访问资格后，按原assets.lock.json五节课依次各2次，提交10个全新taskId，从真实ASR开始，完整走到资料与产物。不得用旧转写或本文补充验证替代正式试次。所有失败计入原试次，不自动补足成功次数。
4. 第11个taskId独立恢复试次，使用原经济学课。翻译至少2个且至少一半根批次SUCCEEDED、仍有未完成批次时，在供应商调用派发前屏障暂停后续翻译，保存不可变批次/物理调用/执行epoch/用量快照。核验本轮worker PID、启动ticks、cwd、候选SHA后仅对此worker发一次SIGKILL，然后用相同冻结JAR重启，等待原租约及持久化恢复协议接管。
5. 比较中断前后已完成批次的编号、源/请求/结果哈希、attempt_count及对应物理调用ID集合，证明没有新增调用或重算；记录epoch提升、resume_count、未完成批次恢复和最终发布。没有到达翻译屏障或没有实际SIGKILL时，明确标记恢复未完成。
6. 结束后停止本轮进程，确认18091释放；不push、不部署、不操作受保护容器生命周期。正常10次与独立恢复分别报告，耗时使用样本标准差ddof=1，分成功/失败阶段；ASR和翻译币种/费用分别列，未知值保留NULL，不将目录价参考写成实际账单。沿用P2-1b统计口径对比P1-3、P1-3b、P2-1b。

## 当前阻碍与补充验证边界

冻结后短音频预检仍HTTP403 AccessDenied.Unpurchased（postfreeze-asr-preflight）。因此正式10+1提交0次、worker启动0次、SIGKILL0次；未将已知拒绝状态消耗成10个新失败，也未改变ASR绕过该阻碍。

MaterialsSupplement.java仅复用上轮normal-algorithms-1已保存的原文/译文，对冻结的提示、上下文守卫、真实本地模型及解析器进行独立验证，无ASR/翻译调用、无数据库写入、无发布、不启动worker。此辅助程序没有服务鉴权/围栏集成，不证明完整链路或恢复，不计入10+1，所有结果原样保留。
