ALTER TABLE task_execution
    ADD COLUMN protocol_version INT NOT NULL DEFAULT 1,
    ADD COLUMN execution_epoch BIGINT NOT NULL DEFAULT 0,
    ADD COLUMN resume_count INT NOT NULL DEFAULT 0;

ALTER TABLE task_outbox
    ADD COLUMN protocol_version INT NOT NULL DEFAULT 1,
    ADD COLUMN execution_epoch BIGINT NULL,
    ADD UNIQUE KEY uk_task_outbox_execution(task_id,event_type,execution_epoch);

ALTER TABLE translation_scheduler_state ADD COLUMN execution_epoch BIGINT NOT NULL DEFAULT 0;
ALTER TABLE translation_scheduler_event ADD COLUMN execution_epoch BIGINT NOT NULL DEFAULT 0;

CREATE TABLE translation_plan (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    snapshot_id VARCHAR(64) NOT NULL,
    config_version BIGINT NOT NULL,
    policy_hash CHAR(64) NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    target_language VARCHAR(32) NOT NULL,
    root_plan_hash CHAR(64) NOT NULL,
    next_batch_no INT NOT NULL,
    physical_calls INT NOT NULL DEFAULT 0,
    accounted_tokens BIGINT NOT NULL DEFAULT 0,
    translation_started_at DATETIME(3) NOT NULL,
    translation_deadline DATETIME(3) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'RUNNING',
    CONSTRAINT fk_translation_plan_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE translation_batch (
    task_id VARCHAR(64) NOT NULL,
    batch_no INT NOT NULL,
    config_version BIGINT NOT NULL,
    parent_batch_no INT NULL,
    child_ordinal INT NULL,
    depth INT NOT NULL,
    source_json JSON NOT NULL,
    source_hash CHAR(64) NOT NULL,
    request_hash CHAR(64) NOT NULL,
    status VARCHAR(32) NOT NULL DEFAULT 'PLANNED',
    result_json JSON NULL,
    result_hash CHAR(64) NULL,
    claim_epoch BIGINT NULL,
    claim_token VARCHAR(64) NULL,
    claim_until DATETIME(3) NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    last_error_category VARCHAR(64) NULL,
    PRIMARY KEY(task_id,batch_no,config_version),
    UNIQUE KEY uk_translation_child(task_id,parent_batch_no,child_ordinal,config_version),
    KEY idx_translation_batch_claim(status,claim_until),
    CONSTRAINT fk_translation_batch_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE,
    CONSTRAINT fk_translation_batch_parent FOREIGN KEY(task_id,parent_batch_no,config_version)
        REFERENCES translation_batch(task_id,batch_no,config_version) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE translation_attempt (
    id VARCHAR(64) NOT NULL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    batch_no INT NOT NULL,
    config_version BIGINT NOT NULL,
    attempt_no INT NOT NULL,
    execution_epoch BIGINT NOT NULL,
    status VARCHAR(32) NOT NULL,
    output_limit INT NOT NULL,
    estimated_input_tokens INT NOT NULL,
    reserved_tokens BIGINT NOT NULL,
    accounted_tokens BIGINT NOT NULL,
    prompt_tokens INT NULL,
    completion_tokens INT NULL,
    total_tokens INT NULL,
    finish_reason VARCHAR(64) NULL,
    error_category VARCHAR(64) NULL,
    duration_millis BIGINT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    completed_at DATETIME(3) NULL,
    UNIQUE KEY uk_translation_attempt(task_id,batch_no,config_version,attempt_no),
    CONSTRAINT fk_translation_attempt_batch FOREIGN KEY(task_id,batch_no,config_version)
        REFERENCES translation_batch(task_id,batch_no,config_version) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE pipeline_step_checkpoint (
    task_id VARCHAR(64) NOT NULL,
    step_name VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    source_fingerprint CHAR(64) NOT NULL,
    result_hash CHAR(64) NOT NULL,
    payload_json JSON NOT NULL,
    execution_epoch BIGINT NOT NULL,
    completed_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    PRIMARY KEY(task_id,step_name),
    CONSTRAINT fk_pipeline_step_checkpoint_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER $$
CREATE TRIGGER translation_plan_immutable_input BEFORE UPDATE ON translation_plan FOR EACH ROW
BEGIN
    IF NOT (OLD.task_id <=> NEW.task_id) OR NOT (OLD.user_id <=> NEW.user_id)
       OR NOT (OLD.snapshot_id <=> NEW.snapshot_id) OR NOT (OLD.config_version <=> NEW.config_version)
       OR NOT (OLD.policy_hash <=> NEW.policy_hash) OR NOT (OLD.source_fingerprint <=> NEW.source_fingerprint)
       OR NOT (OLD.target_language <=> NEW.target_language) OR NOT (OLD.root_plan_hash <=> NEW.root_plan_hash)
       OR NOT (OLD.translation_started_at <=> NEW.translation_started_at) OR NOT (OLD.translation_deadline <=> NEW.translation_deadline) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Translation plan input is immutable';
    END IF;
END$$
CREATE TRIGGER translation_batch_immutable_input BEFORE UPDATE ON translation_batch FOR EACH ROW
BEGIN
    IF NOT (OLD.task_id <=> NEW.task_id) OR NOT (OLD.batch_no <=> NEW.batch_no)
       OR NOT (OLD.config_version <=> NEW.config_version) OR NOT (OLD.parent_batch_no <=> NEW.parent_batch_no)
       OR NOT (OLD.child_ordinal <=> NEW.child_ordinal) OR NOT (OLD.depth <=> NEW.depth)
       OR NOT (OLD.source_json <=> NEW.source_json) OR NOT (OLD.source_hash <=> NEW.source_hash)
       OR NOT (OLD.request_hash <=> NEW.request_hash)
       OR (OLD.status = 'SUCCEEDED' AND (NEW.status <> 'SUCCEEDED'
           OR NOT (OLD.result_json <=> NEW.result_json) OR NOT (OLD.result_hash <=> NEW.result_hash))) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'Translation batch input or committed result is immutable';
    END IF;
END$$
DELIMITER ;
