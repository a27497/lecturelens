-- Additive repeatable migration keeps the version watermark at V25: the pending
-- long-course branch owns V26-V31. Both integration orders work without outOfOrder.
-- A single ALTER is atomic on MySQL 8; rerunning after a crash is harmless.
SET @qa_model_usage_ddl = IF(
    (SELECT COUNT(*) FROM information_schema.columns
     WHERE table_schema = DATABASE() AND table_name = 'course_qa_record'
       AND column_name = 'execution_snapshot_id') = 0,
    'ALTER TABLE course_qa_record ADD COLUMN execution_snapshot_id VARCHAR(64) NULL, ADD COLUMN invocation_state VARCHAR(32) NULL, ADD COLUMN ai_call_record_id BIGINT NULL',
    'SELECT 1'
);
PREPARE qa_model_usage_stmt FROM @qa_model_usage_ddl;
EXECUTE qa_model_usage_stmt;
DEALLOCATE PREPARE qa_model_usage_stmt;
