CREATE TABLE IF NOT EXISTS course_chapter (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    chapter_index INT NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    keywords_json JSON NOT NULL,
    start_millis BIGINT NOT NULL,
    end_millis BIGINT NOT NULL,
    evidence_json JSON NOT NULL,
    status VARCHAR(32) NOT NULL,
    provider VARCHAR(64) NULL,
    model VARCHAR(128) NULL,
    prompt_tokens INT NULL,
    completion_tokens INT NULL,
    total_tokens INT NULL,
    duration_millis BIGINT NULL,
    error_code VARCHAR(64) NULL,
    error_message_summary VARCHAR(512) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_course_chapter_task_user_index (task_id, user_id, chapter_index),
    KEY idx_course_chapter_user_task (user_id, task_id),
    KEY idx_course_chapter_user_created (user_id, created_at),
    CONSTRAINT fk_course_chapter_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_course_chapter_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT chk_course_chapter_status CHECK (status IN ('SUCCEEDED', 'FAILED')),
    CONSTRAINT chk_course_chapter_time_order CHECK (end_millis > start_millis),
    CONSTRAINT chk_course_chapter_duration_non_negative CHECK (duration_millis IS NULL OR duration_millis >= 0),
    CONSTRAINT chk_course_chapter_prompt_tokens_non_negative CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    CONSTRAINT chk_course_chapter_completion_tokens_non_negative CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
    CONSTRAINT chk_course_chapter_total_tokens_non_negative CHECK (total_tokens IS NULL OR total_tokens >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='On-demand course chapter timeline records';
