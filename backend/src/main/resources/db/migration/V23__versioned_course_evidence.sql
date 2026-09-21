CREATE TABLE course_evidence_snapshot (
    task_id VARCHAR(64) NOT NULL,
    revision BIGINT NOT NULL,
    user_id BIGINT NOT NULL,
    manifest_hash VARCHAR(64) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    PRIMARY KEY(task_id,revision)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

CREATE TABLE course_evidence (
    evidence_id VARCHAR(64) NOT NULL PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    revision BIGINT NOT NULL,
    source_type VARCHAR(32) NOT NULL,
    source_id VARCHAR(64) NOT NULL,
    start_ms BIGINT NOT NULL,
    end_ms BIGINT NOT NULL,
    payload LONGTEXT NOT NULL,
    KEY idx_evidence_page(task_id,user_id,revision,evidence_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;

-- Serializing sequence allocation through this row keeps cursor order equal to commit order.
CREATE TABLE evidence_change_clock (id INT NOT NULL PRIMARY KEY);
INSERT INTO evidence_change_clock(id) VALUES (1);
CREATE TABLE evidence_change (
    sequence_id BIGINT NOT NULL AUTO_INCREMENT PRIMARY KEY,
    task_id VARCHAR(64) NOT NULL,
    user_id BIGINT NOT NULL,
    revision BIGINT NULL,
    change_type VARCHAR(16) NOT NULL,
    created_at DATETIME(3) NOT NULL,
    KEY idx_evidence_change_owner(user_id,sequence_id)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci;
