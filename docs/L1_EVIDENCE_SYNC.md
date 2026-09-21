# Evidence 后台增量同步与索引状态

日期：2026-09-15。接续首条 dense 链路，作为 L2 Study Agent 的检索基础。

## 行为

- 源数据事务同时写 `evidence_change` 和 `evidence_index_sync`，同一课程的待同步工作合并到最新 sequence。视频成功后后台建立不可变 Evidence 快照并同步，不需要用户先提问。V24 将存量任务加入同步队列。
- Java `PLAN` 发送证据 ID、规范文本 SHA-256、原始时间范围；Python 返回缺失 ID。`APPLY` 只发送缺失正文。revision 导致证据 ID 变化时，相同文本仍可在课程内按哈希复制原向量，无需重传正文或重新嵌入。变化文本内未变的 chunk 也按哈希复用。
- 问答发送 owner/course/revision、问题、允许的 Evidence ID 和时间范围，不发送证据正文，不建立文档向量。允许 ID 保留目标语言筛选；Java 用本地权威快照解析引用并在远程返回后重新检查删除/版本。
- Python 原子发布新版本及删除旧条目。空 manifest 是合法空索引。没有 24 小时失效或依赖后续查询清理的机制。
- 课程删除仍先在 Java 立即阻断访问；独立删除调度通道每 3 秒尝试物理清理 Python 的证据元数据/向量，并持久保存无正文 tombstone。删除会撤销较早的同步 claim；晚到请求不能恢复已删课程。

## 数据与故障边界

Java V24 新增 `evidence_index_sync`：desired/synced sequence、indexed revision、模型版本、状态、重试次数、下次执行时间、租约和脱敏错误类型。状态为 `PENDING / INDEXING / READY / FAILED / DELETED`；功能关闭时外部返回 `DISABLED`。

claim 与结果确认使用短事务，网络和嵌入在事务外执行。成功确认必须仍匹配 claim ID 和 desired sequence。进程中断后的 claim 最多 660 秒释放（覆盖当前最多两次各 5 分钟的 HTTP 请求）；失败按 3 秒起步、最高 300 秒退避自动重试，不丢弃任务。单课程失败不会阻止其他到期课程工作。

READY/DELETED 每 300 秒重新比对远程状态，以恢复投影丢失和模型版本变化。状态 API 是最后一次同步确认，加当前源版本检查；不是远程服务的实时健康承诺。远程离线或新模型尚未准备好时，查询明确失败，不静默使用另一种检索模式。

Python 在 `evidence_index` 保留课程 sequence、revision、index_version 与状态，在 `indexed_evidence / evidence_vector` 保存当前投影。schema version 2 使用数据库锁进行幂等启动迁移，首次迁移移除 v1 可重建缓存表，旧向量不再遗留；源 Evidence 和历史 QA 在 Java 中保持原有保留规则。新版本完整发布前旧版本留在库中，但新 revision 查询不能命中旧版本；发布失败回滚，不出现半成品 READY。

部署需成套更新 Java/Python 并执行 Flyway V24。查询 JSON 已去除旧 `evidence[]` 字段，旧 Java/Python 混用会明确报契约错误。Python 多 worker 必须运行相同模型和分块版本。当前精确扫描、小课程上限保持 2,000 条 Evidence、5,000 chunks；单次新增正文上限 750,000 字符 / 4 MiB，每条 8,000 字符。超限会记录 FAILED 并重试，不静默截断。

## API

`GET /api/tasks/{taskId}/evidence/index-status` 使用现有用户鉴权与 owner scope。只读，不触发快照/索引；返回：

```json
{
  "status": "READY",
  "revision": 7,
  "indexedRevision": 7,
  "indexVersion": "模型与分块版本",
  "attempts": 0,
  "lastError": null,
  "updatedAt": "最后确认时间"
}
```

实际响应仍包在现有 `ApiResponse.data`。删除或其他用户课程返回 404。课程问答面板自动刷新状态，资料待更新/更新中/失败时显示相应文案，READY 后可提问；停用 dense 时保留原问答模式。

`POST /internal/v1/evidence/sync`：`operation=PLAN/APPLY/DELETE`，公共字段为 request_id、owner_id、course_id、revision、sequence；manifest 每项为 evidence_id/content_hash/start_ms/end_ms，APPLY 额外含 upserts 和 PLAN 返回的 index_version。正文哈希和时间必须与 manifest 一致。DELETE 必须为空清单。响应回显 scope、sequence、index_version、state 和 missing_ids。

内部 HMAC 仍绑定 audience、POST、**实际路径**、60 秒时间窗口、原始请求体 SHA-256；不同端点签名不能互换。查询索引未就绪返回 409；忙/数据库/嵌入错误返回 503；Java 对外保持 `RETRIEVAL_UNAVAILABLE`。浏览器不直接访问 Python。

## 与蓝图的实现差异

蓝图建议 Python 拉取分页快照和全局游标。本轮采用 Java 源事务内合并的持久工作表，Java 后台向 Python 推送清单与差量，复用已有服务签名，避免新增反向内部授权入口。`evidence_change` 继续保留完整变更历史；工作表使用其提交有序 sequence 来确认版本，独立课程可以重试，无全局失败游标阻塞。不是新增 MQ 消费，也不是每次请求全文缓存。

仍有边界：大于上述课程上限时尚无分批 staging 上传；进程硬取消/更高并发吞吐不在本轮。L1 的完整人工评测、Hybrid/Rerank 没有随本轮自动完成。

## L2 接入点

L2 的 `search_evidence` 应复用此 READY/revision/owner 契约，工具返回稳定 Evidence ID，由 Java 校验授权并解析引文。无需让 Agent 触发索引，或把全文存入 Session/checkpoint。待更新时返回可重试的资料状态；课程删除后工具拒绝访问，历史引用只显示失效状态。

后续 L2 工作按蓝图实现 Session/Run/checkpoint、受限工具循环、解释+出题产物、事件流、取消与恢复。本文不将上述规划记为已经实现的 Study Agent。

## 验证

自动覆盖：首次查询不建索引、签名路径绑定、差量正文、跨 revision 哈希复用、无查询删除、tombstone 防晚到恢复、版本乱序、事务回滚、空索引、跨用户/课程/版本隔离、索引模型切换、重启恢复、Java 过期 claim/失败重试/删除撤销 claim、前端状态轮询与切换课程时的响应隔离。

本轮本地执行结果：

- Java 全量 1,352 tests，0 failures / errors / skipped；后端打包通过。
- Python 33 tests，真实 pgvector，0 skipped；Ruff lint / format 通过。
- 前端 40 tests / 13 files 与 production build 通过。
- 独立 `DenseRetrievalLiveIT` 通过：Java 签名 PLAN/APPLY → Python 本地真实多语言 ONNX Embedding → pgvector → 中问英引用与时间过滤 → DELETE。
- 隔离 MySQL 8.4 使用项目的 `utf8mb4_unicode_ci` 排序规则，全量 V1–V24 空库 SQL 与 V24 存量回填验证通过。本轮直接执行迁移 SQL；没有重跑整个 MQ/MinIO/媒体 pipeline 的联合 E2E。
- `git diff --check` 通过。

测试客户端仍有 2 条依赖弃用警告，前端仍有既存的大 chunk / PURE 注释警告，均不阻断本轮检查。没有调用付费模型 API、没有重跑长视频分析、没有声称检索质量评测达标。改动已在本地验证，尚未部署。
