CREATE TABLE asr_scheduler_state (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    policy_hash CHAR(64) NOT NULL,
    plan_hash CHAR(64) NOT NULL,
    audio_hash CHAR(64) NOT NULL,
    config_identity CHAR(64) NOT NULL,
    execution_epoch BIGINT NOT NULL,
    window_size INT NOT NULL,
    success_streak INT NOT NULL DEFAULT 0,
    in_flight INT NOT NULL DEFAULT 0,
    peak_in_flight INT NOT NULL DEFAULT 0,
    physical_calls INT NOT NULL DEFAULT 0,
    cache_hits INT NOT NULL DEFAULT 0,
    checkpoint_hits INT NOT NULL DEFAULT 0,
    rate_limits INT NOT NULL DEFAULT 0,
    decreases INT NOT NULL DEFAULT 0,
    next_dispatch_at DATETIME(3) NULL,
    cooldown_until DATETIME(3) NULL,
    CONSTRAINT fk_asr_state_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER $$
CREATE TRIGGER asr_state_immutable_input BEFORE UPDATE ON asr_scheduler_state FOR EACH ROW
BEGIN
    IF NOT (OLD.task_id <=> NEW.task_id) OR NOT (OLD.user_id <=> NEW.user_id)
       OR NOT (OLD.policy_hash <=> NEW.policy_hash) OR NOT (OLD.plan_hash <=> NEW.plan_hash)
       OR NOT (OLD.audio_hash <=> NEW.audio_hash) OR NOT (OLD.config_identity <=> NEW.config_identity) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ASR plan identity is immutable';
    END IF;
END$$
DELIMITER ;

CREATE TABLE asr_chunk_checkpoint (
    task_id VARCHAR(64) NOT NULL,
    chunk_no INT NOT NULL,
    start_millis BIGINT NOT NULL,
    end_millis BIGINT NOT NULL,
    sources_json JSON NOT NULL,
    audio_hash CHAR(64) NULL,
    attempt_count INT NOT NULL DEFAULT 0,
    status VARCHAR(32) NOT NULL DEFAULT 'PLANNED',
    result_json JSON NULL,
    result_hash CHAR(64) NULL,
    last_epoch BIGINT NULL,
    PRIMARY KEY(task_id,chunk_no),
    CONSTRAINT fk_asr_chunk_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE asr_scheduler_event (
    id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    execution_epoch BIGINT NOT NULL,
    chunk_no INT NULL,
    attempt_no INT NULL,
    category VARCHAR(64) NOT NULL,
    window_size INT NOT NULL,
    in_flight INT NOT NULL,
    created_at DATETIME(3) NOT NULL DEFAULT CURRENT_TIMESTAMP(3),
    KEY idx_asr_event_task(task_id,id),
    CONSTRAINT fk_asr_event_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE asr_result_cache (
    user_id BIGINT NOT NULL,
    audio_hash CHAR(64) NOT NULL,
    config_identity CHAR(64) NOT NULL,
    source_task_id VARCHAR(64) NOT NULL,
    result_json JSON NOT NULL,
    result_hash CHAR(64) NOT NULL,
    expires_at DATETIME(3) NOT NULL,
    PRIMARY KEY(user_id,audio_hash,config_identity),
    KEY idx_asr_cache_source(source_task_id),
    CONSTRAINT fk_asr_cache_task FOREIGN KEY(source_task_id) REFERENCES analysis_task(id) ON DELETE CASCADE,
    CONSTRAINT fk_asr_cache_user FOREIGN KEY(user_id) REFERENCES user_account(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

DELIMITER $$
CREATE TRIGGER asr_chunk_immutable_input BEFORE UPDATE ON asr_chunk_checkpoint FOR EACH ROW
BEGIN
    IF NOT (OLD.task_id <=> NEW.task_id) OR NOT (OLD.chunk_no <=> NEW.chunk_no)
       OR NOT (OLD.start_millis <=> NEW.start_millis) OR NOT (OLD.end_millis <=> NEW.end_millis)
       OR NOT (OLD.sources_json <=> NEW.sources_json)
       OR (OLD.audio_hash IS NOT NULL AND NOT (OLD.audio_hash <=> NEW.audio_hash))
       OR (OLD.status='SUCCEEDED' AND (NEW.status<>'SUCCEEDED'
           OR NOT (OLD.result_json <=> NEW.result_json) OR NOT (OLD.result_hash <=> NEW.result_hash))) THEN
        SIGNAL SQLSTATE '45000' SET MESSAGE_TEXT = 'ASR source or committed result is immutable';
    END IF;
END$$
DELIMITER ;
