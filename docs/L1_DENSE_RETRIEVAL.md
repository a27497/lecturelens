# L1 首条检索链路：Java Evidence → Python → pgvector

## 本轮范围

在保留原有 Java 摄取、权限和 QA 生成逻辑的基础上，新增 `agent-service/`，支持真实多语言 Embedding 与向量检索。默认 `DENSE_RETRIEVAL_ENABLED=false`，原关键词路径继续工作；开启后普通问答调用 Python，课程总览继续使用原有时间均匀采样。时间定位作为向量候选的硬过滤条件。

这是 **L1 最小闭环**，不是完整 L1 或 Agent 完成：50 题人工评测暂缓，Hybrid、Rerank、异步增量索引、Agent Loop 留待下一工作包。

## 服务边界与契约 v1

```mermaid
sequenceDiagram
    participant U as 用户
    participant J as Java QA
    participant P as Python Retrieval
    participant V as PostgreSQL/pgvector
    U->>J: 课程问题
    J->>J: 验证用户/课程，读取当前 CourseEvidence
    J->>P: 签名快照 + query + time_window
    P->>P: 验签、分块、本地 Embedding
    P->>V: 按完整快照版本原子写入/查询
    V-->>P: evidence_id + cosine score
    P-->>J: 作用域 + revision + hits
    J->>J: 校验引用白名单，再检查课程存在与当前版本
    J->>J: 原有 prompt 预算、LLM、可见证据引用校验
    J-->>U: 回答 + 原始时间戳引用
```

内部端点：`POST /internal/v1/retrieve`。JSON Schema 由 `agent-service/src/lecturelens_agent/contracts.py` 定义，字段使用 snake_case；Java 的现有外部 API 不变。

| 请求字段 | 约束/来源 |
| --- | --- |
| request_id | Java 生成 UUID，用于跨服务关联 |
| owner_id、course_id、revision | Java 验证后的用户、taskId 和当前证据版本，不能来自模型 |
| evidence[] | 只发送当前 retrievable 证据，译文匹配目标语言；每项 evidence_id/text/start_ms/end_ms |
| query | 1–500 字符，非空 |
| top_k | 1–8 |
| time_window | 可选原片绝对毫秒闭区间；过滤所有不重叠的候选 |

最多 2,000 条证据、每条 8,000 字符、总计 750,000 字符、4 MiB HTTP 请求体、5,000 个 chunk。超限明确失败，不静默截取前半门课。240 字符分块、40 字符重叠，不跨证据合并；同一长证据的多个 chunk 排名后按 evidence_id 合并，返回最佳相似度。子块沿用源证据起止时间，不推算虚构时间戳。

响应包含原样作用域/request_id、index_version、snapshot_id、cache_hit、hits[]；hit 仅含 evidence_id 与 cosine score。Java 拒绝未知/重复 ID、错用户/错课程/错版本、非法 score、时间越界与过多结果，引用文本与时间始终从 Java 本次快照取得。Python 不生成回答，不返回可覆盖原文的 snippet。

## 内部身份与失效控制

`X-LectureLens-Timestamp` 为 Unix 秒，允许 60 秒时钟差；`X-LectureLens-Signature` 为如下 UTF-8 字符串的 HMAC-SHA256 十六进制值，换行均为 LF，最后没有换行：

```text
lecturelens-retrieval-v1
POST
/internal/v1/retrieve
<timestamp>
<sha256(raw HTTP body)>
```

密钥至少 32 字节。签名绑定 audience、方法、路径、时间和完整请求体，因此不能修改 owner/course/evidence 后复用。有效期内的完全相同请求允许重放，用于幂等重试；这不是一次性 token。Python 只信任持有此服务密钥的 Java，不能直接暴露为浏览器/第三方入口；跨机器部署使用私网与 TLS。Python 不读取 MySQL，不接收用户 JWT，也不接受任意外部文件 URL。

Java 在远程返回后重新读取当前证据并验证相同来源，拦截删除/重建竞态；最终 QA 持久化仍受已有 GenerationFence 保护。任何超时、验签失败、数据库/模型异常均明确失败：Python 返回 503/401/422，Java 返回 `RETRIEVAL_UNAVAILABLE`（503），不自动切换成关键词后把该结果记作 dense 成功。

## 向量投影、模型与性能取舍

首版使用随查询传送的**完整已授权快照**，按需建立缓存。snapshot_id 包含 owner/course/revision、全部证据 ID/文本/时间、index_version 的 SHA-256；查询和 top_k 不改变快照指纹。Embedding 在数据库事务外完成，所有向量及快照标记在一个短事务内发布，失败不能留下半成品 ready 状态。

pgvector 使用 cosine distance 精确扫描，SQL 在计算候选时限定快照、owner/course/revision、index_version 和时间范围。当前单课程小语料不建 HNSW，不把“使用向量数据库”误称为已经建立 ANN 索引。[pgvector 官方检索与索引说明](https://github.com/pgvector/pgvector#querying)

默认模型为 `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` 的 Qdrant ONNX 量化版本，384 维，CPU 两线程。权重固定在仓库 revision `faf4aa4225822f3bc6376869cb1164e8e3feedd0`；模型权重版本、FastEmbed 版本、分块版本共同进入 index_version。更换模型/维度/分块规则必须更新此版本，不能复用旧向量。此轻量模型用于先跑通中英检索；没有评测证据证明它是本项目最优模型。[FastEmbed 文档](https://qdrant.tech/documentation/fastembed/)

数据库只存向量、证据 ID、时间和归属，不复制源文本。快照从创建起 24 小时后逻辑过期，下一次检索时物理清理；服务无请求时不会主动清理。删除任务后旧投影不会经 Java 再被授权查询，但**尚未消费删除事件实现即时物理清除**。向量依然是需受保护的派生数据。

当前没有消费 Evidence change cursor。之后升级为后台分页快照/删除同步和显式索引状态，再移除每次查询携带全文的成本。本轮是蓝图最终同步方案之前的有界实现步骤。首次问题可能包含建索引耗时；单 worker 同时处理一个检索任务，其余返回 busy，默认 Java 总 HTTP 超时 120 秒，最多配置 5 分钟。超时后 Python 的 CPU 工作可能继续直至完成；目前不提供硬取消，也不承诺多用户吞吐。

## 本地启动

环境：Java 21、Python 3.12、uv、Docker。数据库镜像及 Python 依赖分别固定 digest / `uv.lock`。以下仅使用本地模型，不需要付费 AI Key；首次模型下载需要网络。

```bash
# 仓库根目录：准备独立配置，不覆盖已有文件
cp -n .env.agent.example .env.agent.local
python3 -c 'import secrets; print(secrets.token_hex(32))'
# 将上一步生成的值填写为 .env.agent.local 的 AGENT_SERVICE_SECRET
docker compose -f compose.agent.yml up -d --wait

cd agent-service
uv sync --locked
uv run --env-file ../.env.agent.local uvicorn lecturelens_agent.app:app --host 127.0.0.1 --port 8090
```

另一个终端通过 `curl http://127.0.0.1:8090/healthz` 检查启动完成。Java 启动环境需同时设置 `DENSE_RETRIEVAL_ENABLED=true`、相同 `AGENT_SERVICE_SECRET`、`AGENT_SERVICE_URL=http://127.0.0.1:8090`；已有 Demo/真实 AI 配置按原方式保留。Spring 不会自动读取 `.env.agent.local`，可由 IDE/启动器注入这些环境变量。Java 的回答生成仍使用原 LLM Provider；Demo 输出不能当作真实问答质量成绩。

`compose.agent.yml` 仅供本地开发，数据库端口只绑定回环地址，示例数据库口令只用于此环境。首次启动创建检索专用表，现阶段使用幂等建表引导；后续表结构升级需增加版本化数据库迁移，不修改已有 Java Flyway 历史。

停止数据库：`docker compose -f compose.agent.yml down`，保留卷。不要用 `down -v` 清理已有评测/开发数据。

## 验证与复现

```bash
cd agent-service
uv run ruff check src tests
uv run ruff format --check src tests
AGENT_TEST_DATABASE_URL=postgresql://lecturelens:lecturelens-local-only@127.0.0.1:15439/lecturelens_agent uv run pytest -q

cd ../backend
./mvnw test
# 在真实 Python 服务启动、当前 shell 已设置相同 AGENT_SERVICE_SECRET 后：
./mvnw -Dtest=DenseRetrievalLiveIT test
```

普通 CI 使用确定性 Embedding 夹具 + 真实 pgvector，避免依赖模型站点；另有可选真实模型联调测试 `DenseRetrievalLiveIT`，覆盖 Java HMAC 与 Python 验签兼容、中问英证据召回、缓存命中、时间过滤和空范围。它使用手写小夹具，不是此前课程视频的 50 题评测，也没有完整重跑长视频 ASR/OCR/VLM。

本轮验证结果记录在文末；这些检查证明契约和第一条链路可运行，不证明业务准确率提升。暂不设置未经标注校准的相似度拒答阈值；dense TopK 即使对题目不相关也可能返回候选，最终是否证据不足仍取决于现有生成约束与后续评测。

### 2026-09-11 本地验证记录

- Java 全量：1,344 tests，0 failures / errors / skipped；其中本轮新增 17 项常规测试。
- Python：24 tests 全部通过（已设置真实 pgvector 测试数据库，0 skip），Ruff lint/format 通过。测试客户端依赖有两条弃用警告，不影响本轮执行。
- `DenseRetrievalLiveIT`：1 项独立实际联调通过，包含冷缓存、热缓存、中文问英文证据、时间范围与空范围断言；运行的为本地真实 ONNX 模型，非确定性向量夹具，未调用付费 API。
- `docker compose -f compose.agent.yml config --quiet`、`git diff --check` 通过。
- 新增 Python CI job 使用锁定依赖与真实 pgvector；当前分支尚未推送，所以这些是本地结果，不是远程 CI 成绩。

2026-09-15 已完成真实课程小规模验收及前端修复，详见 [验收记录](L1_REAL_COURSE_ACCEPTANCE.md)。完整评测与增量同步仍未完成。

## 后续工作包

先把本地配置接入一个真实完成任务，检查源字幕/画面与回答引用；再补少量人工验证案例。随后做后台 Evidence 增量/删除同步与索引状态，减少冷启动和全文传输成本。Hybrid/Rerank 在有可复现对照案例后接入，L2 再引入 LangGraph 与受限工具循环。
