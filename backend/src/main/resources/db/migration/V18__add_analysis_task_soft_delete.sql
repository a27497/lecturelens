ALTER TABLE analysis_task
    ADD COLUMN deleted_at DATETIME(3) NULL COMMENT '用户逻辑删除时间，NULL表示未删除' AFTER finished_at,
    ADD KEY idx_analysis_task_user_deleted_created (user_id, deleted_at, created_at),
    ADD KEY idx_analysis_task_user_deleted_status_created (user_id, deleted_at, status, created_at);
