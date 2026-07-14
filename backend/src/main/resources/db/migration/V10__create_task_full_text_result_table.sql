CREATE TABLE IF NOT EXISTS task_full_text_result (
    id BIGINT PRIMARY KEY AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    source_language VARCHAR(32) NOT NULL,
    target_language VARCHAR(32) NOT NULL,
    source_full_text LONGTEXT NOT NULL,
    translated_full_text LONGTEXT,
    provider VARCHAR(64),
    created_at DATETIME NOT NULL,
    updated_at DATETIME NOT NULL,
    UNIQUE KEY uk_task_full_text_task_user_lang (task_id, user_id, target_language),
    KEY idx_task_full_text_task_user (task_id, user_id)
);
