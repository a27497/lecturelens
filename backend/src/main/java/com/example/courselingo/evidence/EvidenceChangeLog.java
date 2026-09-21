package com.example.courselingo.evidence;

import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.transaction.support.TransactionSynchronizationManager;

public final class EvidenceChangeLog {
    private EvidenceChangeLog() { }

    public static void append(JdbcTemplate jdbc, String taskId, Long userId, Long revision, String type) {
        if (!TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("Evidence change requires the source transaction");
        }
        jdbc.queryForObject("SELECT id FROM evidence_change_clock WHERE id=1 FOR UPDATE", Integer.class);
        jdbc.update("""
            INSERT INTO evidence_change(task_id,user_id,revision,change_type,created_at) VALUES (?,?,?,?,CURRENT_TIMESTAMP)
            """, taskId, userId, revision, type);
    }
}
