-- PREVIEW ONLY. Run exclusively in the new isolated schema after authorized trials.
-- Bind @task and @user for one owned evaluation task. Never export credential/config JSON columns.
SELECT id,status,current_stage AS stage,error_code,created_at,started_at,finished_at FROM analysis_task WHERE id=@task AND user_id=@user;
SELECT p.task_id,p.snapshot_id,p.config_version,p.engine_version,p.policy_hash,p.prompt_hash,p.deadline
 FROM pipeline_policy_snapshot p WHERE p.task_id=@task AND p.user_id=@user;
SELECT s.id,s.config_version,JSON_UNQUOTE(JSON_EXTRACT(s.resolved_config_json,'$.routes.TRANSLATION_FULL_TEXT.source')) AS translation_source,
 JSON_UNQUOTE(JSON_EXTRACT(s.resolved_config_json,'$.routes.TRANSLATION_FULL_TEXT.model')) AS translation_model
 FROM system_model_execution_snapshot s WHERE s.task_id=@task AND s.user_id=@user AND s.operation_type='PIPELINE';
SELECT e.task_id,e.event_id,e.execution_epoch,e.resume_count,e.lease_until,e.completed_at FROM task_execution e
 JOIN analysis_task t ON t.id=e.task_id WHERE t.id=@task AND t.user_id=@user;
SELECT b.batch_no,b.config_version,b.parent_batch_no,b.child_ordinal,b.depth,b.source_hash,b.request_hash,b.status,b.result_hash,b.attempt_count,b.last_error_category
 FROM translation_batch b JOIN analysis_task t ON t.id=b.task_id WHERE t.id=@task AND t.user_id=@user ORDER BY b.batch_no;
SELECT a.id,a.feature,a.config_version,a.execution_epoch,a.translation_attempt_id,a.model,a.response_model_sha256,a.provider_fingerprint_sha256,
 a.status,a.http_status,a.prompt_tokens,a.completion_tokens,a.total_tokens,a.reasoning_tokens,a.cache_hit_tokens,a.cache_miss_tokens,
 a.finish_reason,a.error_category,a.validation_check,a.usage_status,a.duration_millis,a.price_card_id,a.price_tier,a.currency,a.cost_lower,a.cost_upper,
 a.audio_start_millis,a.audio_end_millis,a.timing_source,a.silence_plan_hash,a.silence_segmentation,a.created_at,a.completed_at
 FROM model_call_attempt a WHERE a.task_id=@task AND a.user_id=@user ORDER BY a.created_at,a.id;
SELECT feature,currency,COUNT(*) physical_calls,SUM(prompt_tokens) known_input_tokens,SUM(completion_tokens) known_output_tokens,
 SUM(cost_lower) known_cost_lower,SUM(cost_upper) known_cost_upper,SUM(cost_lower IS NULL) unknown_cost_calls
 FROM model_call_attempt WHERE task_id=@task AND user_id=@user GROUP BY feature,currency;
SELECT event_seq,event_time,execution_epoch,batch_no,attempt_no,old_window,new_window,inflight,window_epoch,success_streak,reason,cooldown_until_millis
 FROM translation_scheduler_event WHERE task_id=@task AND user_id=@user ORDER BY event_seq;
-- Private 400 error excerpt: keep outside Git; hash exported files. No requests/headers or configuration originals.
SELECT id,request_address,request_body_hash,request_body_bytes,request_summary,http_status,response_chars,response_truncated,private_error_excerpt
 FROM model_call_attempt WHERE task_id=@task AND user_id=@user AND http_status=400;
