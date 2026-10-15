# P1-4 第③提交验收

本阶段实现 ASR 运行时切换。没有 push、部署、重启线上服务或真实供应商调用。管理员页面、主动连通性测试与全项目聚合验收仍属于第④阶段；本次结果验证执行机制，不代表真实识别质量。

## 实现与兼容

- 系统层启用后注册百炼、SiliconFlow 两个工厂，替代启动时唯一真实 provider；关闭时继续原 Spring provider/enabled/Mock 条件选择。
- `ASR_TRANSCRIPTION` 只接受 BAILIAN_ASR/SILICONFLOW_ASR 协议及 ASR 能力。任务创建时冻结路由和非密钥选项；执行时按不可变版本解密凭据，快照不复制明文或密文。
- Pipeline 在内嵌字幕未命中后创建一次任务适配器，显式传给单文件、并发分片、重试和合并。合并结果校验所有分片的快照来源一致，并保留版本与快照 ID。每次分片/重试仍检查任务权属、可见性及取消状态。
- 无绑定沿用显式 provider 优先、单个旧 enabled、Mock/none 语义；环境默认及 Mock 文本随版本冻结。数据库绑定失败不回退 Mock。部署分片约束与供应商大小上限同时生效，数据库 maxAttempts 可覆盖分片重试次数。
- 数据库 ASR 共用有界二进制 POST，禁止代理和重定向，检查最终地址的全部解析 IP；百炼同步端点/WAV/模型限制与 SiliconFlow 固定转写路径保留。错误只携带封闭类别、状态和可重试标记，不保留原始消息/响应/异常链。
- 不修改 Flyway 历史迁移或表结构。非密钥 ASR 选项写入现有版本/快照 JSON，版本冲突、审计、Redis 通知和任务开始前数据库版本校验复用第②阶段机制。其他文本/视觉绑定与 Python decision/review 不变。

已知限制：DNS 检查不固定连接 IP；第②阶段已冻结但不含 ASR 的旧快照不能补推凭据，升级前须排空，执行外部 ASR 时明确报快照无效。无快照旧任务按 ADOPTED 规则冻结。分片时长仍由部署设置，切换供应商不会自动调整，超限明确失败。详见[当前配置行为](../../../docs/SYSTEM_MODEL_MANAGEMENT.md#asr-运行时选择)。

改动文件与 SHA-256 见 [SHA256SUMS](SHA256SUMS)。本清单对应本阶段提交；第①、②阶段清单应分别在对应提交校验。

## 验收证据

Java 全量 **1,571 项通过，0 失败、0 错误、0 跳过**，223 个 suite；真实 MySQL 54 项，其中 ASR 24 项。定向回归 280 项通过。打包与 diff 检查通过。最终日志、XML 和脱敏观测共 231 个文件，10 个供应商/主密钥合成 canary 的匹配为 0。

最终数字、suite 清单、请求地址和版本观测均在 [results.json](results.json)，原始记录的哈希见 [RAW_SHA256SUMS](RAW_SHA256SUMS)。最终 ASR 观测来自补充 scenario 字段后的 24 项窄范围重跑；生产代码与全量通过时相同，全量原始 XML 独立归档。没有把重复执行次数加到全量用例数中。

A 冻结版本 31，两个并发分片加一次 429 重试共 3 个请求均使用百炼；B 版本 32 的两个请求使用 SiliconFlow；回滚后的 C 版本 33 使用百炼。8 条最终 ASR 请求观测还包括两种协议各一次序列化验证，全部为 Mock HTTP。

| 验收点 | 测试依据 |
| --- | --- |
| 两工厂同时注册、唯一 ASR 入口；原条件选择不退化 | `SystemModelRuntimeMySqlTest.enabledRuntimeBootstrapsAndSelectsRoutingProviders`，`AsrProviderSelectionTest` |
| A 运行中切换，B 使用新供应商，A 并发分片及 429 重试继续原版本，合并保留版本 | `SystemModelAsrMySqlTest.concurrentChunksRetriesAndMergeStayOnAWhileNewTaskUsesBThenRollbackCreatesC`；实际 Pipeline/适配器 + Mock HTTP + 独立真实 MySQL |
| 回滚生成新版本且只影响新任务；其他功能有效配置相同 | 同上；逐项比较除 ASR 外全部有效配置；自动接管 A 仍读取原引用 |
| 漏 Redis 通知仍读取最新数据库版本；并发 expectedVersion 仅一个成功 | 同上模拟通知抛错；`concurrentExpectedVersionSavesHaveExactlyOneWinner`；没有启动多实例 |
| 百炼与 SiliconFlow 的最终请求地址、模型、凭据、超时及正文协议正确 | `realAdaptersSerializeFrozenEndpointModelAndCredentialsWithoutMakingNetworkCalls`；百炼完整同步地址，SiliconFlow `/v1/audio/transcriptions` |
| 400/401/403/404/408/429/500、错误模型、无效 JSON、超时、无法解密均失败且不回退 Mock | `httpFailuresAreExplicitAndNeverFallBackToConfiguredMock`、`invalidBailianModelFailsWithoutHttpOrFallback`、`invalidJsonAndTimeoutDoNotUseMockOrExposePayload`、`undecryptableCredentialFailsBeforeAnyAdapterHttpAndDoesNotFallback` |
| 代理/重定向/大小/慢响应体边界与二进制上传 | `SystemModelHttpClientTest`；`boundedTransportRejectionIsNonRetryableForBothAdapters`；`dnsChangeToMixedPublicAndPrivateAddressesIsRejectedBeforeHttp` |
| 无绑定保留环境及 Mock/none；旧快照不受环境文本或 provider 改动影响 | `unboundEnvironmentProviderAndEnabledFlagsRetainFrozenKeyAndSettings`、`mockAndDisabledDefaultsAreFrozenAndExplicitProviderWinsLegacyFlags` |
| 密钥轮换、当前对象删除不改变旧任务；回滚 null 绑定恢复部署默认 | `rotationDeletionAndRollbackToDeploymentDefaultDoNotChangeOldTaskCredentials` |
| 快照无凭据，历史/执行查询只显示掩码；权限回归 | ASR 序列化测试逐个比对密文；第②阶段全管理接口 401/403/管理员及密文排除测试继续通过 |
| 取消/任务范围仍校验；内嵌字幕优先；分片边界、合并、重试回归 | `taskScopeAndCancellationAreCheckedByPinnedAdapter`、`TranscribeAudioStepTest` 及 Java 全量套件 |

## 复现命令

使用独立本机 MySQL 8.4，不能指向现有业务库。以下密码仅用于新建临时测试容器。测试只接受 loopback 及 `_test` 基准库，自行创建/删除随机临时库，不迁移传入的基准库。

```bash
mkdir -p .data/system-model-management
# 若名称已占用，先选择另一个名称，勿删除他人容器。
docker run --detach --name lecturelens-p14-phase3-mysql \
  --env MYSQL_ROOT_PASSWORD=p14-local-test-only \
  --env MYSQL_DATABASE=lecturelens_system_model_test \
  --publish 127.0.0.1::3306 mysql:8.4 \
  --innodb-flush-log-at-trx-commit=2 --sync-binlog=0 --skip-log-bin
task_asr_mysql_address="$(docker port lecturelens-p14-phase3-mysql 3306/tcp)"
task_asr_mysql_port="${task_asr_mysql_address##*:}"
export SYSTEM_MODEL_TEST_JDBC_URL="jdbc:mysql://127.0.0.1:${task_asr_mysql_port}/lecturelens_system_model_test?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
export SYSTEM_MODEL_TEST_MYSQL_USER=root
export SYSTEM_MODEL_TEST_MYSQL_PASSWORD=p14-local-test-only
export SYSTEM_MODEL_VERIFICATION_DIR="$(mktemp -d "$PWD/.data/system-model-management/replay-phase3.XXXXXX")"
```

等待该容器 ready，然后从仓库根目录运行：

```bash
cd backend
# 定向测试（本次通过记录：phase3/targeted-fourth.log）
bash ./mvnw -B '-Dtest=SystemModel*Test,*Asr*Test,SpeechToTextProviderTest,TranscribeAudioStepTest' test \
  > "$SYSTEM_MODEL_VERIFICATION_DIR/targeted.log" 2>&1
# 另选空目录保存全量观测，避免重复追加。
export SYSTEM_MODEL_VERIFICATION_DIR="$(mktemp -d "$PWD/../.data/system-model-management/replay-phase3-full.XXXXXX")"
bash ./mvnw -B test > "$SYSTEM_MODEL_VERIFICATION_DIR/backend.log" 2>&1
bash ./mvnw -B -DskipTests package > "$SYSTEM_MODEL_VERIFICATION_DIR/package.log" 2>&1
cd ..
git diff --check
docker exec lecturelens-p14-phase3-mysql mysql --version
docker rm --force --volumes lecturelens-p14-phase3-mysql
```

全量日志：`.data/system-model-management/phase3/backend-full-final.log`；该次匹配的 JUnit XML：`full-final-reports/`；请求观测：`observations-final/`，补充 ASR 观测为 `asr-receipts-final/`；窄范围日志/XML 为 `asr-receipts-final.log` / `asr-receipts-final.xml`；打包：`package-final.log`；检查及测试容器记录：`checks.json`。这些位置均相对于仓库根目录下 `.data/system-model-management/phase3/`（全量日志已写完整路径）。原始日志不提交 Git。

初次编译变量重名、测试夹具缺少路由、WAV 分片夹具大小设置错误，以及测试删除方法名称错误的失败均保留于 `compile-first.log`、`targeted-first.log`、`targeted-second.log`、`targeted-third.log`，不计为通过。`compile-second.log` 与 `targeted-fourth.log` 为后续通过记录。

Python/PostgreSQL、Ruff 和前端测试/构建未在本阶段运行：本次只修改 Java 及文档，最终跨项目聚合验收留在第④阶段。没有真实 ASR/DeepSeek 请求，没有识别质量评测。

复算本次每个数字、版本与最终地址（从仓库根目录运行；需要本机保留的原始记录）：

```bash
python3 - <<'PY'
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET

raw = Path('.data/system-model-management/phase3')
summary = json.loads(Path('eval/system-model-management/phase3/results.json').read_text())
keys = ('tests', 'failures', 'errors', 'skipped')
log = (raw / 'backend-full-final.log').read_text()
names = re.findall(r'^\[INFO\] Running (\S+)', log, re.M)
totals = dict.fromkeys(keys, 0)
suites = []
for name in names:
    root = ET.parse(raw / 'full-final-reports' / ('TEST-' + name + '.xml')).getroot()
    counts = {key: int(root.attrib[key]) for key in keys}
    for key in keys:
        totals[key] += counts[key]
    if '.systemmodel.' in name:
        suites.append({'name': name, **counts})
assert len(names) == summary['backend_full']['suite_count']
assert totals == {key: summary['backend_full'][key] for key in keys}
assert suites == summary['system_model_suites']
assert sum(s['tests'] for s in suites if s['name'].endswith(
    ('SystemModelMySqlIntegrationTest', 'SystemModelRuntimeMySqlTest',
     'SystemModelAsrMySqlTest'))) == summary['real_mysql_tests']
for filename, field in [('backend-full-final.log', 'backend_full'),
                        ('targeted-fourth.log', 'targeted'),
                        ('asr-receipts-final.log', 'receipt_verification')]:
    text = (raw / filename).read_text()
    match = re.findall(r'^\[INFO\] Tests run: (\d+), Failures: (\d+), Errors: (\d+), Skipped: (\d+)\s*$', text, re.M)
    assert len(match) == 1
    assert dict(zip(keys, map(int, match[0]))) == {key: summary[field][key] for key in keys}
    assert '[INFO] BUILD SUCCESS' in text
receipt_xml = ET.parse(raw / 'asr-receipts-final.xml').getroot()
assert {key: int(receipt_xml.attrib[key]) for key in keys} == {
    key: summary['receipt_verification'][key] for key in keys}
rows = [json.loads(line) for line in (raw / 'asr-receipts-final/asr-requests.jsonl').read_text().splitlines()]
assert rows == summary['asr_mock_requests']
assert len(rows) == 8
switch = summary['asr_mock_version_switch']
assert [r['version'] for r in switch] == [31, 32, 33]
assert [r['provider'] for r in switch] == ['bailian', 'siliconflow', 'bailian']
for result in switch:
    observed = [row for row in rows if row['snapshotId'] == result['snapshotId']]
    assert len(observed) == result['request_count']
    assert sorted(row['status'] for row in observed) == result['statuses']
    assert all(row['version'] == result['version'] and row['finalUrl'] == result['finalUrl']
               and row['scenario'] == 'runtime-switch' for row in observed)
assert [r['request_count'] for r in switch] == [3, 2, 1]
assert {row['finalUrl'] for row in rows} == {
    'https://silicon.example/v1/audio/transcriptions',
    'https://bailian.example/api/v1/services/aigc/multimodal-generation/generation'}
files = [raw / p for p in ('backend-full-final.log', 'asr-receipts-final.log',
                           'package-final.log', 'asr-receipts-final.xml')]
files += sorted((raw / 'full-final-reports').glob('TEST-*.xml'))
files += sorted((raw / 'observations-final').glob('*.jsonl'))
files += sorted((raw / 'asr-receipts-final').glob('*.jsonl'))
canaries = [b'synthetic-env-text-key-5531', b'synthetic-env-vision-key-6942',
            b'synthetic-provider-a-key-1984', b'synthetic-provider-b-key-2756',
            b'synthetic-http-test-key', b'test-only-opaque-model-secret-9347',
            b'test-only-database-secret-8472', b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=',
            b'synthetic-asr-a-key-1264', b'synthetic-asr-b-key-9857']
assert len(files) == summary['credential_log_scan']['files_scanned']
assert len(canaries) == summary['credential_log_scan']['canary_count']
assert not [str(p) for p in files if any(key in p.read_bytes() for key in canaries)]
assert '[INFO] BUILD SUCCESS' in (raw / 'package-final.log').read_text()
assert json.loads((raw / 'checks.json').read_text()) == summary['checks']
assert all(check['exit_code'] == 0 for check in summary['checks'])
print({'suites': len(names), **totals, 'real_mysql_tests': summary['real_mysql_tests']})
print(switch)
PY
sha256sum -c eval/system-model-management/phase3/SHA256SUMS
sha256sum -c eval/system-model-management/phase3/RAW_SHA256SUMS
```

新复跑的随机 snapshot ID 不同，数据库版本号随测试顺序变化；上述精确数字和 ID 对应本次冻结原始记录。新复跑应验证 A < B < C、A 的全部请求使用同一版本、B 切换供应商、C 恢复原绑定的关系，而不把编号本身作为业务契约。
