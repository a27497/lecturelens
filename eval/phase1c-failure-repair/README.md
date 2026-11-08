本目录是 Phase 1-C 的离线诊断和有界修复，不是新的真实验收 PASS。结果、范围及未解决问题见 [REPORT.md](REPORT.md)；冻结原失败的 byte identity 见 FAILURE_IDENTITY.json。不得使用旧 Phase 1-B 授权。

源实现以独立 v19 runner 的 2ecf4d52 为基线，只修改现有 selected runtime 和共享 hint 渲染钩子。没有把实验性实现合入 Phase 0，Phase 0 GitHub CI 仍 PENDING。`CANDIDATE.json` 是源码 hash 记录，不是付费执行许可，也不是新冻结 live manifest。

复核归因不需要数据库：使用现有离线 Python 依赖环境，从本工作树运行 `eval/tutor-scale/safe_exec.py UNIQUE_NETWORK_RECORD_DIR eval/phase1c-failure-repair/analyze_failure.py --implementation-root ROOT --archive ZIP --output NEW_JSON`。ROOT 分别为原冻结 v19 runner 或本工作树；ZIP 为 SHA256 固定的私有原始失败包。输出必须是新文件。函数只构造请求，不实例化 Provider 或数据库；原／新输出分别应复现 79793／69355，均超过 64000，不能把新值改判 PASS。

组合回归需先在已授权范围内准备一个新的、已核验归属的 loopback PostgreSQL，端口 25841，数据库 lecturelens_agent_acceptance、公开合成用户 tutor_scale／密码 synthetic-local-only，fsync 和 synchronous_commit 开启。不得复用业务库，也不得为了复现重启旧 v19 或本次已停止实例。测试本身只在这个新库内创建／清理自己的随机 schema。

长检查使用原样的开发监督器。本次由于日志／pytest 临时文件位于 RAM，监督器复制到 `/dev/shm/lecturelens-phase1c-checks-20261108/scripts/dev/run_check.py`，代码 hash 见 `.data/phase1c/check-environment.json`；最终终态、日志及完整 RAM 目录副本持久保存在 `.data/phase1c/evidence/`。监督器的磁盘门禁没有关闭或修改。示例（将 PYTHON 换为已存在的依赖环境可执行文件，避免自动安装或读取 env 文件）：

```bash
python3 /dev/shm/lecturelens-phase1c-checks-20261108/scripts/dev/run_check.py \
  --name NEW_UNIQUE_CHECK --cwd THIS_WORKTREE --timeout 240 -- \
  PYTHON eval/tutor-scale/safe_exec.py \
  /dev/shm/lecturelens-phase1c-checks-20261108/network-NEW_UNIQUE_CHECK \
  eval/phase1c-failure-repair/run_offline.py \
  --output /dev/shm/lecturelens-phase1c-checks-20261108/output/NEW_UNIQUE_CHECK
```

脚本要求 socket fence，固定仅用合成 acceptance DSN，不接受模型／密钥／live 参数。`--candidate-only` 运行候选专项；默认组合覆盖候选、Tutor／引用、适用的 v18 机制，具体节点清单进入 selection.json。旧 frozen CLI 节点继续在其原身份下验证，不能修改其 manifest 来让本分支冒充旧候选。

本次 197 项机制测试通过；人工编写的完整讲解、代码和纠错，以及历史响应在新请求下的回放，都不能作为新的真实模型生成。独立 AI 语义评审、真实质量、真实 Java／Vue 栈及远端 CI 均未运行。下一步先简化，当前不推荐新真实 Smoke。
