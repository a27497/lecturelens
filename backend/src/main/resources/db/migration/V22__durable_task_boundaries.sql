ALTER TABLE analysis_task ADD COLUMN content_revision BIGINT NOT NULL DEFAULT 0;

CREATE TABLE task_generation (
    task_id VARCHAR(64) NOT NULL,
    scope VARCHAR(128) NOT NULL,
    generation_id VARCHAR(64) NOT NULL,
    PRIMARY KEY (task_id, scope),
    CONSTRAINT fk_generation_task FOREIGN KEY (task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE task_outbox (
    event_id VARCHAR(64) NOT NULL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    event_type VARCHAR(64) NOT NULL,
    payload LONGTEXT NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INT NOT NULL DEFAULT 0,
    available_at DATETIME(3) NOT NULL,
    claim_id VARCHAR(64) NULL,
    claim_until DATETIME(3) NULL,
    last_error VARCHAR(128) NULL,
    created_at DATETIME(3) NOT NULL,
    completed_at DATETIME(3) NULL,
    KEY idx_outbox_pending (status, available_at),
    KEY idx_outbox_task (task_id, event_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE task_execution (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    event_id VARCHAR(64) NOT NULL,
    lease_until DATETIME(3) NOT NULL,
    completed_at DATETIME(3) NULL,
    CONSTRAINT fk_execution_task FOREIGN KEY (task_id) REFERENCES analysis_task(id) ON DELETE CASCADE
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Upgrade requires stopping old workers. Never replay an old worker's mutable workspace.
UPDATE analysis_task SET status='FAILED', error_code='TASK_UPGRADE_INTERRUPTED',
    error_message='Interrupted by durable-task upgrade; create a retry task',
    content_revision=content_revision+1, finished_at=CURRENT_TIMESTAMP
WHERE status IN ('CREATED','QUEUED','RUNNING','RETRYING') AND deleted_at IS NULL;
