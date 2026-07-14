CREATE TABLE IF NOT EXISTS artifact_file (
    id BIGINT NOT NULL AUTO_INCREMENT,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    artifact_type VARCHAR(32) NOT NULL,
    language VARCHAR(32) NOT NULL,
    file_name VARCHAR(255) NOT NULL,
    content_type VARCHAR(128) NOT NULL,
    storage_backend VARCHAR(32) NOT NULL,
    object_key VARCHAR(512) NOT NULL,
    size_bytes BIGINT NOT NULL,
    sha256 VARCHAR(64) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    PRIMARY KEY (id),
    UNIQUE KEY uk_artifact_file_task_user_type_lang (task_id, user_id, artifact_type, language),
    UNIQUE KEY uk_artifact_file_object_key (object_key),
    KEY idx_artifact_file_task_user (task_id, user_id),
    KEY idx_artifact_file_user_created (user_id, created_at),
    CONSTRAINT fk_artifact_file_task_id
        FOREIGN KEY (task_id) REFERENCES analysis_task (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT fk_artifact_file_user_id
        FOREIGN KEY (user_id) REFERENCES user_account (id)
        ON DELETE CASCADE ON UPDATE RESTRICT,
    CONSTRAINT chk_artifact_file_size_non_negative CHECK (size_bytes >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci COMMENT='Artifact file table';
