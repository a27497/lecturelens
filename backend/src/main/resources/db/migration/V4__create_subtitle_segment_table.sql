CREATE TABLE IF NOT EXISTS subtitle_segment (
    id BIGINT NOT NULL AUTO_INCREMENT COMMENT 'Subtitle segment primary key',
    task_id VARCHAR(64) NOT NULL COMMENT 'Analysis task ID',
    user_id BIGINT NOT NULL COMMENT 'Owner user ID',
    segment_index INT NOT NULL COMMENT 'Segment order from ASR result',
    start_millis BIGINT NOT NULL COMMENT 'Segment start timestamp in milliseconds',
    end_millis BIGINT NOT NULL COMMENT 'Segment end timestamp in milliseconds',
    language VARCHAR(32) NOT NULL COMMENT 'Source transcription language',
    text TEXT NOT NULL COMMENT 'Source transcription text',
    provider VARCHAR(64) NULL COMMENT 'Safe ASR provider name',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) COMMENT 'Created time',
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3) COMMENT 'Updated time',
    PRIMARY KEY (id),
    UNIQUE KEY uk_subtitle_segment_task_user_index (task_id, user_id, segment_index),
    KEY idx_subtitle_segment_task_user (task_id, user_id),
    KEY idx_subtitle_segment_user_created (user_id, created_at),
    CONSTRAINT fk_subtitle_segment_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT fk_subtitle_segment_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
        ON UPDATE RESTRICT,
    CONSTRAINT chk_subtitle_segment_index_non_negative CHECK (segment_index >= 0),
    CONSTRAINT chk_subtitle_segment_start_non_negative CHECK (start_millis >= 0),
    CONSTRAINT chk_subtitle_segment_end_after_start CHECK (end_millis >= start_millis)
) ENGINE=InnoDB
  DEFAULT CHARSET=utf8mb4
  COLLATE=utf8mb4_unicode_ci
  COMMENT='Subtitle transcription segment table';
