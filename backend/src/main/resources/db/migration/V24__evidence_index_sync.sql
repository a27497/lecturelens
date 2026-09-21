-- Durable per-course work, coalesced in the same source transaction as evidence_change.
CREATE TABLE evidence_index_sync (
    task_id VARCHAR(64) NOT NULL PRIMARY KEY,
    user_id BIGINT NOT NULL,
    desired_sequence BIGINT NOT NULL,
    synced_sequence BIGINT NOT NULL DEFAULT -1,
    indexed_revision BIGINT NULL,
    index_version VARCHAR(256) NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'PENDING',
    attempts INT NOT NULL DEFAULT 0,
    available_at DATETIME(3) NOT NULL,
    claim_id VARCHAR(64) NULL,
    claim_until DATETIME(3) NULL,
    last_error VARCHAR(64) NULL,
    updated_at DATETIME(3) NOT NULL,
    KEY idx_index_sync_work(available_at,claim_until)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Existing courses are indexed without a first question; deleted courses are also reconciled.
INSERT INTO evidence_index_sync(task_id,user_id,desired_sequence,available_at,updated_at)
SELECT t.id,t.user_id,COALESCE(MAX(c.sequence_id),0),CURRENT_TIMESTAMP,CURRENT_TIMESTAMP
FROM analysis_task t LEFT JOIN evidence_change c ON c.task_id=t.id AND c.user_id=t.user_id
GROUP BY t.id,t.user_id;
