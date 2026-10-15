# 系统模型管理部署记录（2026-10-16，Asia/Shanghai）

已部署 Java 与管理员前端，Flyway V25 成功，账号 `a2749736405@gmail.com`（userId=9）已由离线 CLI 授予 ADMIN。访问地址：

**https://34.81.153.182/admin/settings/models**

本次没有创建供应商、模型或功能绑定，没有调用 DeepSeek、真实 ASR 或其他模型供应商。密钥由用户自行在页面填写。未 push。Python、llama、基础设施和网关访问控制没有升级或重启。

## 版本与部署范围

工作分支为 `codex/p14-system-model-management`，部署时工作区干净。部署代码固定为 `13f8fc03d61d608157be1b7c3c0b5d474536acfd`，四阶段提交均在本地：

| 阶段 | 提交 |
| --- | --- |
| ① 权限、表、加密 | `91fcb319fc39ca906a1ebd8dcbb61be5f65f0947` |
| ② 文本、视觉、翻译与快照 | `55ef3b8e07697f28e82e6d5046851a6c7ad0614d` |
| ③ ASR 运行时切换 | `40f3a8b17527061731cdfb507f9173083f7fc858` |
| ④ 管理员页面、探测与验收 | `13f8fc03d61d608157be1b7c3c0b5d474536acfd` |

四阶段差异为 `fd8ece8..13f8fc0`，141 个文件；完整清单和统计见 `diff-phase1-4-files.txt`、`diff-phase1-4-stat.txt`。实际发布物是此提交构建的后端 JAR 和前端 dist；不发布上述范围中的 Python 运行时、评测记录或脚本。

旧服务运行 `/home/dev/projects/lecturelens-asr-b/.data/asr-b-deploy/backend-asr-b.jar`。该工作树 HEAD 标记为 `7583973a2768f79cfcee2860ce46f8cbe9fa1825`，但不能据此声称旧 JAR 来自该提交的干净构建。旧产物以 SHA256 为准。与该源标记的完整差异另存 `diff-old-source-marker-*`；它包含此前历史的 Python 和评测文件，不能当作本次全部发布范围。`jar-differences.json` 按实际新旧 JAR 逐项列出应用条目的摘要差异（149 项）。

| 项目 | 部署前 | 部署后 |
| --- | --- | --- |
| JAR SHA256 | `a6148f8aad454f506f644102c793690871dce5d2f34036c1a30f5b5d56dd6a08` | `74ce36c807ce2e16cdb7a372dd73efe70bbf88bbf1ec08caac717a7bc82ead01` |
| Flyway | V24 | V25，success=1 |
| 系统配置层 | 未启用 | 启用，配置版本 1 |
| 新建供应商 / 模型 / 绑定 | 无系统表 | 0 / 0 / 0 |
| 指定账号角色 | 旧版本没有角色列 | ADMIN |

前端保留原绑定挂载目录的 inode，复制新文件与 index，并保留已有哈希资源供打开的页面使用。实际浏览器已加载管理员页面；用户个人 `/settings/models` 与 decision/review 路径保持现有实现。

## 升级检查与备份

升级前磁盘占用约 91%，可用约 14 GB；备份和构建前后可用空间的精确值见 JSON 记录。分析任务共 12 个：SUCCEEDED=5、FAILED=6、CANCELED=1，未完成数为 0。V25 前没有系统模型表，因此不存在第二阶段缺少 ASR 路由的旧快照。迁移恢复和重启前再次核对未完成数为 0。

私有备份及原始记录目录（权限 700，Git 忽略）：

```text
/home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/
```

- `mysql-before.sql.gz`：完整 `courselingo` 业务库，包含 user_account、Flyway 记录、表结构、数据、例程、事件和触发器；使用 single-transaction，已通过 gzip 完整性检查。
- `backend-before.jar`、`frontend-before.tar.gz`：升级前实际产物。
- `backend.service`、`90-asr-bailian.conf`、`run-backend.py`、`asr-bailian.yml`、`nginx.conf`：原启动方式与路由配置。已有加密百炼凭据源保留在原位置，只记录引用，不复制 API Key。
- `BACKUP_SHA256SUMS`：上述备份及环境校验摘要的完整性清单。
- 本目录的 `before-command.json`、`before-environment.redacted.json`：启动命令及全部环境变量名的脱敏清单。环境值仅保留带部署主密钥的 HMAC 用于一致性检查，不保留 API Key 明文。复核时移除了初始环境副本及 runtime 文件副本；最终备份、日志和新产物已检查没有 API Key 明文。

主密钥由随机 32 字节生成并 Base64 编码，保存在私有目录 `system-models.env`，权限 600；只通过 systemd EnvironmentFile 注入进程。它没有进入 Git、聊天或日志。保留该文件以解密已保存的历史配置，不能用重新生成主密钥代替恢复。原部署 runtime 与 systemd 百炼凭据源也必须保留。

## 执行过程与迁移恢复

1. Java 使用 `bash ./mvnw -B -DskipTests package dependency:build-classpath -Dmdep.outputFile=target/admin-classpath.txt` 构建；前端使用 `npm run build -- --outDir ../.data/system-model-management/deploy-20261016/frontend-new`，包含 vue-tsc。构建均成功，完整日志在私有目录。
2. 独立 Flyway Java CLI 使用构建产物中的迁移资源，目标固定为 V25，不启动 Spring 或任务消费者。首次显式 validate 将待执行的 V25 报为 pending，未修改数据库；随后正常 migrate 在创建首个触发器时收到 MySQL 1419。
3. 当时服务仍运行旧 JAR，七个新表没有业务写入，未完成任务为 0。确认原因为 log_bin=1、log_bin_trust_function_creators=0 与应用账号缺少全局 SUPER。只移除这次部分创建的 V25 对象及 role 列，Flyway repair 清除失败的 V25 标记，再以数据库管理凭据在内存中执行 V25。没有恢复覆盖业务库，没有修改历史迁移校验和，没有放宽应用账号权限或更改全局 MySQL 设置。最终四个审计/版本保护触发器全部存在。
4. 使用 `scripts/admin/system-model-admin.sh grant --user-id 9`，仅把现有 ACTIVE 账号升为 ADMIN，并产生 LOCAL_CLI 审计。数据库连接凭据只在调用进程环境中传递。
5. 新 JAR 写入私有目录 `backend.jar`；新增 systemd drop-in `/etc/systemd/system/lecturelens-live-backend.service.d/99-system-models.conf`。新启动器沿用原 runtime 加载、systemd 加密百炼凭据和 ASR YAML，只更换 JAR 路径；环境文件启用系统层及 Flyway，并设置唯一探测 origin `https://api.deepseek.com`。
6. `systemctl daemon-reload` 后只重启 `lecturelens-live-backend`。llama 与 agent-service 的 PID、启动时间完全不变，ASR 环境变量的 HMAC 全部一致。没有新建分析任务，未使用真实供应商做健康检查。

原始过程日志：`backend-build.log`、`frontend-build.log`、`flyway-validate-first.log`、`flyway-migrate.log`、`flyway-recovery.log`、`grant-admin.log`、`backend-startup.log`。`artifacts.json` 记录完整路径、大小和 SHA256；失败尝试的日志保留，没有用成功结果覆盖。

## 验证与复现

从仓库根目录执行以下只读检查；脚本生成 120 秒本机验证 JWT，只在进程内使用，不打印或写入令牌及签名密钥。它故意在令牌中声明 USER，以确认 `/api/me` 和管理授权实际读取数据库 ADMIN。真实端点是 **`GET /api/me`**，不是 `/auth/me`。

```bash
python3 eval/system-model-management/deploy-20261016/verify_deployment.py
python3 eval/system-model-management/verify.py
python3 eval/system-model-management/deploy-20261016/verify_artifacts.py
sha256sum -c eval/system-model-management/deploy-20261016/SHA256SUMS
```

`verify_deployment.py` 针对本次“未创建供应商/绑定”的初始状态断言；用户开始配置或创建任务后，部分初始状态断言将不再成立，不应据此认为部署失效。缺省只检查，不改动证据；显式添加 `--record` 才更新 verification.json，更新后应重新封存摘要。

| 验收 | 证据 |
| --- | --- |
| Java / agent-service / llama 健康 | `verification.json`：UP / ready / ok |
| 指定账号 ADMIN，匿名 401、现有普通用户 403 | `verification.json`，真实本机 HTTP 接口 |
| 原配置保留 | `verification.json`：所有功能均无 DATABASE 绑定，文本仍本机 llama；ASR ENV / READY；视觉原部署关闭且缺少凭据，未擅自开启 |
| 管理员页面可打开 | `browser.json`、私有 `admin-live.png`；页面版本 1、白名单显示正确、密钥输入为空、自动探测 0、外部请求 0、页面错误 0 |
| 密钥与密文不出接口 | `verification.json`：catalog、版本、执行查询及审计响应扫描；`credential-check.json`：配置版本只有密文，日志/最终备份/新产物没有 API Key 明文 |
| 白名单与限制 | `verification.json`：唯一 origin 为 DeepSeek，10 秒、2 并发、64 KiB；`probe-safety-evidence.json` 关联已验收的真实 MySQL/Mock HTTP 测试，非白名单返回 ORIGIN_NOT_ALLOWED 且传输器 never called |
| 四阶段回归证据 | `prior-acceptance.json` 与上级 VERIFY.md：Java 1602、前端 119、Python 727、真实 MySQL 79；本次重核冻结证据，未重复宣称跑了一遍全量测试 |
| 回滚脚本 | 私有 `rollback.sh` 通过 `bash -n`；未执行线上回滚演练 |

未发送真实 DeepSeek 请求，因此没有验证用户密钥、`deepseek-flash` 的实际可用性、供应商 JSON 输出或课程翻译质量。页面的 READY 只是本地解析和解密成功。没有放行本机模型主动探测；部署默认调用本机 llama 的兼容路径仍可用。探测禁止代理、重定向和私有地址；DNS 校验后不固定实际连接 IP 的重绑定窗口仍是已确认局限。

## 运行时回滚

以下命令恢复升级前 Java 启动方式及前端，不删除 V25 数据、版本和审计。脚本发现未完成分析任务时会停止；先排空任务，不能强行让旧 worker 接管新快照。

```bash
bash /home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/rollback.sh
```

脚本移除 `99-system-models.conf`、daemon-reload 并重启原 Java 服务，再恢复旧前端内容并轮询健康检查。原 `90-asr-bailian.conf`、旧 JAR 和受保护凭据源保持原位置；备份校验可先运行：

```bash
cd /home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016
sha256sum -c BACKUP_SHA256SUMS
```

该回滚保留 V25 的新增列、表及 ADMIN 角色，旧代码不消费系统绑定。保留 `system-models.env`，重新启用新版本仍需相同主密钥。不要删除审计或改写不可变版本。

**整库恢复是另一项破坏性操作，本次没有执行。** 仅在明确允许丢弃备份后新增的业务数据、已备份当前库并进入维护窗口后使用；必须先运行上面的运行时回滚，并停止 Java 写入。下面命令会删除整个 courselingo 库，再恢复部署前 V24 快照，不能在正常使用期间运行：

```bash
sudo -n systemctl stop lecturelens-live-backend
docker exec lecturelens-demo-l2-mysql-1 sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root -e "DROP DATABASE courselingo"'
gzip -dc /home/dev/projects/lecturelens/.data/system-model-management/deploy-20261016/mysql-before.sql.gz | \
  docker exec -i lecturelens-demo-l2-mysql-1 sh -c \
  'MYSQL_PWD="$MYSQL_ROOT_PASSWORD" mysql -u root'
sudo -n systemctl start lecturelens-live-backend
```

## 用户自行验收清单

1. 使用指定账号重新登录，打开 `/admin/settings/models`。当前基线配置版本是 1，功能绑定来自部署默认；记下全文翻译的原来源和版本。
2. 创建启用的供应商：协议 `OPENAI_CHAT`，Base URL 为 `https://api.deepseek.com`。用户自行填写密钥并保存，页面重新读取只应显示掩码。
3. 在该供应商下创建模型 `deepseek-flash`，声明 `TEXT_CHAT` 和 `JSON_OUTPUT`，保存。模型名是否可用由供应商和下一步手动测试确认。
4. 点击该模型的“测试连通性”。它会产生真实请求和费用，包含 `response_format: {type: json_object}`；最终地址应为 `https://api.deepseek.com/chat/completions`。测试失败时只应看到错误类别和耗时，不应有供应商原始报错或密钥。不要把密钥贴入反馈、截图或日志。
5. 只把 `TRANSLATION_FULL_TEXT` 绑定到这个模型并保存；确认问答、资料、章节、视觉、逐段翻译和 ASR 的有效配置不变。
6. 选一小节课启动新分析任务，在执行记录核对冻结版本。全文翻译可能调用 DeepSeek，真实 ASR 是否调用取决于字幕覆盖和原转写策略，均可能产生费用。不要用正在执行的旧任务验证新绑定是否生效。
7. 在“历史与回滚”把 `TRANSLATION_FULL_TEXT` 恢复到绑定前版本（初始版本 1 的绑定为空），生成新版本；或在绑定选择中恢复部署默认并保存。新任务应恢复原本机文本配置，已开始的任务继续自己的快照。

完成后反馈测试类别、耗时、最终请求地址及脱敏版本/任务记录即可；无需提供密钥。本次部署工作在此停止，等待用户自行配置和验收。
