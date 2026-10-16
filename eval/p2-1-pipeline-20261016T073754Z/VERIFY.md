# P2-1 验证记录（分阶段更新）

设计基线 `a7ad19aebfdf5b56f5212512737c83da414a9339`；用户确认的 DESIGN.md SHA256 为 `1e0636b669eed750b20fe652c3c8ca933ccde08748be93bc3658440c66945946`，保留未修改。仅本地提交，不 push/merge，不部署或重启现有服务，不调用真实供应商。

## 阶段 1：翻译修复

代码和文档改动 **24 个文件**，逐文件路径及结果哈希见 `stages/stage1-files.json`。新增 V27 执行策略表及不可变更新约束，任务创建事务内冻结策略；默认关闭 v2，只对具有冻结策略的任务使用新路径。系统模型配置版本和凭据存储方式不变。

已实现：DeepSeek 全文非 thinking、动态输出预算、length 优先分类、明确空/格式/语言/网络/HTTP 类别、有界拆分和统一物理尝试预算、无隐式 TEXT fallback、原时间区间保留、失败实际基本 usage 携带。输入预算方法为 `UTF8_CONSERVATIVE_V1`，**不是精确 tokenizer**；未下载新依赖或模型，不能用估计 token 计费。

最终相关测试：**252 项，0 失败、0 错误、0 跳过**，包含独立 MySQL 集成测试。当前只是机制验证，不是 DeepSeek 真实译文或 10 次基线通过。

| 轮次 | 测试 / 失败 / 错误 / 跳过 | 说明 |
| --- | --- | --- |
| stage1-unit-01 | 192 / 2 / 0 / 0 | 架构边界失败：响应解码和安全错误类型放错包；移至 LLM 层，未放宽边界检查。 |
| stage1-unit-02 | 192 / 0 / 0 / 0 | 边界修正后通过。 |
| stage1-mysql-01 | 47 / 1 / 0 / 0 | 旧启动测试夹具缺少 P1-3d 新增诊断 Bean；补齐夹具，未改生产 Bean 的必需性。 |
| stage1-combined-03 | 252 / 0 / 0 / 0 | 全部相关单元及独立 MySQL 回归通过，包含新增截止时间及任务诊断测试。 |

MySQL 容器为本任务新建 `lecturelens-p21-mysql-test-20261016`，只监听 `127.0.0.1:33316`，`/var/lib/mysql` 使用 768 MiB tmpfs，内存限制 1536 MiB、CPU 1、日志最多 2 MiB。未连接 demo/acceptance 数据库，未修改受保护容器。首个容器创建因日志驱动“不允许 max-file=1 且开启压缩”失败；仅移除该未启动的本任务容器，显式关闭日志压缩后创建成功。两次记录均保留。数据库测试使用合成凭据，不读取部署环境或供应商 API Key。

安全及兼容证据：

- `SystemModelTranslationV2Test`：真实响应形状的合成空 content + length 优先归 TRUNCATED，并保留 903/3073/3976 原值；DeepSeek 参数、最终 URL、路由上限、逐段/QA 不变；401/404/429/500/408/400 单次物理请求且不泄露合成密钥；ENV 兼容路径不自动转 TEXT。
- `TranslationBatchCoordinatorTest`：截断缩小源文本、空输出一次纠正、认证无重试、网络/429 共用尝试限额、Retry-After 上限、递归总调用上限、拆分深度、未知 usage 预留、开始前/执行中 deadline、动态输出上限和非法配置。
- `PipelineTranslationServiceTest`：真实服务入口复用严格解析/语义校验，拆分后只提交一份完整原段译文。
- `PipelinePolicyMySqlTest`：V27 迁移、策略冻结后配置改变不影响旧任务、关闭开关仍可读取旧策略、owner 隔离、无凭据字段、禁止 UPDATE、任务删除级联。
- 原字幕服务、解析器、prompt、诊断、OpenAI 兼容 provider、任务创建，以及系统模型文本和 ASR 运行时回归同轮通过。

完整日志和各轮执行参数/磁盘采样：

```text
.data/p2-1-pipeline-20261016T073754Z/checks/stage1-unit-01.{log,json}
.data/p2-1-pipeline-20261016T073754Z/checks/stage1-unit-02.{log,json}
.data/p2-1-pipeline-20261016T073754Z/checks/stage1-mysql-01.{log,json}
.data/p2-1-pipeline-20261016T073754Z/checks/stage1-combined-03.{log,json}
.data/p2-1-pipeline-20261016T073754Z/checks/mysql-test-start.json
.data/p2-1-pipeline-20261016T073754Z/checks/mysql-test-start-02.json
.data/p2-1-pipeline-20261016T073754Z/RAW_SHA256SUMS
```

每轮日志哈希、测试结果及启动/结束/峰值磁盘在 `stages/stage1-checks.json`，不依赖后续会覆盖的 target/surefire-reports。MySQL 表中的 media_identity_hash 是上传记录的固定身份摘要，不能冒充媒体文件 SHA256；真实基线仍须核对原 assets.lock.json。

## 数字与哈希复现

下面只读已存证据，不创建任务或调用模型：

```bash
cd /home/dev/projects/lecturelens
sha256sum eval/p2-1-pipeline-20261016T073754Z/DESIGN.md
sha256sum -c eval/p2-1-pipeline-20261016T073754Z/SHA256SUMS
sha256sum -c .data/p2-1-pipeline-20261016T073754Z/RAW_SHA256SUMS
python3 - <<'PY'
import json,re,hashlib
from pathlib import Path
d=Path('eval/p2-1-pipeline-20261016T073754Z')
files=json.loads((d/'stages/stage1-files.json').read_text())
print('stage1_file_count',len(files))
for run in json.loads((d/'stages/stage1-checks.json').read_text()):
    p=Path(run['log_path'])
    assert hashlib.sha256(p.read_bytes()).hexdigest()==run['log_sha256']
    counts=re.findall(r'^\[(?:INFO|ERROR)\] Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)',p.read_text(),re.M)
    print(run['name'],counts[-1],run['execution']['disk_peak_percent'])
PY
```

再次运行相关测试的**命令参数**位于 `stage1-checks.json` 最后一项 execution.command；需先提供独立本地 `_test` 数据库的 `SYSTEM_MODEL_TEST_JDBC_URL` 等测试环境变量。不能使用业务库。示例的 guard runner 只运行指定检查，有 240 秒超时和每秒磁盘检查，超过 85% 结束检查；每轮使用新 name，拒绝覆盖旧日志：

```text
nohup timeout 300 python3 eval/p2-1-pipeline-20261016T073754Z/run_related_checks.py --name stage1-recheck-NEW --timeout 240 -- ./mvnw -o -Dtest=TranslationBatchCoordinatorTest,SystemModelTranslationV2Test,PipelineTranslationServiceTest,TranslationFailureDiagnosticTest,TaskCreationServiceTest,PipelinePolicyMySqlTest,SystemModelRuntimeMySqlTest,SystemModelAsrMySqlTest,TranslationCallDiagnosticsTest,SystemModelTranslationObservationTest,SubtitleTranslationServiceTest,SubtitleTranslationResponseParserTest,SubtitleTranslationPromptFactoryTest,OpenAiCompatibleLlmProviderTest test > NEW-LAUNCHER.log 2>&1 < /dev/null &
```

## 后续验收范围

阶段 2–5、10 次正常基线和 1 次隔离 Java 恢复演示尚未执行。不会把空 trials 或 mock 成功当作真实测量。重启前另报影响范围并等确认；真正实测还受磁盘余量前置约束。

用户补充已纳入实施：**单节费用包含全部 ASR 调用，静音切分引起的调用数量/费用影响单独列出**。仅把“增量”作为差分说明，不能再加到已包含全部 ASR 的总费用上重复计费。若供应商没有返回实际计费单位，明确未知或目录价估算；跨币种没有可信汇率时保留各币种组成，不伪造统一总额。当前阶段未进行费用测量。
