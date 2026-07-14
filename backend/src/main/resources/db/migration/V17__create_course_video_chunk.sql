CREATE TABLE IF NOT EXISTS course_video_chunk (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    target_language VARCHAR(32) NOT NULL,
    chunk_index INT NOT NULL,
    start_millis BIGINT NOT NULL,
    end_millis BIGINT NOT NULL,
    time_text VARCHAR(64) NOT NULL,
    summary TEXT NOT NULL,
    keywords_json JSON NOT NULL,
    evidence_json JSON NOT NULL,
    source_text_preview TEXT NULL,
    translated_text_preview TEXT NULL,
    build_version VARCHAR(32) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_course_video_chunk_task_user_lang_index (task_id, user_id, target_language, chunk_index),
    KEY idx_course_video_chunk_task_user_time (task_id, user_id, start_millis),
    KEY idx_course_video_chunk_user_created (user_id, created_at),
    CONSTRAINT fk_course_video_chunk_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_course_video_chunk_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT chk_course_video_chunk_index_non_negative CHECK (chunk_index >= 0),
    CONSTRAINT chk_course_video_chunk_start_non_negative CHECK (start_millis >= 0),
    CONSTRAINT chk_course_video_chunk_time_order CHECK (end_millis > start_millis)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Rule-based course video context chunks';
