# VERIFY：P1-3d 新增观测与单次复现

最新结果与根因见 [REPRO.md](REPRO.md)。本轮观测代码提交 `bc2e6cc79f1a3311b90cc4d407f75d2e20048275`，改动 10 个代码/迁移/测试文件，详见 `p13d/code-files.json`。相关 Java 单元/回归测试 **115 项通过，0 失败、0 错误、0 跳过**；只打包并替换既有生产 Java JAR，Flyway V26 成功，未改并发/超时/翻译/校验逻辑，未重启 agent-service、llama 或 RocketMQ。

单次任务 `task_1b5dd375008544258544f7b6f3a2001c` 冻结 v10 / DATABASE / deepseek-flash。只提交一次，成功批次 0、失败批次 1；直接失败子项 CONTENT_EMPTY。HTTP 200、content 空、非空 reasoning_content、finish_reason=length，证实本次在给出最终译文前触及长度限制。失败调用 token 已入 `translation_call_diagnostic`：903 输入 + 3073 输出 = 3976。供应商输出计数按原值保留（请求 max_tokens=3072）；不将历史 10 次未知失败追认成同一原因。

系统绑定前后完全一致，保持 v10；修复建议未实施，无第二次真实调用。任务期间磁盘峰值 84.8966563433369%，结束复核 84.81246703111945%，活动任务 0。新响应/课程全文仅存本机 `.data/.../p13d/`，不提交；普通任务 API、错误消息和日志不返回新响应摘录。旧阶段 ai_call_record 的失败 token 列仍可能 NULL，逐调用用量以新诊断表为准。

## 磁盘门槛复核与补交

前次封存阶段因磁盘约 85.58% 停止，真实单次任务当时已经结束。按本次授权重查十个精确上传临时路径：检查前均已不存在；上传均 STORED、11 条关联任务记录均已 FAILED，全局 lsof 路径匹配为 0。本次没有删除文件或扩展范围，删除释放量为 0 字节。北京时间 `2026-10-16T14:49:32.324933+08:00`（UTC `2026-10-16T06:49:32.322337+00:00`）复核磁盘为 **84.503865%**，低于 85%，故继续提交。原始检查、完整十路径及 df 文本见 `p13d/upload-temp-cleanup.json`。该读数与前述真实任务运行期间的历史峰值分别保留。

## P1-3d 证据与数字复算

| 验收/数字 | 证据 | 复算命令 |
| --- | --- | --- |
| 115 项、各类测试数量及 0 失败/跳过 | `p13d/checks/test-summary.json`、`java-related-tests.log` | 读取 test-summary 累加 tests/errors/failures/skipped；相关测试命令见 REPRO.md |
| 单次任务、v10、完整冻结路由、模型/来源、绑定未变 | `p13d/submission*.json`、`snapshots.json`、`catalog-before/after.json` | `python3 eval/baseline-deepseek-20261015T185735Z/p13d_verify.py` |
| 成功 0、CONTENT_EMPTY 1、HTTP200、length、token 903/3073/3976 | `p13d/diagnostics.json`、私有 `diagnostics-with-excerpts.json` | 同上；实时限定列 SELECT 见 REPRO.md |
| 原 body 11337 字符、脱敏保留 4000、摘录 SHA256 | `p13d/diagnostics.json`、`final-check.json`；私有 `response-excerpt.txt` | 同上校验摘录长度和 SHA256；`sha256sum` 私有文本 |
| 阶段 8724 / 104849 / 17431 ms，任务观察 132646.959 ms；输入/prompt 大小与请求参数 | 私有 `task-log.json`、公开 `terminal.json`、`summary.json` | 同上，pipeline_stage_ms / translation_request_parameters / task_observation_ms |
| 磁盘峰值、结束值、无活动任务、服务进程未变 | `p13d/disk.jsonl`、`final-check.json`、`preflight.json` | 同上复算峰值；结束值与进程来自 final-check |
| 旧/新 JAR 哈希、代码身份、V26/健康、备份 | `p13d/deployment-intent/result.json`、`candidate-freeze.json` | `sha256sum` 对应本机 JAR/备份；只读字段见记录 |
| 旧 P1-3b 87 个哈希条目完整保留 | `p13d/P13B_SHA256SUMS.before`、`P13B_VERIFY.before.md`、`old-freeze-check.json` | p13d_verify.py 对旧 VERIFY 使用归档字节，其他旧条目逐个原路径校验 |
| 新日志凭据形态扫描、诊断写入无错误 | `p13d/final-check.json` | 限定部署时间窗 journalctl；仅按 sk-/Bearer 形态扫描，未读取供应商密钥作比对 |

```bash
cd /home/dev/projects/lecturelens
python3 eval/baseline-deepseek-20261015T185735Z/p13d_verify.py
sha256sum -c eval/baseline-deepseek-20261015T185735Z/SHA256SUMS
sha256sum -c eval/baseline-deepseek-20261015T185735Z/RAW_SHA256SUMS
sha256sum -c eval/baseline-deepseek-20261015T185735Z/p13d/RAW_SHA256SUMS
```

本轮原始记录在 `/home/dev/projects/lecturelens/.data/baseline-deepseek-20261015T185735Z/p13d/`。包含两轮早先测试、最终测试、打包、部署驱动/日志、旧 JAR 硬链接、迁移历史备份、任务日志、脱敏响应摘录和最终结果。新私有证据用 `p13d/RAW_SHA256SUMS` 单独封存；根目录 RAW_SHA256SUMS 保持原字节。公开 SHA256SUMS 已更新，包含此次新增交付及更新后的本文件，不包含自身、缓存或私有资料。P1-3c 的 DIAGNOSIS.md 保持该轮“不提交”的本地状态，未纳入此次提交清单。

下方 P1-3b 内容为历史说明，**其中“业务改动无、部署无、Java JAR 未变”只适用于当时十次基线测量**。原完整 VERIFY 字节另存 `p13d/P13B_VERIFY.before.md`，旧试次、结果与私有原始记录均不改写。不要运行 render_report.py 覆盖本文件，亦不要自动重放真实测量驱动。

---

# P1-3b VERIFY

本轮业务源码/业务配置文件改动：**无**。新增内容只在 `eval/baseline-deepseek-20261015T185735Z/`；文件与结果哈希逐一列在 SHA256SUMS。系统数据库只通过管理员接口把 TRANSLATION_FULL_TEXT 从无绑定改为已保存模型 1，生成版本 10，完成后保留；不读取/录入供应商密钥。未改超时、并发、代码，未部署、重启、合并、push。

结果、逐次失败、均值/样本 SD、单节翻译耗时、费用可观测缺口及旧基线对比：SUMMARY.md。管理员页面具体点击步骤：PAGE_STEPS.md。

## 每个数字的证据与复算

| 数字/结论 | 原始记录 | 离线复算命令 |
|---|---|---|
| 10 次、5 课各 2 次、成功率、终态 | trials.jsonl、results/*.json | python3 eval/baseline-deepseek-20261015T185735Z/score.py |
| 各阶段秒数、均值 ± 样本 SD（ddof=1） | events/*.json；私有 logs/*.json | 同上，overall/per_lecture/trials |
| 分段数与已知批次 token | translation-segment-counts.json、events/*.json、results/*.json | 同上；原始计数在 segment-counts 与逐次文件 |
| 未知失败调用 token/重试、完整费用不可得 | database-call-diagnostics.json、summary.json | 同上；NULL 不填 0 |
| 官方价格、费用区间 | pricing.json；私有 deepseek-pricing.html | 同上；SUMMARY.md 中 P/C/T 公式 |
| 全部失败任务 30 / 正式基线 10 / 其余 20 | failed-task-inventory.json | python3 eval/baseline-deepseek-20261015T185735Z/verify.py |
| MQ 重试/死信积压 0，旧 DB 不变 | mq-*.json、dead-handling.json、original-baseline-db-before/after.json | 同上 |
| 版本 10，DATABASE，deepseek-flash，绑定保留 | binding-preflight.json、snapshots/*.json、catalog-final.json | 同上 |
| 磁盘始终不超过 85%、单任务不超过 30 分钟 | disk-observations.jsonl、trials.jsonl、final-check.json | 同上 |
| 旧基线对比数字 | eval/baseline-asr-20261015/summary.json；本目录 summary.json | score.py；render_report.py |
| 原始资料 HTTP 400（若出现） | local-http-400-responses.jsonl、http-400-diagnostics.json | python3 eval/baseline-deepseek-20261015T185735Z/diagnose_400.py（仅离线） |

```bash
cd /home/dev/projects/lecturelens
python3 eval/baseline-deepseek-20261015T185735Z/score.py > /tmp/baseline-deepseek-20261015T185735Z-summary.json
cmp /tmp/baseline-deepseek-20261015T185735Z-summary.json eval/baseline-deepseek-20261015T185735Z/summary.json
python3 eval/baseline-deepseek-20261015T185735Z/verify.py
sha256sum -c eval/baseline-deepseek-20261015T185735Z/SHA256SUMS
sha256sum -c eval/baseline-deepseek-20261015T185735Z/RAW_SHA256SUMS
agent-service/.venv/bin/ruff check eval/baseline-deepseek-20261015T185735Z
agent-service/.venv/bin/ruff format --check eval/baseline-deepseek-20261015T185735Z
```

render_report.py 可从冻结记录重新生成 SUMMARY.md、ALL_FAILED_TASKS.md 与本文件。collect_final.py/inventory.py 会读取实时数据库，不能用来改写历史快照；不属于离线复算。run_measurement.py 会真实收费，不能当验证命令自动重放。

## 原始记录与保密

原始结果全文、按任务筛选后脱敏的 Java 日志、nohup 驱动日志、响应观察器日志、官方价格网页在 `/home/dev/projects/lecturelens/.data/baseline-deepseek-20261015T185735Z/`，路径索引见 raw-locations.json，哈希见 RAW_SHA256SUMS。媒体沿用 `eval/baseline-asr-20261015/assets.lock.json` 中的原路径和 SHA256；没有下载替代媒体，也不重新发布视频或全文。MIT OCW 原来源与 CC BY-NC-SA 4.0 署名沿用旧基线 SOURCES.md。

后台测量命令为 nohup + timeout（总上限 20000 秒），每个任务独立 1800 秒观察上限，串行、无重投。仅 GET /api/me 阶段的初次驱动失败（字符串成功码 0 处理错误）发生在上传/任务创建之前，原驱动、回执和冻结哈希保留为 driver-attempt-01-*；不计入 10 次模型试验。首次绑定检查的来源标签 DB/DATABASE 差异见 binding-preflight.json，绑定只保存一次，没有偷偷增加版本。

## 验证范围

本轮是实际供应商端到端失败/耗时测量，不是学习质量或新课程泛化验收。未运行 Java/前端/Python 业务全量测试，因为业务代码和部署未变。离线证据验证、eval 脚本 ruff 与哈希校验结果见 checks/。冻结的错误试次不改判为成功，失败终止耗时不叫成功时延，未进入阶段不记零，缺失用量不估成零。
