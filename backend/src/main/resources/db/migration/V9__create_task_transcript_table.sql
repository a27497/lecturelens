CREATE TABLE IF NOT EXISTS task_transcript (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Task transcript primary key',
    task_id VARCHAR(64) NOT NULL COMMENT 'Analysis task ID',
    user_id BIGINT NOT NULL COMMENT 'Owner user ID',
    source_language VARCHAR(32) NOT NULL COMMENT 'Source transcription language',
    target_language VARCHAR(32) NOT NULL COMMENT 'Target translation language',
    source_text MEDIUMTEXT NOT NULL COMMENT 'Cleaned source full transcript',
    translated_text MEDIUMTEXT NULL COMMENT 'Translated full transcript',
    segment_count INT NOT NULL COMMENT 'Source subtitle segment count',
    provider VARCHAR(64) NULL COMMENT 'Safe LLM provider name',
    model VARCHAR(128) NULL COMMENT 'Safe LLM model name',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Created time',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_task_transcript_task_user_lang (task_id, user_id, target_language),
    KEY idx_task_transcript_task_user (task_id, user_id),
    KEY idx_task_transcript_user_created (user_id, created_at),
    CONSTRAINT fk_task_transcript_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_task_transcript_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT chk_task_transcript_segment_count_positive CHECK (segment_count > 0)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Cleaned full transcript and full translation table';
