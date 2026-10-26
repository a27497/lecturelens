# 实际检查命令与结果

所有长检查经以下同一包装器运行（命令参数完整在下表重建；监督器只存argv hash，不含环境/凭据）：

```text
python3 /home/dev/projects/lecturelens/scripts/dev/run_check.py
  --name NAME --cwd CWD
  --output-root /home/dev/projects/lecturelens-p6-validation/.data/dev-checks
  --timeout SECONDS -- CHILD_ARGV
```

R=`/home/dev/projects/lecturelens-p6-validation`。各次终态/原始输出在`evidence/supervised-checks/NAME/{run.json,output.txt}`，摘要`evidence/check-summary.json`；都已确认cleanup.complete=true，非只有tool session结束。数据库URL均仅显式传AGENT_TEST_DATABASE_URL，不包含Provider或生产凭据。

| NAME | CWD / 数据库（127.0.0.1:25486，user=p6） | CHILD_ARGV / timeout | 实际结果 |
| --- | --- | --- | --- |
| p6-existing-python | R/agent-service / lecturelens_p6_regression_test | `.venv/bin/python -m pytest -q --junitxml=../eval/p6-feedback-correction/evidence/existing-python.xml` / 600 | 测试库名称门禁setup error；经核验supervisor PID/start ticks发SIGTERM，CANCELLED 143，62.04秒；无完整pytest计数/无XML，不算通过 |
| p6-existing-python-02 | R/agent-service / lecturelens_agent_test | `.venv/bin/python -m pytest -q --junitxml=../eval/p6-feedback-correction/evidence/existing-python-02.xml` / 600 | **845 passed，0 failed，0 errors，0 skipped**，219.21秒；2个现有依赖警告 |
| p6-mechanism-01 | R / lecturelens_p6_test | `agent-service/.venv/bin/python eval/p6-feedback-correction/mock_flow.py --output eval/p6-feedback-correction/evidence/trial-01` / 180 | 6个脚本trial成功；早期无final_evidence侧表 |
| p6-mechanism-02 | 同上 | 同上，输出trial-02 / 180 | 6个脚本trial成功；补显式证据理由 |
| p6-mechanism-final | 同上 | 同上，输出trial-03 / 180 | 6个脚本trial成功；模块/runner哈希 |
| p6-mechanism-binding | 同上 | 同上，输出trial-04 / 180 | 6个脚本trial成功；来源绑定 |
| p6-mechanism-review-final | 同上 | 同上，输出trial-05 / 180 | **最终6个脚本trial成功**，11 Run、44确定性调用、28工具；无外部Provider调用 |
| p6-new-tests-01 | R / lecturelens_p6_test | `agent-service/.venv/bin/python -m pytest -q eval/p6-feedback-correction/tests --junitxml=eval/p6-feedback-correction/evidence/new-tests-01.xml` / 180 | 28 passed，0 skipped |
| p6-new-tests-02 | 同上 | 同上，XML=new-tests-02.xml / 180 | 30 passed、1 failed、0 skipped；分页测试夹具没有显式开启本地反馈开关。保留XML与输出 |
| p6-new-tests-final | 同上 | 同上，XML=new-tests-final.xml / 180 | 31 passed、0 skipped |
| p6-new-tests-reviewed | 同上 | 同上，增加`--p6-manifest=eval/p6-feedback-correction/evidence/trial-05/manifest.json`，XML=new-tests-reviewed.xml / 180 | 30 passed、4 setup errors、0 skipped；启动过早，部分测试读取时trial-05/export.json尚未落盘。未删失败 |
| p6-new-tests-reviewed-02 | 同上 | 同上，XML=new-tests-reviewed-02.xml / 180 | 确认演练SUCCEEDED和文件存在后运行：**34 passed、0 failed、0 errors、0 skipped**，2.89秒 |

短检查与准备实际执行：

```bash
git fetch origin
git rev-parse origin/main
git worktree add -b codex/p6-feedback-correction-validation /home/dev/projects/lecturelens-p6-validation origin/main
env -i PATH="$PATH" HOME="$HOME" uv sync --frozen --directory agent-service
docker compose -p lecturelens-p6-validation-20261026 -f eval/p6-feedback-correction/compose.yaml up -d --wait
docker exec lecturelens-p6-validation-20261026-postgres-1 createdb -U p6 lecturelens_p6_regression_test
docker exec lecturelens-p6-validation-20261026-postgres-1 createdb -U p6 lecturelens_agent_test
agent-service/.venv/bin/ruff check eval/p6-feedback-correction
agent-service/.venv/bin/ruff format --check eval/p6-feedback-correction
git diff --check
git diff --cached --check -- . ":(exclude)eval/p6-feedback-correction/evidence/**"
agent-service/.venv/bin/python eval/p6-feedback-correction/measure.py verify
```

安装通过；Ruff和格式通过；源码/文档补丁空白检查通过；原样pytest XML/日志含尾随空白，全量`git diff --cached --check`因此报出这些原始记录（未改写），按下列排除证据命令检查源码/文档通过；冻结六份资产hash通过。Ruff开发中执行过`--fix`和format；一处未用测试变量由手工更名修复，不涉及金标准/rubric。只改eval层，未改Java/前端/运行时；未跑Java/前端/浏览器，**BROWSER_NOT_RUN**（两个桌面尺寸均未验收）。

最终独立CLI导出、计分、一致性（均已实际执行，非计划）：

```bash
env -i PATH="$PATH" HOME="$HOME" AGENT_TEST_DATABASE_URL=postgresql://p6@127.0.0.1:25486/lecturelens_p6_test \
  agent-service/.venv/bin/python eval/p6-feedback-correction/measure.py export \
  --input eval/p6-feedback-correction/evidence/trial-05/manifest.json \
  --output eval/p6-feedback-correction/evidence/export-repeated.json
agent-service/.venv/bin/python eval/p6-feedback-correction/measure.py score \
  --input eval/p6-feedback-correction/evidence/export-repeated.json \
  --ratings eval/p6-feedback-correction/example-ratings.json \
  --output eval/p6-feedback-correction/evidence/example-metrics-final.json
agent-service/.venv/bin/python eval/p6-feedback-correction/measure.py agreement \
  --ratings eval/p6-feedback-correction/example-ratings.json \
  --second-ratings eval/p6-feedback-correction/evidence/example-ratings-r2.json \
  --output eval/p6-feedback-correction/evidence/example-agreement.json
docker compose -p lecturelens-p6-validation-20261026 -f eval/p6-feedback-correction/compose.yaml stop
docker compose -p lecturelens-p6-validation-20261026 -f eval/p6-feedback-correction/compose.yaml ps -a
```

独立导出与runner导出JSON逐字段完全相同；模拟双评分为21/22一致、κ=0.9176029963，**不是人类一致性证据**。新容器已Exited(0)，volume保留；未对既有容器发stop/down/exec或写数据。
