# P1-4 第①提交：角色、权限、迁移与加密基础

本次仅完成第①阶段。实现及后续边界见 [系统模型管理](../../../docs/SYSTEM_MODEL_MANAGEMENT.md)；运行时解析、ASR 切换和前端仍待后续提交。没有调用真实供应商，没有部署、push 或重启线上服务。

## 实现与结果

- USER/ADMIN、注册固定 USER、注册拒绝角色注入；JWT 签入角色并兼容旧令牌。管理授权每次读取数据库，撤权立即生效。
- 管理路径统一拦截，当前开放只读 capabilities 接口；测试覆盖 401、403、管理员成功以及全部变更 HTTP 方法的拦截边界。
- Flyway V25 新增配置基础表，版本及审计由数据库拒绝修改/删除。执行快照没有凭据列，不创建 probe_record 表。
- AES-256-GCM、随机 nonce、用途/对象 AAD；公开投影只含是否有密钥及后四位。离线 CLI 在同一事务更新角色并写审计。

Java 全量 **1,496 项通过，0 失败、0 错误、0 跳过**，共 218 个 suite。其中加密 24 项、管理员边界 10 项、真实 MySQL 9 项。MySQL 8.4.11 验证空库完整迁移与 V24 存量账号/任务升级，包含角色/协议约束、密文落库、不可变历史、CLI 审计回滚及删除级联。

打包通过；CLI 脚本真实执行到 Java main，无参数返回预期用法错误码 2；shell 语法和 diff 检查通过。最终日志及 JUnit XML 的两个合成模型密钥 canary 扫描无匹配。数据库容器及其匿名数据卷已经清理。

本次没有修改 Python 或前端，未运行其全量测试/Ruff/构建；这些检查留待总验收。上述数字是执行与安全机制测试，不是模型任务质量或真实 DeepSeek/ASR 可用性结论。

## 原始记录与失败保留

[results.json](results.json) 保存结果、命令、退出码及原始路径；[RAW_SHA256SUMS](RAW_SHA256SUMS) 校验本机 `.data/system-model-management/phase1/` 中的完整日志与 XML；`SHA256SUMS` 列出本次改动文件和公开结果的哈希，不包含清单自身。

- `backend-full.log`、`full-reports/`：最终完整 Java 运行的 stdout/stderr 和 218 份对应 XML。没有混入 target 中先前遗留、未在本次运行的报告。
- `package.log`、`cli-usage.log`、`additional-checks.json`：打包、CLI 启动、shell 与 diff 检查。
- `secret-canary-scan.json`：最终日志和 XML 的凭据 canary 扫描。
- `infrastructure.json`：MySQL 版本与本任务容器清理记录。
- `focused-initial.log`：首次 Surefire 选择器未匹配测试，保留该命令失败。
- `focused.log`、`focused-reports/`：首轮针对性测试失败记录。新断言受到既有共享 mock 调用历史影响；临时数据库未显式采用项目 `utf8mb4_unicode_ci`，在历史 V13 外键处失败。已修正测试夹具，未改 V1–V24，未修复或删除迁移历史。最终全量运行重新验证了相关断言。

原始记录在 Git 忽略目录内；公开清单不包含日志内容、密钥、数据库密码或下载媒体。最终 VERIFY.md 在第④提交汇总所有阶段。

## 复现测试

从仓库根目录创建独立测试 MySQL。以下密码只用于本地临时容器，不是部署凭据：

```bash
docker run --detach --name lecturelens-p14-phase1-mysql \
  --env MYSQL_ROOT_PASSWORD=p14-local-test-only \
  --env MYSQL_DATABASE=lecturelens_system_model_test \
  --publish 127.0.0.1::3306 mysql:8.4
task_mysql_test_address="$(docker port lecturelens-p14-phase1-mysql 3306/tcp)"
task_mysql_test_port="${task_mysql_test_address##*:}"
export SYSTEM_MODEL_TEST_JDBC_URL="jdbc:mysql://127.0.0.1:${task_mysql_test_port}/lecturelens_system_model_test?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
export SYSTEM_MODEL_TEST_MYSQL_PASSWORD=p14-local-test-only
```

等待该容器 ready，再运行：

```bash
cd backend
bash ./mvnw -B test
bash ./mvnw -B -DskipTests package
cd ..
bash -n scripts/admin/system-model-admin.sh
git diff --check
# 无参数调用预期打印用法并退出 2；实际 grant/revoke 已由真实 MySQL 测试执行。
bash scripts/admin/system-model-admin.sh
docker rm --force --volumes lecturelens-p14-phase1-mysql
```

测试自行分配随机名称的数据库并清理，只接受 loopback 地址及以 `_test` 结尾的基准库，不对传入的基准库迁移或清理。无需启动 Java HTTP 服务或任何真实 AI 服务。

## 复算本次数字与哈希

以下命令从本次归档 XML 复算全量及相关 suite 数字，并核对公开结果；也复算 canary 扫描文件数和结果、核对附加命令记录：

```bash
python3 - <<'PY'
from pathlib import Path
import json
import re
import xml.etree.ElementTree as ET

raw = Path('.data/system-model-management/phase1')
summary = json.loads(Path('eval/system-model-management/phase1/results.json').read_text())
log = (raw / 'backend-full.log').read_text()
names = re.findall(r'^\[INFO\] Running (\S+)', log, re.M)
totals = dict.fromkeys(('tests', 'failures', 'errors', 'skipped'), 0)
relevant = []
for name in names:
    suite = ET.parse(raw / 'full-reports' / ('TEST-' + name + '.xml')).getroot()
    counts = {key: int(suite.attrib[key]) for key in totals}
    for key in totals:
        totals[key] += counts[key]
    if '.systemmodel.' in name or '.auth.' in name:
        relevant.append({'name': name, **counts})
assert len(names) == summary['backend_full']['suite_count']
assert all(value == summary['backend_full'][key] for key, value in totals.items())
assert relevant == summary['relevant_suites']
assert '[INFO] BUILD SUCCESS' in log
files = [raw / 'backend-full.log', *sorted((raw / 'full-reports').glob('TEST-*.xml'))]
canaries = [b'test-only-opaque-model-secret-9347', b'test-only-database-secret-8472']
matches = [str(path) for path in files if any(key in path.read_bytes() for key in canaries)]
assert len(files) == summary['credential_log_scan']['files_scanned']
assert matches == summary['credential_log_scan']['matching_files'] == []
assert json.loads((raw / 'additional-checks.json').read_text()) == summary['additional_checks']
assert '[INFO] BUILD SUCCESS' in (raw / 'package.log').read_text()
assert 'Ver 8.4.11' in json.loads((raw / 'infrastructure.json').read_text())[0]['output']
print({'suite_count': len(names), **totals})
print(relevant)
PY
sha256sum -c eval/system-model-management/phase1/SHA256SUMS
sha256sum -c eval/system-model-management/phase1/RAW_SHA256SUMS
```

重新运行测试可复现断言和计数；时间戳与随机 ID 会改变日志字节。哈希清单验证本次冻结文件，不要求新运行产生相同日志哈希。后续提交修改相同源码后，源码哈希对应本阶段提交中的文件。
