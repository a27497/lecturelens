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
