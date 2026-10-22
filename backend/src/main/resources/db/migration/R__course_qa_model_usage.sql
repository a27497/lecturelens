-- Keep the version watermark at V25; the pending long-course branch owns V26-V31.
-- Inspect every column: an existing execution reference does not prove that the
-- other two columns exist. Add only missing columns in one atomic MySQL 8 ALTER.
SET @ll_qa_usage_incompatible = (
    SELECT COUNT(*) FROM information_schema.columns
    WHERE table_schema = DATABASE() AND table_name = 'course_qa_record'
      AND column_name IN ('execution_snapshot_id', 'invocation_state', 'ai_call_record_id')
      AND NOT (
          is_nullable = 'YES' AND (
              (column_name = 'execution_snapshot_id' AND data_type = 'varchar' AND character_maximum_length = 64) OR
              (column_name = 'invocation_state' AND data_type = 'varchar' AND character_maximum_length = 32) OR
              (column_name = 'ai_call_record_id' AND data_type = 'bigint' AND column_type NOT LIKE '%unsigned%')
          )
      )
);
-- SIGNAL is not preparable in MySQL. Evaluating invalid JSON only on the
-- incompatible branch fails before DDL; never silently convert existing facts.
SET @ll_qa_usage_schema_check = IF(@ll_qa_usage_incompatible = 0, 1,
    JSON_EXTRACT('Incompatible course_qa_record model usage column definition', '$'));
SET @ll_qa_usage_additions = CONCAT_WS(', ',
    IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'course_qa_record' AND column_name = 'execution_snapshot_id') = 0,
        'ADD COLUMN execution_snapshot_id VARCHAR(64) NULL', NULL),
    IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'course_qa_record' AND column_name = 'invocation_state') = 0,
        'ADD COLUMN invocation_state VARCHAR(32) NULL', NULL),
    IF((SELECT COUNT(*) FROM information_schema.columns WHERE table_schema = DATABASE() AND table_name = 'course_qa_record' AND column_name = 'ai_call_record_id') = 0,
        'ADD COLUMN ai_call_record_id BIGINT NULL', NULL)
);
SET @ll_qa_usage_ddl = IF(@ll_qa_usage_additions = '', 'SELECT 1',
    CONCAT('ALTER TABLE course_qa_record ', @ll_qa_usage_additions));
PREPARE ll_qa_usage_stmt FROM @ll_qa_usage_ddl;
EXECUTE ll_qa_usage_stmt;
DEALLOCATE PREPARE ll_qa_usage_stmt;
