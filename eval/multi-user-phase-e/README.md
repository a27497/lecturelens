# Phase E · Multi-user Agent Concurrency & Isolation

本轮验证多用户执行和隔离机制；没有新增 Agent 产品能力、工具或数据库写入通道。实验结果及逐 Run 失败保存在 [results.json](results.json)。固定模型与真实 qwen3-max 分开统计；真实模型的 succeeded 表示运行完成，不代表新增教学质量验收。


## 完成结果（2026-09-21）

**Phase E 实验验收完成，生产代码未修改，原演示 Agent 已恢复。** 多用户隔离、取消和恢复检查通过；当前并发检索会真实失败。此轮到此停止，不开启 Phase F。

| 模式 | users / workers（实际 running 峰值） | attempted / succeeded / failed | Run P50 / P95（s，含排队及失败） | SEARCH P50 / P95（ms，含失败） |
| --- | --- | --- | --- | --- |
| Deterministic | 5 / 5（5） | 5 / 1 / 4 | 1.255 / 2.933 | 58.468 / 131.493 |
| Deterministic | 20 / 5（5） | 20 / 10 / 10 | 2.620 / 6.237 | 42.720 / 76.934 |
| Deterministic | 50 / 5（5） | 50 / 40 / 10 | 9.618 / 19.250 | 61.238 / 80.489 |
| Real · qwen3-max | 5 / 5（5） | 5 / 4 / 1 | 20.755 / 22.726 | 87.090 / 108.756 |
| Real · qwen3-max | 10 / 10（10） | 10 / 4 / 6 | 3.493 / 22.245 | 42.613 / 169.482 |

五个正式组均为 cancelled=0、recovered=0；故障注入另计。成功 Run 的 P50/P95 分别为：固定 5 人 **2.933/2.933s**，20 人 **4.872/6.504s**，50 人 **11.892/19.250s**；真实 5 人 **20.755/22.726s**，10 人 **18.875/22.245s**。真实 10 人组低的总 P50 来自六个快速失败，不是性能改善。

| 模式 / users | model / tool calls | 实际 input / output tokens | timeout / provider rate-limit / infra failed Runs |
| --- | --- | --- | --- |
| Fixed / 5 | 8 / 7 | unknown / unknown（付费调用 0） | 0 / 0 / 4 |
| Fixed / 20 | 50 / 40 | unknown / unknown（付费调用 0） | 0 / 0 / 10 |
| Fixed / 50 | 170 / 130 | unknown / unknown（付费调用 0） | 0 / 0 / 10 |
| Real / 5 | 18 / 14 | 41,081 / 2,948 | 0 / 0 / 1 |
| Real / 10 | 23 / 19 | 46,250 / 3,045 | 0 / 0 / 6 |

正式组共 **90 attempted、59 succeeded、31 failed**。31 个失败均有 SEARCH/HTTPStatusError Trace，并与 Java 的 `RETRIEVAL_UNAVAILABLE` / 503 日志对应。真实成功 Run 的模型调用占总耗时约 **81%–86%**；固定 50 人组排队 P50/P95 为 **7.461s / 17.281s**，执行 P50/P95 为 **2.049s / 2.290s**。五 worker 会逐步错开 SEARCH，50 人组的成功比例不构成更高并发容量的证明。

最终审计：**2,160 次负向请求，0 次越权成功**；另有 360 项正向 scope 检查，0 次混串：

| 检查 | 泄漏 / 绕过 / 混串数 | 样本 |
| --- | ---: | ---: |
| 跨用户 Evidence 页面 / 真实非空 foreign-ID READ | 0 | 180 次请求 |
| 跨 course/session/run 的 Artifact/ANSWERS | 0 | 270 次请求 |
| 跨 course/session/run 的 READ / EVENTS / CANCEL | 0 | 810 次请求 |
| 签名 wrong owner / stale revision，四个 Authority 动作 | 0 | 720 次请求（各 360） |
| unsigned Java Authority / Python command | 0 | 180 次请求 |
| 原始 Session checkpoints / selected Evidence scope | 0 | 90 个 Session、569 个 checkpoint |

59 份成功产物、569 个 checkpoint ID 无重复；实际返回的 Evidence IDs 和最终引用均归属本用户课程。数据是同一公开片段的独立副本，这些数字表示所测路径的 scope/ID 隔离，不是任意私有语料泄漏的穷举证明。

final-review 取消：**5/5 cancelled，5 个晚到返回，0 个旧产物、0 次业务事件或已提交 checkpoint 状态覆盖**；同 Session replacement **5/5 成功**。SEARCH 后中断恢复 **5/5**、产物事务提交后中断恢复 **5/5**；每 Run 仍只有一份产物和一次结束事件，后者连产物内容、工具结果与调用数也不变。故障组与吞吐组分开。

全部 trial 共保留 **128 个终态 Run：82 succeeded、36 failed、10 cancelled**。36 次失败包括正式 31、pilot 2、首次取消组 replacement 3，均为真实检索错误；没有删除失败后重算成功率。准备阶段另保留 **21 个用户的 27 次客户端等待超时**，最终同一批 50 门原课程全部 SUCCEEDED/READY；这些不是 Study Run 超时。

回归：**Python/PostgreSQL 605 passed、0 skipped；Java 相关 62 passed、0 skipped；runner 统计 4 passed；Ruff、语法与 whitespace 检查通过**。Python 只有既有 Starlette/AnyIO 弃用提醒。原始 Trace、provider response、凭据、媒体、准备日志和全部失败均在 `.data/multi-user-phase-e/`，公开投影经过 secret 检查。

## 实验拓扑与数据

- 50 个独立账号，分别通过原 `register → login → upload → task pipeline → READY index` 准备自己的课程。没有复制数据库行，也没有共享用户身份。
- 每人上传同一段 MIT 6.0001 Lecture 3 的 11:00–12:57 字符串视频；原字幕是真实 Evidence。SHA256、出处与 CC BY-NC-SA 4.0 许可见 [课程来源](../study-v1/sources.json) 和 [演示课程说明](../recruiter-demo-phase-d/README.md)。原视频、账号及生成的翻译留在 `.data/`。
- 每个虚拟用户正常登录 Java 8084，创建 Session、幂等 START，经原 Java Authority 和 Python StudyRuntime 执行工具并读取结果。Study 的用户范围由 Java 决定；运维 SQL 仅用于只读 Trace 和副作用核对。
- 运行前停止隔离演示的普通 8094 worker；实验 API 暂停自动 dequeue。runner 仅调度本轮通过 Java 创建的 Run，不领取其他用户的任务。8080/8090/8091 线上服务及模型配置保持原样。
- deterministic 的 5/20/50 用户同时登录和提交，所有 START 持久化后启动本组执行池，固定为 **5 workers**；记录真实 running 峰值及排队时间。真实模型为 5 users / 5 workers、10 users / 10 workers。默认生产 worker 仍串行执行，本实验不宣称默认部署能同时推理 50 个 Run。
- 固定响应复用原 MockProvider 的 search → window → practice/review 路径，显式增加 100ms decision 延迟；只替换模型响应。普通 Run 配置仍由原 API 冻结，私有 Trace 的模型身份另标为 `phase-e-fixed-response`。固定产物仅为合成执行探针；即使原产物字段显示 `model_review`，也不计入真实模型或教学质量结论。
- 同一台 8 logical CPU 主机上的 MySQL、PostgreSQL、Java、embedding 服务及后台课程准备共享资源。早期组测量时仍有正常媒体准备任务；这不是隔离硬件的吞吐量基准。
- 准备后半批账号时临时增加了同隔离库的 Java 8086 进程（原 JAR，512MB heap），只执行正常媒体准备。显式请求 dispatch core/max=8，但线程转储实际只看到 2 个执行线程；没有为此修改生产代码。准备结束后停止该进程，再测 20/50-user 组；没有改变 Agent worker、检索锁或最终被测 Java 配置。

## 指标口径

Run latency 从持久化 `created_at` 到 `finished_at`，**包括排队**；另列 execution、queue 和成功 Run 的分位数。所有分位数使用 nearest rank，5/10 个样本的 P95 不表示稳定尾延迟。

SEARCH latency 来自原 Trace 的 Authority SEARCH 事件，包含 Python→Java→retrieval 整体调用；成功与失败 SEARCH 另有分组。快速 503 也会进入全部 Run / SEARCH 的分位数。模型和工具调用数来自原持久预算计数；token 仅汇总 provider usage，预留预算不当作 token。固定模型 token 为 unknown/null，新增付费模型调用为 0。

主瓶颈已定位到 `Retriever.search()` 的进程内非阻塞单请求锁（与索引同步共用）：并发查询遇到占用返回 503，经 Java `RETRIEVAL_UNAVAILABLE` 传回，Run 记录 `STUDY_EXECUTION_FAILED`。Trace、Java 和 Agent 原日志均保留在 `.data/multi-user-phase-e/`。另做 5 users / 1 worker 固定响应对照：5/5 成功、峰值 1，Run P50/P95 为 6.701s / 10.858s，SEARCH 为 85.097ms / 89.545ms；只作为瓶颈诊断，不替换正式并发组成绩。未增加重试、扩大检索并行度或修改生产代码来提高成功率。

## 隔离和故障实验

每组以 ring peer 并发执行 foreign course/session/run 的 READ、ANSWERS、EVENTS、CANCEL，以及 foreign Evidence、unsigned gateway / Authority 请求。另由可信签名的运维探针向 Java 发出 wrong owner 和 stale revision 的 CHECK / SEARCH / READ / WINDOW，验证签名本身不能绕过业务权属或版本检查。探针不是所有用户对的穷举。

Trace 中实际返回的 Evidence、最终引用及 checkpoint selected Evidence 与该用户自己的 Java Evidence 清单比对。后续组还直接只读枚举 Session 的全部原始 checkpoint，避免只检查按 Run 过滤后的 Trace。产物 ID、checkpoint ID 的重复也单独统计。失败且没有返回 Evidence 的 Run 不被误算为泄漏；公开结果保留实际观察条数。

故障专组逐个通过 SEARCH 后暂停模型响应，让五个真实 Run 同时保持 running；这避免检索容量错误阻止故障注入。取消组在产物最终 review 调用中暂停，取消后先创建同 Session 新 Run。旧 worker 仍持锁时竞争执行不得推进新 Run；放行晚到 review 后旧 Run 不得保存产物或改业务事件。新 Run 随后串行执行，避免把已知检索拒绝混入这项隔离断言。这个受控组不计入并发性能数字。

恢复组在已提交 SEARCH 后、下一次模型调用中真实 SIGKILL 五个独立 worker，然后用每个 Run 两个竞争进程恢复。核对原 Run、deadline、checkpoint 历史、原 tool call ID、SEARCH 次数、唯一 artifact 和唯一 run_finished；被中断的模型调用预算保留，不声称 provider 调用 exactly once。

另有 5-user 提交后崩溃组：eval wrapper 只在原 `StudyStore.save_tool()` 真实提交事务之后暂停，随后 SIGKILL；没有直接 SQL 写入，也没有替换工具结果。此时每个 Run 已有 1 份 artifact / 1 条 artifact_created，但最终 tool checkpoint 尚未完成。双进程竞争恢复后 5/5 成功，产物内容 hash、工具结果、model/tool calls 和原 deadline 均不变，每个 Run 仍只有 1 份 artifact、1 条 artifact_created 和 1 条 run_finished。

## Bad Case 保留

- pilot 3 users：1 成功、2 个 SEARCH/503 失败；最早的 harness 把零 Evidence 观察标成 scope check 不通过。这是缺少观察与泄漏混用的统计错误，原结果仍保留，后续分开记录观察条数与越权返回。
- 早期 foreign-ID 探针从对方成功 Trace 取 ID，失败 Run 可能产生空 READ。最终五组数字统一使用另存的 `isolation-audit-v2.json`：所有 foreign-ID 请求均携带从对方 Java 清单取得的真实非空 ID；原始实验文件未覆盖。
- 正式各组的每个失败 Run、错误码、延迟均列在 results.json；不补跑覆盖原成绩。
- 首次取消专组的 5 个原 Run 全部取消，5 个并发 replacement 中 3 个遇到检索 503，2 个成功；该失败保留。之后单独执行的 final-review 取消组使用串行 replacement，只验证隔离。
- 初次要求完整 checkpoint 对象逐字不变过严：LangGraph 会为 `RunStopped()` 追加 `pending_writes.__error__`。完整对象比较的 false 保留；后续保存取消前后快照，核对新增的只有停止诊断，已提交 checkpoint ID/state 与业务事件不变。没有删掉错误或把它改写为业务成功。

## 复现

需要现有隔离 learning-loop 配置、真实数据库、已有 Java JAR 和 hash 匹配的视频。私有配置固定为 `.data/phase-completion-20260920/runtime.local.json`；`serve.py` 会拒绝线上 profile。不要与普通 8094 worker 同时运行实验 API。

```bash
# 从仓库根目录；先停隔离演示 Agent 8094，保留 Java 8084 和基础服务。
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/serve.py

# 另一终端。已有用户可继续等待原 task/index；保存日志以保留准备失败。
python3 eval/multi-user-phase-e/prepare.py --users 50

# 每次使用新的 label；已有 trial 目录会拒绝覆盖。
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/run.py cohort --users 5 --workers 5 --label deterministic-5
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/run.py cohort --users 20 --workers 5 --label deterministic-20
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/run.py cohort --users 50 --workers 5 --label deterministic-50
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/run.py cohort --mode real --users 5 --workers 5 --label real-5
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/run.py cohort --mode real --users 10 --workers 10 --label real-10
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/run.py faults --label faults-5
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/run.py late-result --label late-artifact-5
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/run.py artifact-recovery --label artifact-recovery-5

# 对五个正式 cohort 分别追加完整隔离审计，例如：
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/audit.py --label deterministic-5
# 将其余四个 label 同样审计后，可查看各 trial 的 result.json。
# 以下命令专门复算本次完整私有台账的公开投影：还需本次 pilot、
# sequential-control、environment.json、regression.json 等已保存的运维证据。
PYTHONPATH=agent-service/src agent-service/.venv/bin/python eval/multi-user-phase-e/report.py --output eval/multi-user-phase-e/results.json

# 独立测试库，不能指向实验/生产数据。
AGENT_TEST_DATABASE_URL='postgresql://USER:PASSWORD@127.0.0.1:PORT/lecturelens_agent_test' uv run --directory agent-service --frozen pytest -q
PYTHONPATH=agent-service/src agent-service/.venv/bin/pytest -q eval/multi-user-phase-e/test_runner.py
(cd backend && ./mvnw -q -Dtest=StudyControllerTest,StudyAuthorityTest,DenseEvidenceClientTest,DenseRetrievalRoutingTest,CourseQaEvidenceRetrieverTest test)

# 停实验 API 后恢复原演示 Agent：
python3 eval/recruiter-demo-phase-d/serve.py agent
```

固定响应验证协议与隔离；真实模型只验证当前公开课程上的并发执行。此轮不推进 AU 质量门槛，不证明未见课程泛化、自动评分、Memory 或长期并发稳定性。Phase E 是本次最后一个求职增强实验，完成后停止，不开启 Phase F。

`run.py` 可用新 label 重跑单组；`report.py` 是本次冻结台账的汇总脚本，包含本次早期 harness 问题的历史说明。新实验不应复用旧的回归/环境证据或历史失败说明。公开仓库没有本机凭据、课程数据库和原始响应，不宣称新机器零配置复现。
