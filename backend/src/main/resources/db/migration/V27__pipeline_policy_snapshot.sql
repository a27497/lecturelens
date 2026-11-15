-- Execution policy is immutable and contains no credential material.
CREATE TABLE pipeline_policy_snapshot (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    snapshot_id VARCHAR(64) NOT NULL,
    config_version BIGINT NOT NULL,
    engine_version VARCHAR(64) NOT NULL,
    policy_json JSON NOT NULL,
    policy_hash CHAR(64) NOT NULL,
    prompt_hash CHAR(64) NOT NULL,
    tokenizer_identity VARCHAR(64) NOT NULL,
    media_identity_hash CHAR(64) NOT NULL,
    deadline DATETIME(3) NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY idx_pipeline_policy_owner (task_id,user_id),
    CONSTRAINT fk_pipeline_policy_task FOREIGN KEY (task_id) REFERENCES analysis_task(id) ON DELETE CASCADE,
    CONSTRAINT fk_pipeline_policy_snapshot FOREIGN KEY (snapshot_id)
        REFERENCES system_model_execution_snapshot(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TRIGGER pipeline_policy_no_update BEFORE UPDATE ON pipeline_policy_snapshot
FOR EACH ROW SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Pipeline policies are immutable';
