ALTER TABLE translation_attempt
    ADD COLUMN reasoning_tokens INT NULL,
    ADD COLUMN cache_hit_tokens INT NULL,
    ADD COLUMN cache_miss_tokens INT NULL,
    ADD COLUMN usage_status VARCHAR(64) NOT NULL DEFAULT 'UNOBSERVED_LEGACY',
    ADD COLUMN validation_check VARCHAR(64) NULL;
ALTER TABLE translation_call_diagnostic ADD COLUMN attempt_id VARCHAR(64) NULL;

CREATE TABLE model_price_card (
    id VARCHAR(100) NOT NULL PRIMARY KEY,
    provider_model VARCHAR(128) NOT NULL,
    currency VARCHAR(8) NOT NULL,
    source_url VARCHAR(512) NOT NULL,
    checked_at DATE NOT NULL,
    rate_json JSON NOT NULL,
    card_sha256 CHAR(64) NOT NULL
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE model_call_attempt (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    snapshot_id VARCHAR(64) NOT NULL,
    config_version BIGINT NOT NULL,
    execution_epoch BIGINT NOT NULL,
    execution_event VARCHAR(64) NOT NULL,
    feature VARCHAR(64) NOT NULL,
    model VARCHAR(128) NOT NULL,
    response_model_sha256 CHAR(64) NULL,
    provider_fingerprint_sha256 CHAR(64) NULL,
    route_source VARCHAR(32) NOT NULL,
    translation_attempt_id VARCHAR(64) NULL,
    request_address VARCHAR(1024) NOT NULL,
    request_body_hash CHAR(64) NOT NULL,
    request_body_bytes BIGINT NOT NULL,
    request_summary JSON NOT NULL,
    audio_start_millis BIGINT NULL,
    audio_end_millis BIGINT NULL,
    timing_source VARCHAR(32) NULL,
    silence_plan_hash CHAR(64) NULL,
    silence_segmentation BOOLEAN NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'STARTED',
    http_status INT NULL,
    prompt_tokens INT NULL,
    completion_tokens INT NULL,
    total_tokens INT NULL,
    reasoning_tokens INT NULL,
    cache_hit_tokens INT NULL,
    cache_miss_tokens INT NULL,
    finish_reason VARCHAR(64) NULL,
    error_category VARCHAR(64) NULL,
    validation_check VARCHAR(64) NULL,
    usage_status VARCHAR(64) NOT NULL DEFAULT 'AWAITING_RESPONSE',
    duration_millis BIGINT NULL,
    price_card_id VARCHAR(100) NULL,
    price_tier VARCHAR(64) NULL,
    currency VARCHAR(8) NULL,
    cost_lower DECIMAL(24,12) NULL,
    cost_upper DECIMAL(24,12) NULL,
    private_error_excerpt TEXT NULL,
    response_chars INT NULL,
    response_truncated BOOLEAN NOT NULL DEFAULT FALSE,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    completed_at DATETIME(3) NULL,
    UNIQUE KEY uk_model_call_translation(translation_attempt_id),
    KEY idx_model_call_task(task_id,feature,created_at),
    CONSTRAINT fk_model_call_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE,
    CONSTRAINT fk_model_call_price FOREIGN KEY(price_card_id) REFERENCES model_price_card(id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER model_price_no_update BEFORE UPDATE ON model_price_card
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Price cards are immutable';
