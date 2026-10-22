# P1-4 第②提交验收

本阶段实现 Java 文本/视觉解析、全文/逐段翻译独立绑定、不可变配置版本与执行快照。系统层默认关闭；没有 push、部署、重启线上服务或真实供应商调用。ASR 动态切换、管理员前端、主动连通性测试及最终聚合验收仍在后续阶段。

## 改动与存储边界

- `systemmodel/` 新增受管理员保护的供应商、模型、绑定、回滚、版本、审计与执行查询，以及版本存取、快照和直接 Chat Completions 传输。
- 新增 `SYSTEM_MODEL_CONFIG_ENABLED`；启用时缺少环境主密钥直接启动失败，关闭时保留原路径。启用仍要求 Flyway；没有新增或修改历史迁移。
- 配置完整版本存加密凭据；执行快照只有版本号及无凭据解析结果。普通任务创建时冻结，恢复沿用原引用；问答、章节和手动资料按操作冻结，修订继续同一版本。
- 文本/视觉、翻译、任务创建和 runner 显式传递引用，不把密钥放进请求 metadata、ThreadLocal 或快照。历史和执行查询一律经过专用 DTO 投影，不透传存储 JSON、密文、环境指纹或凭据内部引用。
- 新数据库地址只追加 `/chat/completions`；数据库绑定的 JSON 请求不降级纯文本。无绑定继续原环境语义；系统层要求关闭 LangChain4j，该独立旧路径的默认关闭状态不变。
- Redis 提交后通知缓存失效；快照创建读数据库版本并发锁。原取消、owner、generation fence 和发布边界保留。
- 部署、架构、API、数据库、用户模型管理和环境模板同步更新，Python decision/review 与前端用户页未修改。

完整改动文件及其 SHA-256 见 [SHA256SUMS](SHA256SUMS)；当前行为与 API 请求说明见 [系统模型管理](../../../docs/SYSTEM_MODEL_MANAGEMENT.md)。该清单对应本阶段提交；第①阶段源码哈希应在其提交 `91fcb31` 上校验。

## 结果与证据

Java 全量 **1,546 项通过，0 失败、0 错误、0 跳过**，222 个 suite。真实 MySQL **30 项**，分别为第①阶段存储验证 9 项与当前运行时验证 21 项；另有启动开关 2 项、URL 策略 22 项、HTTP 边界 4 项。打包、shell 语法和 diff 检查通过。

| 验收点 | 可复现证据 |
| --- | --- |
| 启用缺主密钥即启动失败；未启用正常启动 | `SystemModelActivationTest`；有效配置启动/primary provider 选择由 RuntimeMySqlTest 验证 |
| 当前、历史、执行响应没有密文 | `everyManagementEndpointChecksAdminAndQueriesNeverReturnCiphertext`；先轮换凭据，再查旧版本、当前版本、执行列表与详情，并逐个比对所有历史密文 |
| 全文绑定独立、回滚生成新版本 | `changingOnlyFullTranslationPreservesEveryOtherEffectiveRouteAndRollback`；其他有效路由逐项比较 |
| A 运行中保存配置，B 用新版本 | `runningAUsesOldVersionWhileNewBUsesNewVersion`；阻塞 Mock、真实 MySQL 快照及请求/结果观测 |
| 密钥轮换/当前对象删除不改旧快照 | `keyRotationAndDeletingCurrentObjectsDoNotChangeExistingExecution` |
| 全文、逐段各自命中绑定 | `actualFullAndSegmentTranslationHitIndependentBindings`；实际翻译服务执行，各运行于对应部署模式 |
| 视觉走冻结凭据、图片消息与精确 URL | `visualCallsUseFrozenIndependentKeyAndExactEndpoint` |
| 漏 Redis 通知、并发保存冲突 | `missedRedisNotificationStillFreezesCurrentDatabaseVersion`、`concurrentSavesHaveExactlyOneWinner`；仅同进程内模拟独立缓存，未启动多实例 |
| 任务与快照同事务、发送前已冻结 | `pipelineCreationAndSnapshotRollbackTogether`、`TaskCreationServiceTest.enabledSystemModelsFreezeBeforePublishingCreatedTask` |
| 401/404/429/500、无效 JSON、无法解密 | 参数化错误用例；不走备用供应商、不返回原始错误，错误主密钥在网络之前失败 |
| 超时包含慢响应体、响应超限、不跟随重定向、不使用默认代理 | `SystemModelHttpClientTest` 的本机短 HTTP 夹具；地址策略另测全部解析 IP 和 IPv4/IPv6 私网 |
| 无绑定、Mock、越权、取消与删除 | RuntimeMySqlTest 对应用例，加全量原链路回归 |

本轮是配置、执行和协议机制验收，不是 DeepSeek/ASR 真实可用性或学习任务质量评测，没有消费保留集。没有改 Python/前端，未在本阶段运行 Python/PostgreSQL、Ruff 和前端全量；总验收另行汇总。

## 最终请求地址与冻结版本

以下来自 `observations-final/requests.jsonl` 的实际 Mock transport 入参，不是向这些公网地址发出的真实请求。各场景使用独立夹具；模型 ID 是测试占位名称。

| 场景 | 模型 | 最终地址 | 输出契约 |
| --- | --- | --- | --- |
| 运行中的 A | translation-a | `https://api.deepseek.com/chat/completions` | json_object |
| 修改配置后的 B | translation-b | `https://other.example/v1/chat/completions` | json_object |
| 全文模式 | full-text | `https://api.deepseek.com/chat/completions` | json_object |
| 逐段模式 | segments | `https://other.example/v1/chat/completions` | 原有纯文本 |
| 视觉 | vision-model | `https://api.deepseek.com/chat/completions` | 图片消息 + json_object |
| 无绑定环境默认 | legacy-model | `https://legacy.example/v1/chat/completions` | 原有默认路径 |

`versions.jsonl` 记录 A 的冻结/实际版本均为 **28**，B 均为 **29**，包含对应快照 ID 供本机对照。版本号是本次观测，不要求其他运行产生同一编号；必须满足 A/B 各自一致且 B 晚于 A。请求记录只保存模型、地址、协议及密钥掩码，不保存 Authorization 或提示词。

## 原始记录与哈希

[results.json](results.json) 是公开结果；[RAW_SHA256SUMS](RAW_SHA256SUMS) 列出本机 Git 忽略目录 `.data/system-model-management/phase2/` 的原始文件哈希。

- `backend-full-final.log`、`full-final-reports/`：最终全量输出及本次匹配的 222 份 XML，没有合并 target 中的旧报告。
- `observations-final/requests.jsonl`、`versions.jsonl`：脱敏 Mock 请求与 A/B 结果，共 6 条请求、2 条版本结果。
- `secret-canary-scan.json`：扫描最终日志、XML 和观测，共 225 个文件；8 个合成模型/主密钥 canary 无匹配。该检查针对合成夹具，不宣称替代任意真实凭据的泄漏审计。
- `package-final.log`、`checks.json`：最终打包和常规检查。
- `infrastructure.json`：独立 MySQL 8.4.11 版本及本任务容器/匿名卷清理回执。
- `compile-initial.log` 保留最初 lambda 捕获编译失败；修正后才执行测试。`focused-initial.log`、`focused-network.log` 和 `backend-full-initial.log` 保留前面的成功运行，最终数字只取 final 记录。

原始记录、临时容器凭据及媒体不提交 Git。SHA 清单验证本次冻结文件，重新运行的时间戳、UUID 和版本号允许变化。

## 复现运行

从仓库根目录创建独立本机 MySQL。密码仅用于本地测试容器：

```bash
mkdir -p .data/system-model-management
docker run --detach --name lecturelens-p14-phase2-mysql \
  --env MYSQL_ROOT_PASSWORD=p14-local-test-only \
  --env MYSQL_DATABASE=lecturelens_system_model_test \
  --publish 127.0.0.1::3306 mysql:8.4 \
  --innodb-flush-log-at-trx-commit=2 --sync-binlog=0 --skip-log-bin
task_mysql_test_address="$(docker port lecturelens-p14-phase2-mysql 3306/tcp)"
task_mysql_test_port="${task_mysql_test_address##*:}"
export SYSTEM_MODEL_TEST_JDBC_URL="jdbc:mysql://127.0.0.1:${task_mysql_test_port}/lecturelens_system_model_test?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
export SYSTEM_MODEL_TEST_MYSQL_PASSWORD=p14-local-test-only
export SYSTEM_MODEL_VERIFICATION_DIR="$(mktemp -d "$PWD/.data/system-model-management/replay-phase2.XXXXXX")"
```

等待该容器 ready。Java 测试自行创建随机名称测试库并清理，只接受 loopback 及 `_test` 基准库，不迁移或清理传入的基准库：

```bash
cd backend
bash ./mvnw -B test > "$SYSTEM_MODEL_VERIFICATION_DIR/backend.log" 2>&1
bash ./mvnw -B -DskipTests package > "$SYSTEM_MODEL_VERIFICATION_DIR/package.log" 2>&1
cd ..
bash -n scripts/admin/system-model-admin.sh
git diff --check
docker rm --force --volumes lecturelens-p14-phase2-mysql
```

复算本次全部数字与最终地址：

```bash
python3 - <<'PY'
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET

raw = Path('.data/system-model-management/phase2')
summary = json.loads(Path('eval/system-model-management/phase2/results.json').read_text())
log = (raw / 'backend-full-final.log').read_text()
names = re.findall(r'^\[INFO\] Running (\S+)', log, re.M)
totals = dict.fromkeys(('tests', 'failures', 'errors', 'skipped'), 0)
suites = []
for name in names:
    suite = ET.parse(raw / 'full-final-reports' / ('TEST-' + name + '.xml')).getroot()
    counts = {key: int(suite.attrib[key]) for key in totals}
    for key in totals:
        totals[key] += counts[key]
    if '.systemmodel.' in name:
        suites.append({'name': name, **counts})
assert len(names) == summary['backend_full']['suite_count']
assert all(value == summary['backend_full'][key] for key, value in totals.items())
assert suites == summary['system_model_suites']
assert sum(s['tests'] for s in suites if s['name'].endswith(
    ('SystemModelMySqlIntegrationTest', 'SystemModelRuntimeMySqlTest'))) == summary['real_mysql_tests']
requests = [json.loads(line) for line in (raw / 'observations-final/requests.jsonl').read_text().splitlines()]
versions = [json.loads(line) for line in (raw / 'observations-final/versions.jsonl').read_text().splitlines()]
assert requests == summary['mock_requests']
assert [{k: v for k, v in row.items() if k != 'snapshotId'} for row in versions] == summary['mock_version_switch']
assert all(v['frozenVersion'] == v['observedVersion'] for v in versions)
assert versions[0]['frozenVersion'] < versions[1]['frozenVersion']
assert 'https://api.deepseek.com/chat/completions' in {r['finalUrl'] for r in requests}
files = [raw / 'backend-full-final.log', *sorted((raw / 'full-final-reports').glob('TEST-*.xml')),
         *sorted((raw / 'observations-final').glob('*.jsonl'))]
canaries = [b'synthetic-env-text-key-5531', b'synthetic-env-vision-key-6942',
            b'synthetic-provider-a-key-1984', b'synthetic-provider-b-key-2756',
            b'synthetic-http-test-key', b'test-only-opaque-model-secret-9347',
            b'test-only-database-secret-8472', b'AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA=']
assert len(files) == summary['credential_log_scan']['files_scanned']
assert len(canaries) == summary['credential_log_scan']['canary_count']
assert not [str(p) for p in files if any(key in p.read_bytes() for key in canaries)]
assert '[INFO] BUILD SUCCESS' in log and '[INFO] BUILD SUCCESS' in (raw / 'package-final.log').read_text()
assert json.loads((raw / 'checks.json').read_text()) == summary['checks']
assert 'Ver 8.4.11' in summary['test_infrastructure'][0]['output']
print({'suite_count': len(names), **totals, 'real_mysql_tests': summary['real_mysql_tests']})
print(versions)
print(requests)
PY
sha256sum -c eval/system-model-management/phase2/SHA256SUMS
sha256sum -c eval/system-model-management/phase2/RAW_SHA256SUMS
```

已知网络局限保留在部署文档：DNS 检查与连接之间没有固定 IP 的重绑定防护，符合本阶段确认的简化方案。
