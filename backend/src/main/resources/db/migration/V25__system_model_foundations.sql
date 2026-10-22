ALTER TABLE user_account
    ADD COLUMN role VARCHAR(16) CHARACTER SET ascii COLLATE ascii_bin NOT NULL DEFAULT 'USER',
    ADD CONSTRAINT chk_user_account_role CHECK (role IN ('USER', 'ADMIN'));

CREATE TABLE system_model_provider (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    name VARCHAR(128) NOT NULL,
    protocol VARCHAR(32) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    base_url VARCHAR(2048) NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    api_key_ciphertext VARCHAR(8192) CHARACTER SET ascii COLLATE ascii_bin NULL,
    key_last4 VARCHAR(4) NULL,
    row_version BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    CONSTRAINT chk_system_provider_protocol CHECK (protocol IN ('OPENAI_CHAT', 'BAILIAN_ASR', 'SILICONFLOW_ASR')),
    CONSTRAINT chk_system_provider_key CHECK (
        (api_key_ciphertext IS NULL AND key_last4 IS NULL) OR
        (api_key_ciphertext IS NOT NULL AND api_key_ciphertext LIKE 'v1.%' AND CHAR_LENGTH(key_last4) = 4 AND key_last4 IS NOT NULL)
    ),
    CONSTRAINT chk_system_provider_version CHECK (row_version >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE system_model (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    provider_id BIGINT NOT NULL,
    model_id VARCHAR(256) COLLATE utf8mb4_bin NOT NULL,
    capabilities JSON NOT NULL,
    parameters JSON NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    row_version BIGINT NOT NULL DEFAULT 0,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    updated_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3) ON UPDATE CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_system_model_provider_name (provider_id, model_id),
    CONSTRAINT fk_system_model_provider FOREIGN KEY (provider_id) REFERENCES system_model_provider(id),
    CONSTRAINT chk_system_model_version CHECK (row_version >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE system_model_binding (
    feature_key VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL PRIMARY KEY,
    model_id BIGINT NOT NULL,
    CONSTRAINT fk_system_binding_model FOREIGN KEY (model_id) REFERENCES system_model(id),
    CONSTRAINT chk_system_binding_feature CHECK (feature_key IN (
        'TRANSLATION_FULL_TEXT', 'SUBTITLE_TRANSLATION', 'LEARNING_PACKAGE', 'COURSE_QA',
        'COURSE_CHAPTER', 'VISION_FRAME_ANALYSIS', 'ASR_TRANSCRIPTION'
    ))
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Version payloads contain encrypted credentials; no HTTP response may serialize the raw payload.
-- LONGTEXT preserves canonical JSON bytes for reproducible SHA-256 verification.
CREATE TABLE system_model_config_version (
    version BIGINT NOT NULL PRIMARY KEY,
    parent_version BIGINT NULL,
    config_json LONGTEXT NOT NULL,
    config_sha256 CHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
    actor_user_id BIGINT NULL,
    reason VARCHAR(256) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    CONSTRAINT fk_system_version_parent FOREIGN KEY (parent_version) REFERENCES system_model_config_version(version),
    CONSTRAINT chk_system_version_json CHECK (JSON_VALID(config_json)),
    CONSTRAINT chk_system_version_number CHECK (version >= 0)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO system_model_config_version (version, config_json, config_sha256, reason)
VALUES (0, '{"providers":[],"models":[],"bindings":{}}',
    SHA2('{"providers":[],"models":[],"bindings":{}}', 256), 'INITIAL_EMPTY_CONFIG');

CREATE TABLE system_model_config_state (
    id TINYINT NOT NULL PRIMARY KEY,
    current_version BIGINT NOT NULL,
    CONSTRAINT chk_system_config_singleton CHECK (id = 1),
    CONSTRAINT fk_system_config_current FOREIGN KEY (current_version) REFERENCES system_model_config_version(version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

INSERT INTO system_model_config_state (id, current_version) VALUES (1, 0);

-- Actor IDs intentionally have no user FK: deleting an account must not rewrite immutable history.
CREATE TABLE system_model_audit (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    config_version BIGINT NULL,
    actor_type VARCHAR(32) NOT NULL,
    actor_user_id BIGINT NULL,
    action VARCHAR(64) NOT NULL,
    object_type VARCHAR(32) NOT NULL,
    object_id VARCHAR(64) NOT NULL,
    safe_changes JSON NOT NULL,
    request_id VARCHAR(64) NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY idx_system_audit_version (config_version, id),
    KEY idx_system_audit_actor (actor_user_id, id),
    CONSTRAINT fk_system_audit_version FOREIGN KEY (config_version) REFERENCES system_model_config_version(version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Execution snapshots never contain credentials, including ciphertext. Resolve secrets through config_version.
CREATE TABLE system_model_execution_snapshot (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    operation_type VARCHAR(64) NOT NULL,
    operation_id VARCHAR(64) NOT NULL,
    config_version BIGINT NOT NULL,
    resolved_config_json JSON NOT NULL,
    snapshot_origin VARCHAR(32) NOT NULL DEFAULT 'CREATED',
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    UNIQUE KEY uk_system_snapshot_operation (task_id, operation_type, operation_id),
    KEY idx_system_snapshot_owner (task_id, user_id),
    CONSTRAINT fk_system_snapshot_task FOREIGN KEY (task_id) REFERENCES analysis_task(id) ON DELETE CASCADE,
    CONSTRAINT fk_system_snapshot_user FOREIGN KEY (user_id) REFERENCES user_account(id) ON DELETE CASCADE,
    CONSTRAINT fk_system_snapshot_version FOREIGN KEY (config_version) REFERENCES system_model_config_version(version)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER system_model_version_no_update BEFORE UPDATE ON system_model_config_version
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'System model versions are immutable';

CREATE TRIGGER system_model_version_no_delete BEFORE DELETE ON system_model_config_version
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'System model versions are immutable';

CREATE TRIGGER system_model_audit_no_update BEFORE UPDATE ON system_model_audit
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'System model audit is append only';

CREATE TRIGGER system_model_audit_no_delete BEFORE DELETE ON system_model_audit
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'System model audit is append only';
