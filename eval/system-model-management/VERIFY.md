# P1-4 系统模型管理：第①–④阶段验收

四阶段均为本地交付，系统配置层默认关闭。没有 push、部署、重启线上服务或真实 DeepSeek/ASR 调用。本报告验证权限、存储、配置解析、执行快照、切换和管理交互，不证明真实模型可用性、识别质量或学习任务质量。

## 提交与改动文件

| 阶段 | 冻结提交 | 内容与原始阶段记录 |
| --- | --- | --- |
| ① | `91fcb319fc39ca906a1ebd8dcbb61be5f65f0947` | ADMIN/USER、逐请求授权、Flyway V25、AES-256-GCM、离线管理员 CLI；[记录](phase1/README.md) |
| ② | `55ef3b8e07697f28e82e6d5046851a6c7ad0614d` | 文本/视觉解析、全文/逐段绑定、不可变版本、无凭据执行快照；[记录](phase2/VERIFY.md) |
| ③ | `40f3a8b17527061731cdfb507f9173083f7fc858` | ASR 双工厂、运行时选择、同任务分片/重试/合并固定供应商；[记录](phase3/VERIFY.md) |
| ④ | 下方命令解析本文件首次加入的提交 | `/admin/settings/models`、手动探测、状态查询及总验收；[结果](phase4/results.json) |

第④阶段在同一个提交内加入本报告，因此用以下命令解析自身提交，实际哈希同时见交付回复，避免在提交内容内自引提交哈希：

```bash
git log --diff-filter=A --format=%H -- eval/system-model-management/VERIFY.md
```

[SHA256SUMS](SHA256SUMS) 枚举相对于基线 `fd8ece82a3eef8d0c71cf63aa49ce2b211e843d3` 的全部最终改动文件与结果文件哈希（不包含清单自身）。各阶段原清单保留，应在对应提交校验；`verify.py` 会通过 Git 对象校验第①–③阶段的历史源码哈希，而不是拿旧哈希比较当前文件。

改动集中在：Java `auth/`、`systemmodel/`、`ai/asr/`、模型路由及任务/字幕/问答/章节/视觉的执行引用传递，Flyway V25，离线管理员脚本，前端独立管理员路由/API/页面、角色加载和导航，部署/架构/API 文档，以及阶段验收材料。个人 `ModelManagementView.vue` 和 Python runtime/模型管理实现未改动；用户 decision/review 命令和 PostgreSQL 所有权保持独立。

第④阶段还统一探测与现有 Qwen JSON 路径的非思考请求选项，并把系统声明的 `ASR` 映射到旧视觉路由的 `AUDIO_TRANSCRIPTION` 标识；扩展实际图片请求测试，防止额外能力声明影响视觉调用。这不新增视觉之外的协议。

## 最终检查

| 检查 | 结果 | 原始记录（相对于仓库根目录） |
| --- | --- | --- |
| Java 全量 | 1,602 项，225 suites；0 失败/错误/跳过 | `.data/system-model-management/phase4/backend-full-final.log`、`full-final-reports/` |
| 独立真实 MySQL | 上述全量内 79 项：基础 9、文本/视觉 21、ASR 24、状态/探测 25 | `SystemModel*MySql*` / `SystemModelMySqlIntegrationTest` 对应 XML |
| 前端全量 | 119 项，29 个测试文件；0 失败/错误/跳过 | `phase4/frontend-full-final.log`、`frontend-final.xml` |
| 前端构建及类型检查 | 通过 | `phase4/frontend-build-final.log` |
| Python 全量 | 727 项；0 失败/错误/跳过，独立 PostgreSQL/pgvector | `phase4/python-final.log`、`python-final.xml` |
| Ruff | check、format check 通过；88 个文件已格式化 | `phase4/ruff-check-final.log`、`ruff-format-final.log` |
| 个人模型管理回归 | 前端 8 项；Python 26 项，包含 decision/review 和版本/凭据/owner 边界 | 两份全量 XML 的 `ModelManagementView.test.ts` / `tests.test_models` |
| 浏览器 Mock 检查 | 桌面 1440×1000、手机 390×844 视口；无自动探测，手动探测 1 次；密钥不入存储，保存/刷新后为空；普通用户被路由拒绝 | `phase4/browser/check-final.log`、`results.json`、`desktop.png`、`mobile.png` |
| Java 打包、CLI shell 语法、diff | 通过 | `phase4/backend-package-final.log`、`checks.json` |
| 验收复算脚本 | Ruff 检查和格式检查通过 | `phase4/verifier-lint-final.log`、`verifier-format-check-final.log` |
| 凭据日志检查 | 最终 240 个日志/XML/脱敏观测文件，15 个合成凭据 canary，匹配 0 | [复算脚本](verify.py) 的 `scan_files/CANARIES` 与 [阶段结果](phase4/results.json) |

除第一行写出的完整路径，其余 `phase4/...` 均位于 `.data/system-model-management/` 下。重复运行不累加到用例总数；前几阶段的历史数字见各自冻结记录。Python 保留一条依赖弃用警告；Vite 保留大包及第三方注释警告，不隐去日志。

[汇总结果](results.json)、[第④阶段结果](phase4/results.json) 和 [第④阶段原始文件哈希](phase4/RAW_SHA256SUMS) 保存精确计数、命令/退出码、探测最终地址与记录位置。第①–③阶段的原始记录分别由对应目录中的 `RAW_SHA256SUMS` 校验。

## 验收项与证据

| 验收项 | 对应证据 |
| --- | --- |
| 未登录 401、普通用户 403、管理员成功；JWT 不代替当前数据库角色 | `SystemModelAdminBoundaryTest`；`SystemModelRuntimeMySqlTest.everyManagementEndpointChecksAdminAndQueriesNeverReturnCiphertext`；`SystemModelProbeMySqlTest.newApisRequireAdminAndResponsesNeverContainStoredCiphertextOrVendorMessage` |
| 注册及存量账号默认 USER；首个管理员可不经过前端指定 | Flyway 新库/V24 升级测试；`AuthRegistrationServiceTest`；`SystemModelMySqlIntegrationTest` 的 CLI grant/revoke/事务审计回滚；`scripts/admin/system-model-admin.sh` |
| 启用缺主密钥即启动失败，关闭层保持旧启动 | `SystemModelActivationTest`；有效启动/双 ASR 工厂注册由 RuntimeMySqlTest 验证 |
| 数据库只有密文，nonce/AAD/篡改/错误主密钥失败；日志不含凭据 | `SystemModelSecretCipherTest`、MySQL 密文落库测试、最终 canary 检查 |
| 当前/历史/执行 API 不透传配置原文或密文，只返回密钥摘要 | 全管理接口逐一比对历史密文的 RuntimeMySqlTest；ASR 快照/历史序列化测试；新增状态/探测 API 权限与密文排除测试 |
| 全文新绑定不改变逐段、问答、资料、章节、视觉；两模式各用对应绑定 | `changingOnlyFullTranslationPreservesEveryOtherEffectiveRouteAndRollback`、`actualFullAndSegmentTranslationHitIndependentBindings` |
| 文本 A 使用旧快照、B 使用新版本；不在快照复制凭据 | `runningAUsesOldVersionWhileNewBUsesNewVersion`；任务创建事务回滚及执行引用作用域测试；版本/请求观测 |
| 视觉独立密钥、冻结版本、图片消息及精确 URL；额外 ASR 声明不破坏路由 | `visualCallsUseFrozenIndependentKeyAndExactEndpoint` 的实际图片请求 |
| ASR 两工厂运行时切换，A 的并发分片/429 重试/合并固定旧供应商，B 用新供应商 | `SystemModelAsrMySqlTest.concurrentChunksRetriesAndMergeStayOnAWhileNewTaskUsesBThenRollbackCreatesC`；实际 Pipeline + 适配器 + Mock HTTP + MySQL，观测留在 `observations-final/asr-requests.jsonl` |
| 回滚只恢复所选功能的历史绑定，产生新版本；旧任务不变 | 上述文本/ASR 回滚测试；ASR 的密钥轮换、删除当前对象与回滚 null 绑定测试 |
| 漏 Redis 通知仍读数据库版本；expectedVersion 并发保存仅一成功 | RuntimeMySqlTest 的漏通知/并发保存；AsrMySqlTest 的通知抛错及 `concurrentExpectedVersionSavesHaveExactlyOneWinner`；没有启动多实例 |
| 错误密钥/模型、401/429、超时、无效 JSON、无法解密均失败，无供应商/Mock 静默回退 | 文本状态码及 JSON 测试；ASR 400/401/403/404/408/429/500、错误模型、超时、无效 JSON、解密失败测试；探测仅返回闭合错误类别 |
| DeepSeek 根地址不补 /v1，显示实际最终地址 | 运行时与探测请求均断言 `https://api.deepseek.com/chat/completions`；管理员状态表和浏览器检查；环境默认保留原 `/v1` 语义 |
| 探测只由管理员手动发起，不自动测试，不写任务/版本/审计/探测表 | ProbeMySqlTest 的手动文本/ASR请求及数据库计数断言；前端与浏览器的无自动探测、仅点击触发断言 |
| 地址白名单 + 全 IP 检查 + 禁止代理/重定向 + 有界请求 | `SystemModelUrlPolicyTest`、`SystemModelHttpClientTest`、`SystemModelProbeTransportTest`，以及精确 origin/混合 DNS/超时后不释放并发名额测试 |
| ASR 探测用仓库授权音频，响应不返回转写 | `asrUsesAuthorizedBundledFixtureAndNeverReturnsTranscript`；[MIT 合成音频说明](../../backend/src/main/resources/system-model-probe/NOTICE.md)；夹具 SHA-256 见阶段结果 |
| 页面显示来源、版本、最终地址、本地有效性和未接通功能；测试结果只属于当前版本 | `AdminModelManagementView.test.ts`；`/status` 本地状态测试；浏览器桌面/手机检查 |
| 密钥不入 localStorage，提交（含失败）/切换/刷新/离开/撤权清空；打开仅掩码 | 管理页 12 项测试及浏览器保存/刷新/存储检查；未知服务端消息不显示 |
| 入口仅 ADMIN 可见，直接 URL 重新查角色；普通用户的管理员 API 403 不清除其有效登录 | `adminModels.test.ts`、`authSessionHttp.test.ts`，后端权限测试独立验证最终授权 |
| 无绑定、旧 enabled/provider 选择、Mock、内嵌字幕、ASR、检索与个人学习 Agent 不退化 | Java 全量、原 provider 选择与 TranscribeAudioStep 套件；Python/PostgreSQL 全量；个人模型前端/Python 专项；没有修改个人页面实现 |

## 执行命令与复现

从仓库根目录启动独立测试数据库。名称若已占用，应选择新名称，不能删除现有容器。下方密码只用于新建的临时测试容器，不是部署凭据。

```bash
mkdir -p .data/system-model-management
export SYSTEM_MODEL_VERIFICATION_DIR="$(mktemp -d "$PWD/.data/system-model-management/replay-phase4.XXXXXX")"
docker run --detach --name lecturelens-p14-replay-mysql \
  --env MYSQL_ROOT_PASSWORD=p14-local-test-only \
  --env MYSQL_DATABASE=lecturelens_system_model_test \
  --publish 127.0.0.1::3306 mysql:8.4 \
  --innodb-flush-log-at-trx-commit=2 --sync-binlog=0 --skip-log-bin
docker run --detach --name lecturelens-p14-replay-postgres \
  --env POSTGRES_USER=lecturelens --env POSTGRES_PASSWORD=p14-local-test-only \
  --env POSTGRES_DB=lecturelens_agent_test --publish 127.0.0.1::5432 \
  pgvector/pgvector:0.8.6-pg17
task_p14_mysql_address="$(docker port lecturelens-p14-replay-mysql 3306/tcp)"
task_p14_postgres_address="$(docker port lecturelens-p14-replay-postgres 5432/tcp)"
export SYSTEM_MODEL_TEST_JDBC_URL="jdbc:mysql://127.0.0.1:${task_p14_mysql_address##*:}/lecturelens_system_model_test?useSSL=false&allowPublicKeyRetrieval=true&serverTimezone=UTC"
export SYSTEM_MODEL_TEST_MYSQL_USER=root
export SYSTEM_MODEL_TEST_MYSQL_PASSWORD=p14-local-test-only
export AGENT_TEST_DATABASE_URL="postgresql://lecturelens:p14-local-test-only@127.0.0.1:${task_p14_postgres_address##*:}/lecturelens_agent_test"
```

等待两容器 ready。Java 测试只在本机 `_test` 基准库创建/删除随机临时测试库；Python 使用上述独立 PostgreSQL，不跳过数据库测试。供应商由测试替身接管，无需真实密钥。

```bash
cd backend
bash ./mvnw -B test > "$SYSTEM_MODEL_VERIFICATION_DIR/backend.log" 2>&1
bash ./mvnw -B -DskipTests package > "$SYSTEM_MODEL_VERIFICATION_DIR/backend-package.log" 2>&1
cd ../frontend
npm ci
npm run test:unit -- --reporter=default --reporter=junit \
  --outputFile.junit="$SYSTEM_MODEL_VERIFICATION_DIR/frontend.xml" \
  > "$SYSTEM_MODEL_VERIFICATION_DIR/frontend.log" 2>&1
npm run build > "$SYSTEM_MODEL_VERIFICATION_DIR/frontend-build.log" 2>&1
cd ../agent-service
uv sync --locked
uv run ruff check src tests > "$SYSTEM_MODEL_VERIFICATION_DIR/ruff-check.log" 2>&1
uv run ruff format --check src tests > "$SYSTEM_MODEL_VERIFICATION_DIR/ruff-format.log" 2>&1
uv run pytest -q --junitxml="$SYSTEM_MODEL_VERIFICATION_DIR/python.xml" \
  > "$SYSTEM_MODEL_VERIFICATION_DIR/python.log" 2>&1
cd ..
agent-service/.venv/bin/ruff check --config agent-service/pyproject.toml eval/system-model-management/verify.py
agent-service/.venv/bin/ruff format --check eval/system-model-management/verify.py
bash -n scripts/admin/system-model-admin.sh
git diff --check
docker rm --force --volumes lecturelens-p14-replay-mysql lecturelens-p14-replay-postgres
```

本次使用已有锁定依赖环境；Python 实际命令为 `.venv/bin/pytest` / `.venv/bin/ruff`，效果等同 `uv run`。数据库版本和本任务临时容器清理记录见 `phase4/checks.json`；没有触碰现有业务数据库。浏览器仅运行本地 Vite，所有 API 由 Playwright 拦截，外部 origin 被拒绝。可在保留原始记录的本机重放：

```bash
# 终端 A
cd frontend
npm run dev -- --host 127.0.0.1 --port 4177 --strictPort
# 终端 B，从仓库根目录；check.mjs 首行记录本机 Playwright 安装路径，Chrome 为 /usr/bin/google-chrome。
node .data/system-model-management/phase4/browser/check.mjs
# 完成后只停止刚启动的本地 Vite。
```

浏览器原始记录中保留了实际脚本、成功结果及截图；重新执行应输出到新目录，避免覆盖冻结记录。在其他机器上需安装 Playwright 并调整脚本中的本机工具路径。新复跑的任务/快照 ID、耗时和绝对配置版本号可能不同，应检验冻结版本关系和目标地址，不要求复现随机 ID 本身。

复算报告的全部计数、历史提交/source 哈希、最终探测地址、音频参数、canary、退出码及原始文件哈希：

```bash
python3 eval/system-model-management/verify.py
sha256sum -c eval/system-model-management/SHA256SUMS
sha256sum -c eval/system-model-management/phase4/RAW_SHA256SUMS
```

需要本机 `.data/system-model-management/phase1` 至 `phase4` 的原始记录；Git 只保存脱敏结果和哈希，不保存完整日志。提交前使用 `--pre-commit` 只跳过解析本报告自身提交，其余检查相同。

## 保留的失败与边界

所有阶段的失败记录保留，不改写为成功。第④阶段的 `frontend-type-initial.log` / `frontend-type-second.log` 为新组件导入及输入元素类型错误；`backend-targeted-initial.log` 为测试请求叠加身份头的问题；`browser/check-initial.log` 及初始截图为手机端溢出失败。后续定向/全量通过记录单独命名。首轮全量通过后补充的 Qwen 请求选项与视觉能力兼容映射，均另跑 Java 全量；旧通过日志保存在 `backend-full-before-options.log` / `backend-full-before-capability-map.log`，不与最终 XML 混用。

已知限制：DNS 校验不固定连接 IP；探测并发限制按实例计算；第②阶段没有 ASR 路由的旧快照需升级前排空；分片时长仍由部署配置。LangChain4j 默认关闭，系统层启用时要求关闭它。连通性结果不是模型能力/教学质量认证，也不验证视觉图片或 Python Agent 工具调用。

本次不统一 Python 系统配置，不新增协议、Anthropic/Responses、负载均衡、自动故障转移、插件或远程 embedding；`system_model_probe_record`、幂等键及回滚预览按确认要求推迟。回滚首版只恢复指定功能的历史绑定并生成新版本。
