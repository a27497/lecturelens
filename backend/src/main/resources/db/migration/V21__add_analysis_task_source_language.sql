ALTER TABLE analysis_task
    ADD COLUMN source_language VARCHAR(32) NULL AFTER target_language;

ALTER TABLE ai_call_record
    ADD COLUMN provider_duration_millis BIGINT NULL AFTER duration_millis,
    ADD COLUMN batch_count INT NULL AFTER provider_duration_millis,
    ADD COLUMN retry_count INT NULL AFTER batch_count;
