CREATE TABLE IF NOT EXISTS learning_package (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    source_language VARCHAR(32) NOT NULL,
    target_language VARCHAR(32) NOT NULL,
    title VARCHAR(255) NOT NULL,
    summary TEXT NOT NULL,
    key_points_json JSON NOT NULL,
    glossary_json JSON NOT NULL,
    qa_json JSON NOT NULL,
    provider VARCHAR(64) NULL,
    schema_version VARCHAR(32) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_learning_package_task_user_lang (task_id, user_id, target_language),
    KEY idx_learning_package_task_user (task_id, user_id),
    KEY idx_learning_package_user_created (user_id, created_at),
    CONSTRAINT fk_learning_package_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_learning_package_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE ON UPDATE RESTRICT
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Structured learning package table';
