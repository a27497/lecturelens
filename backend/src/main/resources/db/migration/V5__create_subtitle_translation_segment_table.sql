CREATE TABLE IF NOT EXISTS subtitle_translation_segment (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Subtitle translation segment primary key',
    task_id VARCHAR(64) NOT NULL COMMENT 'Analysis task ID',
    user_id BIGINT NOT NULL COMMENT 'Owner user ID',
    segment_index INT NOT NULL COMMENT 'Segment order from source transcription',
    start_millis BIGINT NOT NULL COMMENT 'Segment start timestamp in milliseconds',
    end_millis BIGINT NOT NULL COMMENT 'Segment end timestamp in milliseconds',
    source_language VARCHAR(32) NOT NULL COMMENT 'Source transcription language',
    target_language VARCHAR(32) NOT NULL COMMENT 'Target translation language',
    translated_text TEXT NOT NULL COMMENT 'Translated subtitle text',
    provider VARCHAR(64) NULL COMMENT 'Safe LLM provider name',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Created time',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_subtitle_translation_task_user_lang_index (task_id, user_id, target_language, segment_index),
    KEY idx_subtitle_translation_task_user_lang (task_id, user_id, target_language),
    KEY idx_subtitle_translation_user_created (user_id, created_at),
    CONSTRAINT fk_subtitle_translation_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_subtitle_translation_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT chk_subtitle_translation_index_non_negative CHECK (segment_index >= 0),
    CONSTRAINT chk_subtitle_translation_start_non_negative CHECK (start_millis >= 0),
    CONSTRAINT chk_subtitle_translation_end_after_start CHECK (end_millis >= start_millis)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Subtitle translation segment table';
