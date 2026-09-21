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
        if ("DELETE".equals(type)) jdbc.update(
            "UPDATE evidence_index_sync SET claim_id=NULL,claim_until=NULL WHERE task_id=?", taskId);
        long sequence = jdbc.queryForObject("SELECT MAX(sequence_id) FROM evidence_change", Long.class);
        int changed = jdbc.update("""
            UPDATE evidence_index_sync SET desired_sequence=?,status='PENDING',attempts=0,
                available_at=CURRENT_TIMESTAMP,last_error=NULL,updated_at=CURRENT_TIMESTAMP WHERE task_id=?
            """, sequence, taskId);
        if (changed == 0) jdbc.update("""
            INSERT INTO evidence_index_sync(task_id,user_id,desired_sequence,available_at,updated_at)
            VALUES (?,?,?,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
            """, taskId, userId, sequence);

    }
}
