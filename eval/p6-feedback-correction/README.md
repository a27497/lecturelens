# P6 反馈订正价值：测量准备

**Mock 数据，不代表教学效果。** 本目录独立于历史冻结评测。main基线核对见[BASELINE.md](BASELINE.md)，研究方案见[PROTOCOL.md](PROTOCOL.md)，主持/学生/双评分表见[FORMS.md](FORMS.md)，最终结果见[REPORT.md](REPORT.md)。不新增产品功能；不依赖PR #47。

- `development/`：CC0合成课程、4个开发任务标准、6种初答场景。
- `holdout/`：独立CC0课程和4个留出任务；没有运行反馈或质量评测。不可把本轮开发调试计为留出结果。
- `FREEZE.json`：在任何P6反馈输出前生成并单独提交的六份资产hash；冻结提交`3fba4a2b20ca1f43e1a05d80545ab1d3d0df83c8`。`rubric.json`含评分与一致性定义。
- `mock_flow.py`：真实Runtime/PostgreSQL、夹具Evidence授权、确定性反馈与脚本学生。包含改对、误导、诚实不足、错误拒答和漏检；远程socket被拒绝。它不加载真实模型路由、Provider配置或生产env。
- `measure.py`：冻结检查、只读全历史导出、来源绑定、导入独立评分、计算描述性指标和双评分一致性。导出限loopback `lecturelens_p6_*_test`，用于隔离研究库；不作为生产/Java网关导出器。
- `example-ratings.json`：6例脚本评分；`evidence/example-metrics-final.json`：对应示例统计；`evidence/example-agreement.json`：**模拟**第二评分者的一处预置分歧，不是真人一致性结果。
- `tests/`：计分错误/边界、冻结与覆盖保护、真实PG导出、24版作答/23版核对分页、版本/权限/来源污染拒绝。
- `evidence/`：各次原始演练、失败与最终测试XML、监督进程终态及日志、文件hash。最终正式演练是`trial-05`；01–04是保留的工程演练，不合并成样本量。没有截图：**BROWSER_NOT_RUN**。

## 重现

从新worktree根目录运行，安装依赖不读部署文件。Docker仅操作此处新建项目，不使用已有容器/volume。下面连接串不含Provider凭据，数据库是新建、loopback、trust认证的本地合成测试库。

```bash
env -i PATH="$PATH" HOME="$HOME" uv sync --frozen --directory agent-service
docker compose -p lecturelens-p6-validation-20261026 -f eval/p6-feedback-correction/compose.yaml up -d --wait
agent-service/.venv/bin/python eval/p6-feedback-correction/measure.py verify
```

本基线不含run_check.py；本次使用原工作区只读包装器（hash见BASELINE），显式把输出指向新worktree。复用此服务器时可用相同绝对路径；在另一环境先取得相同hash的包装器。不要为缺指南而改原工作区。包装器不转发Provider环境。每次检查名称、output目录与XML文件名必须新建。

```bash
AGENT_TEST_DATABASE_URL=postgresql://p6@127.0.0.1:25486/lecturelens_p6_test \
  python3 /home/dev/projects/lecturelens/scripts/dev/run_check.py \
  --name p6-replay-UNIQUE --cwd "$PWD" --output-root "$PWD/.data/dev-checks" --timeout 180 -- \
  agent-service/.venv/bin/python eval/p6-feedback-correction/mock_flow.py \
  --output .data/p6/replay-UNIQUE
```

这一步运行全部六个脚本trial；参数不支持切换真实Provider。失败原始结果在新目录保留；同名目录拒绝覆盖。先看监督进程run.json终态再判断结束。测试默认读取已提交的trial-05清单，因此在全新空数据库中先重放；要运行live测试，使用下面`--p6-manifest`指定刚产生的清单，避免把已提交UUID误当新库数据。

```bash
AGENT_TEST_DATABASE_URL=postgresql://p6@127.0.0.1:25486/lecturelens_p6_test \
  agent-service/.venv/bin/python eval/p6-feedback-correction/measure.py export \
  --input .data/p6/replay-UNIQUE/manifest.json --output .data/p6/export-UNIQUE.json
agent-service/.venv/bin/python eval/p6-feedback-correction/measure.py score \
  --input .data/p6/export-UNIQUE.json --ratings eval/p6-feedback-correction/example-ratings.json \
  --output .data/p6/metrics-UNIQUE.json
```

真人用`data_kind=PILOT`、自己的trial清单、独立评分表，并加`--course eval/p6-feedback-correction/holdout/course.json`和计分的`--standard eval/p6-feedback-correction/holdout/standard.json`。填写FORMS的source_binding。当前没有真人结果；导出不能替代认证Java前后版本核验。

一致性计算：

```bash
agent-service/.venv/bin/python eval/p6-feedback-correction/measure.py agreement \
  --ratings /private/pilot-r1.json --second-ratings /private/pilot-r2.json \
  --standard eval/p6-feedback-correction/holdout/standard.json --output /private/agreement-UNIQUE.json
```

评分/一致性只算数学，不调用模型。新脚本与真实PG测试（清单替换为刚重放的文件）：

```bash
AGENT_TEST_DATABASE_URL=postgresql://p6@127.0.0.1:25486/lecturelens_p6_test \
  python3 /home/dev/projects/lecturelens/scripts/dev/run_check.py \
  --name p6-tests-UNIQUE --cwd "$PWD" --output-root "$PWD/.data/dev-checks" --timeout 180 -- \
  agent-service/.venv/bin/python -m pytest -q eval/p6-feedback-correction/tests \
  --p6-manifest=.data/p6/replay-UNIQUE/manifest.json
```

结束仅停止本项目，保留volume及所有证据：

```bash
docker compose -p lecturelens-p6-validation-20261026 -f eval/p6-feedback-correction/compose.yaml stop
```

没有真实模型执行命令。未来只在用户另行授权调用数和金额后，复用现有feedback评测账本机制创建**新候选/新输出/新留出**；不直接重跑覆盖eval/feedback-v1或phase-completion。
