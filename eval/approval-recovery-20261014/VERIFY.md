# P1-2 验收包

本文件仅补充出处、口径和复算步骤，旧 JSONL、summary、RESULTS 与验证记录不改写。文档补充批次为 2026-10-15（北京时间）；新执行记录自带实际 UTC 时间。运行时代码不变，不 push、不部署。

## 数字与原始证据

| 数字 / 口径 | 样本量 | 原始文件与计算 |
|---|---:|---|
| 577/577 次不变量检查通过 | 577 个计划试验 | `matrix-final/raw.jsonl` 523 行 + `approval-decisions/raw.jsonl` 54 行；检查每行 `passed` 及所有 `checks` 均为 true；对照 `RESULTS.json` |
| 523 个不同注入点，各 1 次 | 523 个 `(profile, point)` | `matrix-final/raw.jsonl` 去重该二元组；每个组 N=1；包括一个三次强杀的特殊场景，见下文 |
| 54 次审批边界 = 18 组合 × 3 | 18 个组合 / 54 次 | `approval-decisions/raw.jsonl` 按 `(kind, decision, point)` 分组；每组 N=3 |
| 96 次 `MODEL_OUTCOME_UNKNOWN` | 主矩阵 523 次中 96 次 | 原始 `after.error_code`；不是同名 Trace 事件出现次数，也不是恢复成功 |
| 主矩阵恢复 P50 1658.319 / P95 2641.105 ms | 523 个 `recovery_ms` | `matrix-final/raw.jsonl`；排序后取 `ceil(N×p)-1` 下标，与 `RESULTS.json` 对照 |
| 审批恢复 P50 1140.497 / P95 1214.510 ms | 54 个 `recovery_ms` | `approval-decisions/raw.jsonl`，同一 nearest-rank 算法 |
| 发布成功 456、明确拒绝 18、读取上限失败 1、取消 2、删除 4 | 合计 577 次中的各终态 | 两批 `after`，已删除为 `deleted`，否则优先 `error_code`、再 `status`；主矩阵成功 420，审批成功 36 / 拒绝 18 |
| 原全量 Python 727 passed，0 failed/errors/skipped | 727 个唯一 case | `tests/group-0.xml` 至 `group-3.xml` 的 testcase；逐项与 `tests/collected.txt` 比较 Counter，全部且仅执行一次；原 `tests/verification.json` 记载四个独立 PG 实例 |
| 其中审批/恢复测试 23 项 | 23 个 case，包含在 727 中 | 同一四份 JUnit 中 classname 含 `test_study_approval`；不是额外加到 727 |
| 原相关 Java 12 项（8 权属 + 4 网关） | 12 个 case | `browser-evidence/java/TEST-*.xml` 是已有 Surefire 文件的公开投影：保留 suite 属性及原 testcase，去掉环境 properties/system logs；原文件路径与原字节哈希见 `browser-evidence/manifest.json`；对照原 `verification-static-final.json` |
| 原前端 99 passed，0 failed/pending | 99 个测试 | `frontend-tests.json` 原 Vitest JSON；对照 `verification-static-final.json` |
| 原真实 Chrome 7/7 | 7 个检查 | `browser-final.json` 的 5 个 checks + `browser-feedback-final.json` 的 2 个 checks；六张旧截图不能替代 JSON 中等待强杀/越权断言 |
| 原真实 Java 删除 1/1，7296.182 ms | 1 次 | `deletion-final.json`，单个实际删除清理样本，不是 SLA 或浏览器额外 case |
| 本次审批测试 23 passed / 0 skip | 23 个 case | `documentation-check-20261015/approval-tests.xml`，专用临时 PostgreSQL；本次未重跑全量 727 / Java / 前端 / 浏览器 |
| 本次 Ruff check + format check 通过 | 检查 agent-service 与三个指定脚本 | `documentation-check-20261015/checks.json` 记录命令、退出码和实际输出；92 个文件格式检查通过 |
| 本次缺审计表审批 18/18，通过等待强杀 6/6 | 18 个组合，各一次 | `documentation-check-20261015/approval-missing-audit-table/raw.jsonl`；在独立 PG 完成审批测试后，确认 `eval_remote_call` 不存在，再执行审批脚本；不并入旧 577 样本 |
| 本次矩阵 smoke 30/30 | 30 个不同子集注入点，各一次 | `documentation-check-20261015/matrix-smoke/raw.jsonl`；实际串行运行抽样入口，不并入旧 523/577 或原恢复分位数 |
| 本次空 schema 明确拒绝启动 | 1 次 | `documentation-check-20261015/empty-schema-check.json`：非零退出，错误包含矩阵前置命令，输出目录未创建 |

全量/Java/前端的旧测试数字来自旧原始结果复算，本次只重新执行用户要求的审批相关测试和 Ruff。验收方的外部 35/35（等待强杀 12/12）没有对应原始文件保存在本目录，不能由本包独立复算，也未混入统计。

## 已实际执行的只读复算命令

在仓库根目录：

```bash
agent-service/.venv/bin/python eval/approval-recovery-20261014/verify.py
```

标准输出实存于 [recomputed.json](documentation-check-20261015/recomputed.json)。该脚本从原 JSONL 复算两批样本、终态和分位数，逐点核对两份原 summary，核对原 RESULTS；从原 JUnit 核对 collection 及 727/23，读取 Java 公开投影、前端和浏览器原记录，校验复制截图哈希。已执行两次，输出一致；`checks.json` 记录重复核对。关键输出：577/577、523 个不同点、18×3、96、1658.319/2641.105 ms、1140.497/1214.510 ms。

本次新增证据的复算（无需启动服务）：

```bash
agent-service/.venv/bin/python - <<'PY'
import json
import xml.etree.ElementTree as ET
from pathlib import Path
p = Path('eval/approval-recovery-20261014/documentation-check-20261015')
suite = ET.parse(p / 'approval-tests.xml').find('testsuite')
tests = {k: int(suite.get(k)) for k in ('tests', 'failures', 'errors', 'skipped')}
assert tests == dict(tests=23, failures=0, errors=0, skipped=0)
rows = [json.loads(s) for s in (p / 'approval-missing-audit-table/raw.jsonl').read_text().splitlines()]
assert len(rows) == 18 and all(r['passed'] and all(r['checks'].values()) for r in rows)
waiting = [r for r in rows if r['point'] == 'waiting']
assert len(waiting) == 6 and all(r['checks']['injection_reached'] for r in waiting)
checks = json.loads((p / 'checks.json').read_text())
assert all(checks[k]['exit_code'] == 0 for k in ('ruff_check', 'ruff_format'))
error = json.loads((p / 'empty-schema-check.json').read_text())
assert error['clear_prerequisite_error'] and error['output_directory_not_created']
smoke = [json.loads(s) for s in (p / 'matrix-smoke/raw.jsonl').read_text().splitlines()]
assert len(smoke) == 30 and all(r['passed'] and all(r['checks'].values()) for r in smoke)
deletion = json.loads((p.parent / 'deletion-final.json').read_text())
assert deletion['n'] == deletion['passed'] == 1 and deletion['cleanup_ms'] == 7296.182
print({'approval_tests': tests, 'approval_sample': '18/18', 'waiting_SIGKILL': '6/6', 'matrix_smoke': '30/30', 'ruff': 'passed', 'blank_schema': 'explicit error', 'original_deletion_ms': deletion['cleanup_ms']})
PY
```

## 特殊行：同一次 Run 三次 SIGKILL

`retry_cap / SEARCH:three_crashes` 原记录没有 `injection_reached`。它的正确检查键为 `checks.three_injections`；同一 Run 在 `authority.SEARCH:0:before` 被三个子进程分别强杀，第四个 worker 恢复后耗尽已持久化尝试上限。

`check-study-crash-matrix.py` 逐次将 `process()` 返回码加入 `codes`，实际判断为 `codes == [-signal.SIGKILL] * 3`（Linux 为三个 -9）。**三次必须全部是 SIGKILL 才通过**，不是仅检查最后一次，也不是任何非零退出均算。`verify.py` 对照原 `verification-static-final.json` 校验该驱动 SHA-256 未变，并检查此判断以及原行 `three_injections/persistent_cap` 为 true。

原记录未保存三个独立的返回码值；原始布尔检查的判断代码和冻结身份是现有证据，不能事后伪造返回码字段。该行统计 N=1，`recovery_ms` 只计第四个 worker，前三次强杀不计入此恢复耗时。不修改旧原始记录，也不计成三个独立恢复样本。

## 最小抽样复跑与依赖

专用 PG 连接串通过 `AGENT_TEST_DATABASE_URL` 提供，dbname 必须为 `lecturelens_agent_test`；不能使用服务库。按 [REPRODUCE](REPRODUCE.md) 准备依赖后，从仓库根目录串行运行：

```bash
APPROVAL_BATCH="eval/approval-recovery-NEW-$(date -u +%Y%m%dT%H%M%SZ)"
agent-service/.venv/bin/python scripts/eval/check-study-crash-matrix.py \
  --smoke --trials 1 --output "$APPROVAL_BATCH/matrix-smoke"
agent-service/.venv/bin/python scripts/eval/check-study-approval-recovery.py \
  --trials 1 --output "$APPROVAL_BATCH/approval-sample"
```

矩阵必须先初始化基础 Agent、VectorStore 与 checkpoint schema，原实现还先建 `eval_remote_call`。补充后的审批脚本可在基础 schema 已存在时自己补建该评测审计表；空基础 schema 则明确报错，提示先执行矩阵。它复用矩阵驱动，不能当成完全独立的冷启动脚本。输出目录必须全新，不能覆写本目录旧结果。审批最小样本为 18 个组合各一次，等待中强杀为六个组合各一次；不等于旧 54 次重复采样。

## 浏览器文件与局限

[六张截图与来源哈希](browser-evidence/manifest.json)来自之前最终浏览器运行，按字节复制，未补拍或修改。[报告](README.md#验收证据补充2026-10-15仅追加)逐张引用。**等待强杀及越权检查无截图；无已保存的 Playwright trace**。其 JSON 断言仍可核对，但无法还原完整 UI 交互视频或每步浏览器网络日志。

矩阵使用 mock 模型和 Java Authority 桩、真实 Agent worker/PostgreSQL/LangGraph checkpoint；不是付费模型质量验证。主矩阵每点仅一次，不能证明每点故障恢复概率或生产延迟稳定性；审批每组合三次也不足以作生产 SLA。仅课程所有者可审批，没有管理员跨账号代审。强杀 Agent worker不等于数据库进程强杀、主机断电、磁盘损坏或主备切换。完整未覆盖范围见原报告边界表。
