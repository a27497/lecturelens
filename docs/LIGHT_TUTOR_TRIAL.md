# Light Tutor 正常用户试学

试学使用现有 Java 网关、课程上传、Vue Tutor 面板与 Python/PostgreSQL。DeepSeek 默认为关闭。一次试学收据只绑定一个用户、一门已导入的课程和一个 Evidence revision，在所有对话中累计最多 **3 次生成**、**USD 1**，有效期最多 24 小时。纯文本协议使用非流式 Chat Completions。真实试学需要本轮之外的新费用授权。 [Chat Completions](https://api-docs.deepseek.com/api/create-chat-completion/) [DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)

## 准备独立课程

1. 按 [无密钥 Demo](QUICKSTART.md) 启动独立的 Java、Vue 和数据服务。使用独立 Compose 项目、MySQL 和 PostgreSQL/pgvector，保留各自的数据卷。Java 与 Agent 共享内部签名配置，`AGENT_SERVICE_URL`、`AGENT_JAVA_BASE_URL` 指向同一试学栈。Java 开启 `DENSE_RETRIEVAL_ENABLED=true` 和 `STUDY_AGENT_ENABLED=true`。使用 [Demo Mock 配置](../.env.demo.example) 和本地嵌入缓存完成无付费导入。
2. 从 `agent-service/` 用已有 ASGI 入口启动 Python，设置 `TUTOR_ENABLED=true AGENT_LLM_MODE=mock TUTOR_ENGINE=light`，`TUTOR_PROVIDER` 取默认 `mock`。在浏览器打开 `/register` 注册新用户，登录后到 `/upload` 上传课程并开始处理。课程详情等待 Evidence 索引就绪。
3. 选一门可以发送给供应商的短课。下表以一门只讲 Python 列表遍历和计数的课为例。测试用课程的字幕讲解了列表逐项执行、计数器从 2 逐项加 1、循环内外的打印次数。独立试学可导入含这些内容的课程，核对页面的实际 Evidence 后再提问。若采用 Demo Mock ASR，字幕取自配置的合成课文，评审以页面展示的课文为准。

| 场景 | 在 Tutor 面板输入 | 独立评审要点 |
| --- | --- | --- |
| 完整讲解 | 请完整解释 Python for 循环怎样遍历列表并累计计数，给出初值 2 和两个名字的可运行代码，标注课程出处。 | 代码可运行，计数轨迹为 2→3→4，出处支撑逐项执行与计数方法 |
| 苏格拉底追问 | 勾选 Socratic。最后一次打印应放在循环体内还是循环结束后？请用问题引导我。 | 针对「最后一次打印」问一个可推进思考的问题，引用当前课文，留出学习者作答空间 |
| 明确拒答 | 取消 Socratic。这门课讲了如何配置 Kubernetes 集群的自动扩缩容吗？ | 明确指出课程证据不足，无 Kubernetes 配置答案、无伪造引用 |

## 授权后开启真实试学

由独立栈操作者在收到明确的新授权后签发收据。以本人登录的 `GET /api/me` 返回的 `userId`、课程 URL 中的 task ID 和 `GET /api/tasks/<id>/evidence` 返回的 `revision` 为准。复核模型和峰值费率。原 E3 的库、收据与标记属于历史验收。 [DeepSeek 模型与价格](https://api-docs.deepseek.com/quick_start/pricing/)

以下示例在 `agent-service/` 执行，使用已指向本次独立栈的 `AGENT_DATABASE_URL`。将前三个参数换成真实 scope，第四个参数使用稳定的私有绝对目录。数据库目标仅预置一次，重复执行会因唯一约束失败。收据示例有效一小时。

```bash
mkdir -m 700 /absolute/private-trial-state
tutor_trial_owner=1
tutor_trial_task=task_replace_with_your_course_id
tutor_trial_revision=5
.venv/bin/python - "$tutor_trial_owner" "$tutor_trial_task" "$tutor_trial_revision" \
  /absolute/private-trial-state/receipt.json <<'PY'
import os
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import psycopg
from lecturelens_agent.study.contracts import StudyScope
from lecturelens_real_eval.tutor.flash_ledger import TARGET_SCHEMA, build_digest
from lecturelens_real_eval.tutor.flash_provider import MODEL, MODEL_VERSION, PRICE_ID, digest
from lecturelens_real_eval.tutor.trial import TrialAuthorization

scope = StudyScope(owner_id=int(sys.argv[1]), course_id=sys.argv[2], revision=int(sys.argv[3]))
path = Path(sys.argv[4])
if not path.is_absolute() or path.exists():
    raise SystemExit("Use a new receipt path in the isolated trial state directory")
with psycopg.connect(os.environ["AGENT_DATABASE_URL"]) as conn:
    historical, = conn.execute("SELECT to_regnamespace('tutor_e3') IS NOT NULL").fetchone()
    if historical:
        raise SystemExit("An independent trial database is required")
    conn.execute(TARGET_SCHEMA)
    target, = conn.execute("INSERT INTO tutor_flash_target DEFAULT VALUES RETURNING target_id").fetchone()
now = datetime.now(timezone.utc)
receipt = TrialAuthorization(
    version="lecturelens-light-tutor-trial-v1", mode="real",
    grant_id=uuid.uuid4().hex, target_id=str(target), build_sha256=build_digest(),
    dataset_sha256=digest(scope.model_dump_json().encode()), scope=scope,
    model=MODEL, model_version=MODEL_VERSION, price_id=PRICE_ID,
    issued_at=now, expires_at=now + timedelta(hours=1),
    accepts_supplier_risk=True, request_limit=3, budget_nano_usd=1_000_000_000,
)
os.umask(0o077)
with path.open("x") as stream:
    stream.write(receipt.model_dump_json())
PY
```

在操作者控制的终端停止试学栈的 Mock Agent，复用该栈的连接配置。保持文件权限 0600、目录权限 0700。通过隐藏输入将密钥仅注入 Agent 进程环境。使用以下现有入口，保留其他 Study 模型为 Mock。

```bash
(
  set +x
  ulimit -c 0
  IFS= read -r -s -p 'DeepSeek API Key: ' tutor_trial_secret || exit 1
  printf '\n'
  TUTOR_FLASH_API_KEY="$tutor_trial_secret" \
  TUTOR_TRIAL_RECEIPT_FILE=/absolute/private-trial-state/receipt.json \
  TUTOR_ENABLED=true TUTOR_ENGINE=light TUTOR_PROVIDER=deepseek-flash AGENT_LLM_MODE=mock \
  exec .venv/bin/python -m uvicorn lecturelens_real_eval.tutor.app:create_app --factory \
    --host 127.0.0.1 --port 8090
)
```

端口与试学 Java 的 `AGENT_SERVICE_URL` 一致。以刚注册的账号回到课程详情，打开 **Tutor 对话**，也可直接访问 `/tasks/<TASK_ID>?view=tutor`。面板显示 DeepSeek 试学提示后提交表中的三个问题。首个异常停止本次质量判断。结束后停止试学 Agent 并保留同一 PostgreSQL、收据和外置发送标记。

## 费用、权限和评审证据

- 每个调用在发送前持久预留 **USD 0.319488**，根据供应商返回的有效 usage 结算。PostgreSQL 按收据串行控制累计请求和费用。超限、过期、未发布的已发送回合或未结算责任阻止下一次发送。外置发送标记须与账本一致，原位置应保留在数据库快照之外。
- Java 每次按登录用户和当前 revision 鉴权，Python 再校验收据 scope，并重新读取当前 Evidence 后发布。取消后回合不发布，已发请求仍可结算。重启可继续发布已接收的检查点，`reserved` 状态会停止。无检索证据的固定拒答不发生成请求。
- 操作者从私有 PG 读取 `tutor_turn.checkpoint` 内的 `messages`、`provider_content`、`evidence`，并对照公开回合中的答复和 `citations`。按 `turn_id` 关联 `tutor_flash_call` 可取得请求与响应摘要、usage、费用、错误和发布状态。使用收据绑定版本的 `payload(messages, text_reply=True)` 可复算请求摘要。私有检查点随课程删除清理。人工评审分别记录教学完整性、引导质量、拒答和引用是否支持相邻陈述。
- 本地预留约束使用公开峰值价格，供应商账单与模型路由仍需单独核对。离线 Mock 只验证执行、协议和权限。真实教学结果当前为 `NOT_RUN`。


## 离线验收

独立 Java/MySQL、Python/PostgreSQL 和 Chromium 通过正常注册、登录、上传及课程索引流程。三次 Mock HTTP 回合分别通过代码与引用导航、定向追问和明确拒答。刷新恢复对话，换新对话提交第四次生成被拒，另一账号的 Tutor 列表、读取和创建请求均返回 HTTP 404。

| 检查 | 实际退出码 | 结果 |
| --- | ---: | --- |
| Python / 独立 PostgreSQL | 0 | 263 项通过，含作用域、持久预留、未知费用停止、恢复和历史试验回归 |
| Vue 类型检查与 Tutor 面板 | 0 | 类型检查通过，20 项测试通过 |
| Java/MySQL → Python/PG → Vue/Chromium | 0 | 三个 Mock 回合、持久证据、费用上限与跨账号拒绝通过 |

私有验收记录在 `.data/light-tutor-trial/browser-run-1/`，包括 `result.json`、`browser-trial.json`、`turns.json` 和 `ledger.json`。监督器退出码记录在 `.data/light-tutor-trial/checks/`。本轮真实模型请求为 0。
