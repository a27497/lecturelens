# Study Agent 持久记录指标

输入 3 Run；选中 3 Run。

以下均为执行指标，不认证内容质量。金额无持久化记录，标为不可得。

|来源 / 标签 / 场景|N|成功 / 拒答 / 失败 / 取消 / 预算 / 其他|UTC 范围|持久化端到端 P50/P95 ms (N)|执行计时 P50/P95 ms (N)|模型调用总数 (Run N)|完整 token (Run N)|
|---|---:|---|---|---|---|---|---|
|postgresql / saved / unspecified|3|3/0/0/0/0/0|2026-10-14T11:07:19.400690+00:00 → 2026-10-14T11:07:20.771035+00:00|424.248/439.621 (3)|不可得 (0)|12 (3)|不可得 (0)|

工具请求与执行口径（S/F/R/U = 成功/失败/拒绝/未知；百分比顺序为成功/失败/拒绝，分母不含未知）：

|来源 / 标签 / 场景|请求 N，S/F/R/U|请求比率 %|执行 N，S/F/R/U|执行比率 %|
|---|---|---|---|---|
|postgresql / saved / unspecified|9，9/0/0/0|100.00/0.00/0.00|9，9/0/0/0|100.00/0.00/0.00|

完整的每 Run 用量、每工具成功率/失败类别、每节点 P50/P95、各指标样本与时间范围见 report.json。

- 运行成功不等于教学质量通过；故障注入与 mock 只验证机制。各来源/实现/模型/场景分别统计，不合并宣传。
- 端到端=持久化 created_at→finished_at，含排队/恢复；evaluation_execute_ms 是评测执行计时，两者不混用。
- 工具请求=requested_tools，含执行前 tool_rejected；执行口径=executed_tools，仅有 tool_started 的逻辑调用；logical_tools 是后者的兼容别名。
- 两种工具口径分别以成功+失败+拒绝为比率分母，unknown 单列；读取重试不新增逻辑调用。缺失/非法工具名归 unknown。
- 请求口径仅统计可观察的执行起点与拒绝边界，不重建未记录的模型响应；匿名/整段协议拒绝计一个边界，无法取得其中原始工具数/名称。
- MCP 传输成功仅表示调用返回；响应内容校验失败见 tool_read_failed，不能视为依赖语义成功。
- public EVENTS 导出可能分页/截断，缺失工具结束记 unknown；分节点延迟需要已保存的 node 事件。
- 延迟 population_count 为队列 Run 数，sample_count 为已记录调用/节点次数；嵌套耗时不可相加。
- 部分 token 已知总量单列；无完整 usage 的 Run 不进入完整 token 总量/P50/P95。预留 token 不是用量。
- model_calls/tool_calls 是现有持久预算计数；model_events_started/completed 是记录到的调用事件，取消窗口可能不一致。
- time_range 为贡献样本所属 Run 的 UTC 生命周期；时间戳缺失数量明确列出，未推算事件时间。
- 拒答以最终产物 kind=insufficient_evidence 判断；成功但产物类型缺失归 unknown。
- 数据库历史记录未存代码 SHA 时 source_sha256 不可得；已记录模型路由仅输出安全字段指纹，不推断代码版本。

数据来源（SHA256 与逐项身份保存在 report.json）：

- postgresql：3 Run
