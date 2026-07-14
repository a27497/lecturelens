CREATE TABLE IF NOT EXISTS course_qa_record (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    question VARCHAR(1000) NOT NULL,
    answer TEXT NOT NULL,
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
    KEY idx_course_qa_task_user_created (task_id, user_id, created_at),
    KEY idx_course_qa_user_created (user_id, created_at),
    CONSTRAINT fk_course_qa_record_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_course_qa_record_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT chk_course_qa_record_status CHECK (status IN ('SUCCEEDED', 'FAILED')),
    CONSTRAINT chk_course_qa_record_duration_non_negative CHECK (duration_millis IS NULL OR duration_millis >= 0),
    CONSTRAINT chk_course_qa_record_prompt_tokens_non_negative CHECK (prompt_tokens IS NULL OR prompt_tokens >= 0),
    CONSTRAINT chk_course_qa_record_completion_tokens_non_negative CHECK (completion_tokens IS NULL OR completion_tokens >= 0),
    CONSTRAINT chk_course_qa_record_total_tokens_non_negative CHECK (total_tokens IS NULL OR total_tokens >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Course-scoped QA records with sanitized evidence';
