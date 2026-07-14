CREATE TABLE IF NOT EXISTS video_keyframe_ocr (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    keyframe_id BIGINT NOT NULL,
    timestamp_millis BIGINT NOT NULL,
    provider VARCHAR(64) NOT NULL,
    language_hint VARCHAR(64) NOT NULL,
    ocr_text TEXT NULL,
    text_length INT NOT NULL DEFAULT 0,
    text_truncated TINYINT(1) NOT NULL DEFAULT 0,
    confidence DECIMAL(5,4) NULL,
    status VARCHAR(32) NOT NULL,
    error_code VARCHAR(64) NULL,
    error_message VARCHAR(255) NULL,
    duration_millis BIGINT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    PRIMARY KEY (id),
    UNIQUE KEY uk_video_keyframe_ocr_keyframe (keyframe_id),
    KEY idx_video_keyframe_ocr_task_user_time (task_id, user_id, timestamp_millis),
    CONSTRAINT fk_video_keyframe_ocr_keyframe_id
        FOREIGN KEY (keyframe_id) REFERENCES video_keyframe (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_video_keyframe_ocr_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_video_keyframe_ocr_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
