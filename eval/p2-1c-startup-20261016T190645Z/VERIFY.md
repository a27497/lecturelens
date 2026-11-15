# 只读启动机制检查

基准提交 ad244a4。任务中“仅放宽这一条来源，不扩大其他权限”的新授权完整记录在 STARTUP_BOUNDARY.md：已批准的 system-models.env 不再是审批问题，当前边界为额外 runtime.json 来源和支持冻结 JAR 的服务内适配。

本轮只读取 Git 实现、旧 eval 脚本代码，以及 live Python 启动器的 AST/固定符号和路径常量；没有执行或导入它们，没有打开 runtime.json、credential 文件或输出 Environment 值。

实际使用的结构检查包括：

```bash
rg -n -o '\.data/[A-Za-z0-9_./@+-]+\.(json|jar|yml)|[A-Za-z0-9_.-]+\.yml' \
  .data/system-model-management/deploy-20261016/run-backend-new.py
rg -n -o 'sys\.argv|dict\(os\.environ\)|env\.update|os\.execve' \
  .data/system-model-management/deploy-20261016/run-backend-new.py
systemctl show lecturelens-p21c-worker-20261017.service --property=LoadState,MainPID,ActiveState,SubState
systemctl show lecturelens-live-backend.service --property=MainPID,ActiveState,SubState,ExecMainStartTimestampMonotonic
ss -ltn '( sport = :18091 )'
```

AST 解析仅投影已知路径常量与布尔结果，其他字面量省略。所得路径为 `.data/live-access/runtime.json`、`.data/system-model-management/deploy-20261016/backend.jar`、asr-bailian.yml；sys.argv 使用为 false。runtime.json 只检查存在/可读性，未跟读值。

相关源码与原冻结记录校验：

```bash
python3 - <<'PY'
import hashlib, json
from pathlib import Path
x = json.loads(Path('eval/p2-1c-20261016T155847Z/candidate-artifact.json').read_text())
for p in (
    'backend/src/main/java/com/example/courselingo/systemmodel/SystemModelEnvironment.java',
    'backend/src/main/java/com/example/courselingo/systemmodel/SystemModelSecretCipher.java',
    'backend/src/main/java/com/example/courselingo/ai/asr/BailianAsrProperties.java',
):
    assert hashlib.sha256(Path(p).read_bytes()).hexdigest() == x['source_files'][p]
with Path(x['jar_path']).open('rb') as f:
    assert hashlib.file_digest(f, 'sha256').hexdigest() == x['jar_sha256']
print('FROZEN_IDENTITY_PASS')
PY
```

旧 P21Bootstrap 的 selftest/preflight/migrate 入口仅看代码，全部没有执行。尤其不执行 prepare_runtime.py 或 runtime_support.deployment()：其值读取和配置复制逻辑不符合当前权限。指纹缺失也不通过改版本或跳过 requireIdentity 来消除。

preflight.json 保存磁盘字节、未执行状态、冻结身份、175 个原证据文件哈希和既有未提交文件的 inode/size/mtime。closeout.json 再次核验；trials.jsonl 为空。没有启动日志或供应商调用记录，不能把没有执行冒烟写为成功或失败，也不能报告“零费用”的供应商账单结论。

```bash
sha256sum --check --quiet eval/p2-1c-startup-20261016T190645Z/SHA256SUMS
git diff --check
```

本轮只提交新证据目录。原有未提交 DIAGNOSIS.md 正文未读、未修改、未提交；原 P2-1c 验收目录及被冻结字节保持不变。没有额外进程或服务启动、资源创建及清理操作。
