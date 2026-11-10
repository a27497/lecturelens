# LectureLens 验收 CLI

`ll` 随现有 Agent Python 包安装。它提供统一的运行标识、进程记录、状态、报告和独立评审交接。E3 仍由冻结的 Java/Python/PostgreSQL 验收逻辑执行。

## 本地命令

在 LectureLens checkout 中执行：

```bash
uv sync --project agent-service --frozen
uv run --project agent-service ll eval preflight e3
uv run --project agent-service ll eval run e3
uv run --project agent-service ll eval status e3
uv run --project agent-service ll eval report e3
```

| 命令 | 行为 |
| --- | --- |
| `preflight e3` | 校验冻结身份、来源和检索覆盖，创建独立临时栈；无模型请求 |
| `run e3` | 默认离线。预检后通过 Java 网关、Python、Mock HTTP 和 PostgreSQL 验证一次端到端调用 |
| `status e3` | 查看最新或 `--run-id` 指定运行的进程状态、终态退出码和待审阅路径 |
| `report e3` | 查看检索、各回合状态、账本汇总和证据目录 |
| `review e3` | 导入与某个 E3 私有评审包摘要匹配的两份独立结果。保存通过、失败和未决意见 |

输入缺失时可用 `--assets /absolute/path/e3-assets.json` 指定 `archive`、`upstream_dir`、`embedding_cache_source` 和 `java_jar`，字段可按需覆盖。前 3 项的本地默认位置沿用 Phase 1-E 的忽略目录。Java JAR 默认取本 checkout 的 `backend/target/courselingo-backend-0.0.1-SNAPSHOT.jar`。输入文件应来自已校验的冻结材料和对应 Java 构建。具体来源与哈希见 [E1/E2 冻结集](../eval/phase1e-tutor/README.md)。

每次运行在 `.data/ll-eval/<experiment>/<run-id>/` 写独立记录。相同运行 ID 拒绝复用。冻结历史保留在其原始路径。离线命令使用 [已有监督器](LOCAL_CHECK_EXECUTION.md) 及其超时、清理、日志和退出码；运行中返回的退出码为空。根文件系统超过现有磁盘阈值时会返回 `88`。离线测试可通过 `--check-supervisor` 指定字节相同的监督器副本，记录中仍会应用该副本的磁盘检查。真实模式拒绝监督器覆盖。

## 开发机一次性交互试验

已获本阶段授权的操作者可在现有开发机的独立 OpenSSH 登录终端中，亲自启动一次 E3 批量采集。使用普通前台 SSH shell，保持标准输入、输出和错误输出连接到该终端。启动命令如下。

```bash
/home/dev/.codex/worktrees/phase1e-tutor-provider-20261109/lecturelens/agent-service/.venv/bin/ll --workspace /home/dev/.codex/worktrees/phase1e-tutor-provider-20261109/lecturelens eval run e3 --live --dev-ssh --batch --confirmed-price-id deepseek-flash-peak-usd-2026-11-09
```

入口检查真实 SSH 登录终端、冻结价格确认、干净 checkout、授权期限、未消费的阶段锚点及原监督器磁盘门禁。课程检索预检通过后，终端先提示输入 `E3 USD10` 确认阶段和供应商计费风险，再提示隐藏输入 DeepSeek API Key。此时只输入密钥本身。CLI 从终端读取后通过匿名管道交给专用 worker。worker 的启动输出不落日志，密钥无命令行、环境或文件来源。取消、SSH 挂断或 launcher 消失时终止 worker。此路径依赖操作者控制终端，同机 root 或特权自动化仍可检查内存或终端，密钥也不能保证在 Python 内存中立即擦除。原 systemd 隔离方式继续可用。

磁盘门禁返回 `88` 时，真实运行停在提示密钥和写入锚点之前。准备栈之后和批量采集的每个位置前还会复查。使用 `Ctrl-C` 结束采集，已结算记录和未知责任继续保留。不要恢复旧数据库快照来重新启动。

`--batch` 按原顺序采集 10 个冻结位置。已发布且账本结算、证据检查均通过的回合记为 `QUALITY_PENDING`，随即保存私有评审包。执行、协议、来源、磁盘、过期、取消和未知费用故障会停止后续提交。采集成功状态为 `COLLECTION_COMPLETE`。该状态记录采集结果，教学质量仍待独立评审。显式 `--batch` 也支持离线 Mock HTTP 机械验证。 [DeepSeek 定价](https://api-docs.deepseek.com/quick_start/pricing/)

## 受控执行主机上的一次性凭据配置

当前开发机的 Codex 账号拥有免密 sudo 和 Docker 权限，能够越过服务账号的隔离。长期供应商凭据应配置在独立执行主机，或在撤销开发账号所有等效 root 权限并重新核验隔离之后配置。另一个 Linux UID、`chmod 0600` 或 systemd 加密凭据无法防止具有 root 权限的主体读取运行中的密钥。独立执行主机应限制开发账号对 sudo、root 组、Docker/LXD socket、service unit、代码、venv、资产及阶段状态的访问。 [systemd Credentials](https://github.com/systemd/systemd/blob/main/docs/CREDENTIALS.md)

以下为管理员在受控执行主机上的操作。当前 checkout 只提供配置样例。

1. 创建专用系统账号 `ll-eval`。把批准的 checkout 和锁定的 Python 环境放在管理员控制的 `/srv/lecturelens`。仅为可信执行账号配置隔离 Docker 栈的访问权限；Docker 管理权限等同于 root。准备仅服务账号和管理员可访问的 `.data`、`.data/phase1e3` 与 `.demo`。如果 Git 因管理员拥有 checkout 而拒绝读取，管理员可为该路径配置 `safe.directory`。保留阶段目录与相关 PostgreSQL/MySQL 数据卷，数据库快照不应覆盖外置发送标记。
2. 管理员使用终端隐藏输入设置长期 DeepSeek 密钥。以下命令只把加密后的凭据落盘。凭据文件名和 unit 的凭据 ID 保持一致。

   ```bash
   sudo -v
   sudo install -d -m 0700 /etc/credstore.encrypted /etc/lecturelens
   systemd-ask-password 'DeepSeek API key' |
     sudo systemd-creds encrypt --name=deepseek-api-key - \
       /etc/credstore.encrypted/lecturelens-deepseek-api-key
   sudo chmod 0600 /etc/credstore.encrypted/lecturelens-deepseek-api-key
   ```

3. 单独创建管理员控制的 `/etc/lecturelens/e3-authorization.json`。这是本次 E3 费用授权，长期密钥不会授予此权限。权限设为 `0600`。填入本次批准的干净 checkout SHA、实际 Java JAR SHA-256、唯一 32 位小写十六进制批准 ID 和短有效期。下列固定字段沿用原 E3 授权及截止时间，截止前也可设置更早的有效期。启动前重新核对模型和费率；变动时保留拒绝结果。

   ```json
   {
     "experiment": "e3",
     "approval_id": "<32 lowercase hex>",
     "commit_sha": "<approved 40-hex checkout HEAD>",
     "java_jar_sha256": "<approved Java jar SHA-256>",
     "dataset_sha256": "8d6db2bae205f262a86a6d4d3d42c59f953828b9751df04b3a5dcbbfd96eb4cf",
     "price_id": "deepseek-flash-peak-usd-2026-11-09",
     "accepts_supplier_risk": true,
     "budget_nano_usd": 10000000000,
     "initial_requests": 10,
     "retest_requests": 6,
     "expires_at": "2026-11-12T23:59:00+08:00"
   }
   ```

4. 将 [unit 样例](../infra/systemd/lecturelens-eval-e3.service.example) 安装为 `/etc/systemd/system/lecturelens-eval-e3.service`，配置管理员控制的 `e3-assets.json`，核验账号、可写目录、Java 工件和 Docker 隔离项目。用合成凭据先检查授权失败和权限隔离。完成后由用户手动触发；本次交付未安装 unit。 [DeepSeek 定价](https://api-docs.deepseek.com/quick_start/pricing/)

   ```bash
   sudo systemctl daemon-reload
   sudo systemctl start lecturelens-eval-e3.service
   ```

unit 的实际入口为 `ll eval run e3 --live`。它先校验专用 UID、systemd 凭据目录、独立授权、签入版本和 Java 工件，再创建隔离运行。真实检索预检通过后才读取注入的密钥，且仅向 E3 worker 传递。缺少凭据、授权过期、阶段锚点已存在或身份不匹配均拒绝。原手工门禁及原始记录保留。

## E3 预算与评审交接

旧 runner 的 USD 0.55 初始草稿可能提前阻止完整 10 回合。CLI 在 worker 启动前为本次初始运行生成唯一可用收据，按 `10 × USD 0.319488` 预留能力设定 USD 3.19488 的运行上限。阶段门禁仍是 USD 10、最多 16 次生成，首次 10 次和一次开发复测最多 6 次。按当前冻结费率，两段最大请求预留合计 USD 5.111808。未知发送、并发、费用、恢复、过期和外置发送标记继续由既有 PG/文件门禁处理。预算为本地准入约束。供应商硬限未经验证。

有合格回复时，`status` 和 `report` 会列出私有包。管理员把单个包交给两个独立评审上下文。按 [E3 规则](../eval/phase1e3-tutor/REVIEW.md) 收到结果后，由有权访问运行目录的操作员执行：

```bash
ll eval review e3 --run-id RUN_ID --case loop-1 --decision /private/two-decisions.json
```

导入校验包摘要、两份独立身份和评分项，原子保存原始意见。运行时继续使用冻结的通过规则。顺序评审模式默认最多等待每回合 600 秒，可用 `--review-wait` 调整至 0–1200 秒，并受授权失效时间约束。缺少一致通过时按原 E3 规则停止。逾期导入可留证，终态运行保持终态。CLI 不调用评审模型。统一入口仅支持首次试验。首次 `loop-1` 失败后的复测准入与同阶段状态要求见 [E3 修复审计](../eval/phase1e3-tutor/LOOP_1_REPAIR.md)。

## 后续实验复用

在 `lecturelens_real_eval.experiments` 注册实验适配器，复用 `ll` 的运行 ID、记录目录、进程监督、状态与报告。适配器声明输入、离线入口、真实授权和评审数据校验，调用现有课程与实验逻辑。持久预算、来源权威和未知结果停止继续由原领域组件负责。增加实验应优先新增参数和适配，复用已有隔离栈与账本。
