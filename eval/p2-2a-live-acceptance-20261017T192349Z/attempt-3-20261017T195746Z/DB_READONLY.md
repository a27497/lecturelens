# 数据读取边界及可复核查询

此次目标只有 `task_38372ad3617f4a91b6c1f864429b5966`；执行时间 2026-10-17 19:57 UTC 后。先通过 information_schema 查指定表列名，再投影所需非凭据字段。所有数据库查询置于显式 READ ONLY 事务。MySQL 应用身份为 courselingo，PostgreSQL 应用身份为 lecturelens；复用容器已有身份，未读配置/credential 文件、未打印或持久化密码。没有登录 root/postgres 角色，没有查询用户账号、模型连接密文、worker_token 或 model_config。

容器内客户端通过本机 `nohup timeout 20s docker exec -i …` 调用。命令输出中的 MySQL `session_default_read_only=0` 是会话的**默认**值，不代表此次 `START TRANSACTION READ ONLY` 被取消；所有查询实际都包在该显式事务中。PostgreSQL 另读到 `current_setting('transaction_read_only')=on`。没有执行 DML、DDL、GRANT、锁定读取或数据库写入。

下面是主要查询的复核口径，不是让后续自动重跑的指令。所有 scope 均为同一个 task；表不存在时仅查元数据，未运行会触发错误的业务查询。

## MySQL：courselingo

先在 courselingo 和旧设计的 lecturelens_learning_loop 中精确查该 task_id，只有 courselingo 命中；没有读取无关任务正文或排障冻结的 P2-1c schema。

```sql
START TRANSACTION READ ONLY;
SELECT id,status,current_stage,progress_percent,content_revision,retry_count,
       error_code,started_at,finished_at,
       TIMESTAMPDIFF(MICROSECOND,started_at,finished_at)/1000000 AS duration_seconds,
       deleted_at IS NULL AS not_deleted
FROM courselingo.analysis_task
WHERE id='task_38372ad3617f4a91b6c1f864429b5966';

SELECT status,indexed_revision,desired_sequence,synced_sequence,index_version,
       attempts,updated_at,last_error IS NULL AS no_sync_error
FROM courselingo.evidence_index_sync
WHERE task_id='task_38372ad3617f4a91b6c1f864429b5966';

SELECT revision,source_type,COUNT(*) AS evidence_count,
       MIN(start_ms),MAX(end_ms)
FROM courselingo.course_evidence
WHERE task_id='task_38372ad3617f4a91b6c1f864429b5966'
GROUP BY revision,source_type;

SELECT e.evidence_id,e.revision,e.source_type,e.start_ms,e.end_ms,
       JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.contentHash')) AS content_hash,
       JSON_UNQUOTE(JSON_EXTRACT(e.payload,'$.normalizedText')) AS normalized_text,
       JSON_EXTRACT(e.payload,'$.retrievable') AS retrievable,
       e.user_id=t.user_id AS owner_matches_task
FROM courselingo.course_evidence e
JOIN courselingo.analysis_task t ON t.id=e.task_id
WHERE e.task_id='task_38372ad3617f4a91b6c1f864429b5966'
  AND e.revision=t.content_revision
ORDER BY e.source_type,e.start_ms;

SELECT call_type,stage,provider,model,status,started_at,finished_at,
       duration_millis,provider_duration_millis,batch_count,retry_count,
       prompt_tokens,completion_tokens,total_tokens,input_units,output_units,error_code
FROM courselingo.ai_call_record
WHERE task_id='task_38372ad3617f4a91b6c1f864429b5966'
ORDER BY started_at,id;

SELECT feature,model,provider_attempt,segment_count,http_status,validation_category,
       prompt_tokens,completion_tokens,total_tokens,duration_millis,created_at
FROM courselingo.translation_call_diagnostic
WHERE task_id='task_38372ad3617f4a91b6c1f864429b5966' ORDER BY created_at;

SELECT stage,level,created_at FROM courselingo.task_log
WHERE task_id='task_38372ad3617f4a91b6c1f864429b5966' ORDER BY created_at,id LIMIT 200;

SELECT provider,COUNT(*),MIN(start_millis),MAX(end_millis)
FROM courselingo.subtitle_segment
WHERE task_id='task_38372ad3617f4a91b6c1f864429b5966' GROUP BY provider;
COMMIT;
```

另外投影该 task 的 artifact_file 类型/语言/大小/创建时间，查得 SRT、VTT、MARKDOWN、JSON 各一份；未读取 object_key 或带签名 URL。task_transcript 投影 provider/model/segment_count/时间返回空集，不将其当作“没有字幕”；实际字幕已由 subtitle_segment 和 course_evidence 确认。task_execution 的元数据只有 task/event/lease/completed 字段，没有阶段耗时字段。用量事实来自 ai_call_record 与 translation_call_diagnostic，没有取得费用账单。

## PostgreSQL：lecturelens_agent

```sql
BEGIN READ ONLY;
SELECT current_user,current_database(),current_setting('transaction_read_only');
SELECT course_id,revision,sequence,index_version,state,updated_at FROM evidence_index
WHERE course_id='task_38372ad3617f4a91b6c1f864429b5966';
SELECT e.evidence_id,e.start_ms,e.end_ms,e.content_hash,i.revision
FROM indexed_evidence e JOIN evidence_index i USING(owner_id,course_id)
WHERE e.course_id='task_38372ad3617f4a91b6c1f864429b5966';
SELECT session_id,revision,created_at FROM study_session
WHERE course_id='task_38372ad3617f4a91b6c1f864429b5966' ORDER BY created_at;
SELECT r.run_id,r.session_id,r.goal,r.status,r.model_mode,r.model_calls,r.tool_calls,
       r.reserved_tokens,r.error_code,r.created_at,r.finished_at
FROM study_run r JOIN study_session s USING(session_id)
WHERE s.course_id='task_38372ad3617f4a91b6c1f864429b5966';
SELECT COUNT(*) FROM study_event e JOIN study_run r USING(run_id)
JOIN study_session s USING(session_id)
WHERE s.course_id='task_38372ad3617f4a91b6c1f864429b5966';
SELECT COUNT(*) FROM study_tool_result t JOIN study_run r USING(run_id)
JOIN study_session s USING(session_id)
WHERE s.course_id='task_38372ad3617f4a91b6c1f864429b5966';
SELECT COUNT(*) FROM study_artifact a JOIN study_run r USING(run_id)
JOIN study_session s USING(session_id)
WHERE s.course_id='task_38372ad3617f4a91b6c1f864429b5966';
COMMIT;
```

派生索引与权威快照按 evidence_id 匹配，比较起止时间、content_hash 和 revision；owner/task 一致性在 MySQL 查询内核对。两次读取不是跨库原子快照，不把结果推广到其他 revision 或未来状态。没有模型引用，所以此比对不能代替 DESIGN 的引用文本/语义及浏览器实际跳秒验收。

## 窄时间窗日志

只读查询 live-agent/live-backend 两个 unit 的 journal，窗口为 `2026-10-17 19:55:40 UTC` 至 `19:56:05 UTC`；命令使用 nohup+timeout。解析器只输出 Study command HTTP 状态、限定的数据库异常类型和 STUDY 错误码，不输出完整日志、请求体、认证头或其他任务内容。留下三个 Agent HTTP 状态记录，无请求关联 ID/响应正文；backend 匹配项为空。空匹配不代表后端没有其他日志，更不证明配置无误。
