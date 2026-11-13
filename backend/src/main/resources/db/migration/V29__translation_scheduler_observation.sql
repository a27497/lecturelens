CREATE TABLE translation_scheduler_state (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    config_version BIGINT NOT NULL,
    policy_hash CHAR(64) NOT NULL,
    window_epoch BIGINT NOT NULL,
    window_size INT NOT NULL,
    success_streak INT NOT NULL,
    cooldown_until_millis BIGINT NOT NULL,
    last_event_seq BIGINT NOT NULL,
    revision BIGINT NOT NULL,
    CONSTRAINT fk_translation_scheduler_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE translation_scheduler_event (
    task_id VARCHAR(64) NOT NULL,
    event_seq BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    config_version BIGINT NOT NULL,
    policy_hash CHAR(64) NOT NULL,
    event_time DATETIME(3) NOT NULL,
    old_window INT NOT NULL,
    new_window INT NOT NULL,
    inflight INT NOT NULL,
    window_epoch BIGINT NOT NULL,
    success_streak INT NOT NULL,
    reason VARCHAR(64) NOT NULL,
    batch_no INT NOT NULL,
    attempt_no INT NOT NULL,
    cooldown_until_millis BIGINT NOT NULL,
    PRIMARY KEY(task_id,event_seq),
    CONSTRAINT fk_translation_scheduler_event_task FOREIGN KEY(task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
