# L4 评测工具：CodeRabbit Major 意见分诊

CodeRabbit 在 PR #80（head `9305e18`）的审阅正文里列出 29 条 Major 意见，全部针对 `agent-service/src/lecturelens_real_eval/l4/` 评测工具及其测试。本文逐条对照 main（`d9cb21a`）的代码核实。

## 结论

- **29 条在当前代码上都成立**：问题都还在代码里，没有一条已过时，也没有一条判为不成立。
- **一条都没有修。** 已发布的 L4 结果由这套工具产出，冻结记录绑定了它的代码身份（[freeze.json](freeze.json)）。改工具会让代码和证据对不上。另外，第 12 条的修复会改变已发布的数字（见下表），按规则只能记为已知问题。其余 28 条留给下一个评测候选的工具版本，到时与新留出集一起冻结。
- **对已发布结果的影响**：逐条对照了私有运行记录。第 18 条只影响探索性的“无裁判在途”延迟子集。其余 27 条在 L4 运行中没有触发，或只会让费用闸门更保守。这 28 条都不影响任何质量指标。第 12 条的触发情况见下文。
- **离线复算**：在 main 上用已保存的输出重新执行 `verify` 和 `score`（没有调用任何模型）。逐行结果文件与发布时的文件逐字节相同（sha256 `4c48c8b6…de58`）。汇总文件只有输出标签字段不同，去掉标签后的规范化 JSON 哈希相同（`f611236f…03ae`）。

## 分诊表

“未触发”的依据是 L4 私有运行记录：`verify` 通过；UNDETERMINED 为 0；最终留出集记录中的每条失败都带有 `cost_nano`；Java 地址为本机 `127.0.0.1`；运行期间没有重新建索引。

| # | 文件 | 意见 | 判定 | 对已发布结果的影响 |
| --- | --- | --- | --- | --- |
| 1 | ledger.py | 部分调用缺 usage 时，UNCERTAIN 的记账金额可能低于已知成本 | 成立 | 只影响费用台账。UNCERTAIN 已按账单核实为 0 |
| 2 | ledger.py | `os.write` 部分写入时仍会确认预留 | 成立 | 未触发：台账重放正常 |
| 3 | test_l4_benchmark.py | 并发上限测试在子进程异常退出时会卡住 | 成立 | 仅测试健壮性 |
| 4 | citations.py | 引文按子串匹配，不按整词匹配 | 成立 | 只影响金标准引文校验。全部金标准经过 Codex 全量审核 |
| 5 | questions.py | `load_frozen` 校验的字节与解析的字节不是同一次读取 | 成立 | 未触发：冻结后文件没有变化 |
| 6 | questions.py | 加载冻结时没有校验 asset lock 和审核文件 | 成立 | 未触发 |
| 7 | questions.py | 空题集也能冻结 | 成立 | 未触发：冻结记录了 30 / 96 题 |
| 8 | questions.py | 没有检查文件内声明的 split 与文件名一致 | 成立 | 未触发 |
| 9 | questions.py | 校验与计算哈希是两次读取 | 成立 | 未触发 |
| 10 | questions.py | Evidence 快照没有绑定到冻结记录 | 成立 | 未触发 |
| 11 | judge.py | nugget 列表里出现非对象元素时，worker 会崩溃，不会重试 | 成立 | 未触发：UNDETERMINED 为 0，780 条判定全部有效 |
| 12 | judge.py | 同一论断允许同时出现 `alone` 和 `needed`；support 不是 `full` 时也允许 `needed` | 成立 | **会改变已发布数字**，见下文。不修，记为已知问题 |
| 13 | cli.py | 成本闸门把未结预留算了两次 | 成立 | 闸门偏保守。投影 USD 24.4，远低于 100，判定不变 |
| 14 | cli.py | 打分时没有检查所选记录的判定是否完整 | 成立 | 未触发：`verify` 通过，判定 780 条，有效记录 780 条 |
| 15 | cli.py | 预测时把 0 成本的单元按预留上限计 | 成立 | 闸门偏保守 |
| 16 | cli.py | `choices` 不是对象时，worker 会崩溃，不会重试 | 成立 | 未触发 |
| 17 | cli.py | 记录文件不是原子写入 | 成立 | 未触发：全部记录可以解析 |
| 18 | cli.py | RAG 的“裁判在途数”在节流等待之前采样 | 成立 | 只影响探索性的“无裁判在途”延迟子集，两组 P50 只差 0.02 s |
| 19 | cli.py | 余额预检在还没有观测值时按 0 成本估算 | 成立 | 未触发：每次预检时都已有观测值 |
| 20 | cli.py | 余额估算按判定条数计，不按唯一单元计 | 成立 | 未触发：rejudge 只有 1 条 |
| 21 | cli.py | 收到 402 时，先释放并发槽位，再设置停止标志 | 成立 | 修订 4 之后没有再出现 402 |
| 22 | cli.py | 余额查询本身失败时没有停止准入 | 成立 | 未触发 |
| 23 | cli.py | `rejudge` 没有先整体校验再归档 | 成立 | 未触发：只用过一次，1 条 |
| 24 | cli.py | 同一次重复内，各路径的 Evidence revision 没有强制一致 | 成立 | 未触发：运行期间没有重新建索引 |
| 25 | runner.py | 远程 Java 地址没有要求 HTTPS | 成立 | 未触发：只连本机 127.0.0.1 |
| 26 | runner.py | Tutor 的预算拒绝变成普通失败记录，没有让整个运行停止 | 成立 | 未触发：Tutor 唯一一次失败是 `TUTOR_CITATION_MISMATCH` |
| 27 | runner.py | 重定向时会把 Bearer token 转发出去 | 成立 | 未触发：本机，没有重定向 |
| 28 | runner.py | START 成功后 READ 失败，Study 不会写失败记录 | 成立 | 未触发：`verify` 通过 |
| 29 | runner.py | UNCERTAIN 分支的失败记录缺 `cost_nano` | 成立 | 未触发：最终记录中的 84 条失败都带有 `cost_nano` |

### 第 12 条为什么会改变数字

在 2,206 条论断中，同时带 `alone` 和 `needed` 的有 3 条；support 不是 `full` 却有 `needed` 的有 136 条。如果当时用更严的校验器，这些判定会被拒绝并重试，裁判可能给出别的判定，引用精确率和对应的严格分都可能变化。已发布的引用指标按发布时的规则计算，[README](README.md) 已注明引用指标可靠性有限（引用完全支持的一致性 κ 0.44）。

## 未在本文分诊的意见

CodeRabbit 在 PR #80 的后续评论里另有 10 条 Major 和 10 条 Minor，同样针对评测工具，例如 Tutor 预留绑定到单题、揭盲前校验映射值、`FREEZE.json` 的原子发布和权限。本次没有逐条分诊。它们与上表一样，留给下一个工具版本处理。

## 复算命令

在私有目录的副本上运行，不写入原目录。媒体、素材和密钥没有复制。

```bash
cd agent-service
.venv/bin/python -m lecturelens_real_eval.l4.cli --root <copy> verify --split holdout --sources rep1,rep2,rep3
.venv/bin/python -m lecturelens_real_eval.l4.cli --root <copy> score --split holdout --label l5-recompute --sources rep1,rep2,rep3
sha256sum <copy>/judge/holdout/final/rows-*.json <copy>/judge/holdout/l5-recompute/rows-*.json
```
