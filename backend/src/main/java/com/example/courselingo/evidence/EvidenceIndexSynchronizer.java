package com.example.courselingo.evidence;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.qa.service.DenseEvidenceClient;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.List;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** Coalesced durable delivery; claims/publication are short transactions, HTTP is outside them. */
@Service
public class EvidenceIndexSynchronizer {
    private static final Logger log = LoggerFactory.getLogger(EvidenceIndexSynchronizer.class);
    private final JdbcTemplate jdbc;
    private final CourseEvidenceService evidence;
    private final DenseEvidenceClient client;
    private final TransactionTemplate transaction;

    public EvidenceIndexSynchronizer(JdbcTemplate jdbc, CourseEvidenceService evidence, DenseEvidenceClient client,
                                      PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.evidence = evidence;
        this.client = client;
        transaction = new TransactionTemplate(manager);
    }

    @Scheduled(fixedDelayString = "${courselingo.retrieval.sync-poll-millis:3000}")
    public void synchronize() { dispatch(false); }

    // Independent scheduler lane: deletion is not queued behind slow document embedding.
    @Scheduled(fixedDelayString = "${courselingo.retrieval.sync-poll-millis:3000}")
    public void synchronizeDeletes() { dispatch(true); }

    private void dispatch(boolean deleted) {
        if (!client.enabled()) return;
        for (int i = 0; i < 5; i++) {
            Work work = claim(deleted);
            if (work == null) return;
            deliver(work);
        }
    }

    private Work claim(boolean deleted) {
        return transaction.execute(status -> {
            var rows = jdbc.queryForList("""
                SELECT s.task_id,s.user_id,s.desired_sequence,t.content_revision,s.attempts
                FROM evidence_index_sync s JOIN analysis_task t ON t.id=s.task_id AND t.user_id=s.user_id
                WHERE s.available_at<=CURRENT_TIMESTAMP AND (s.claim_until IS NULL OR s.claim_until<CURRENT_TIMESTAMP)
                """ + (deleted ? " AND t.deleted_at IS NOT NULL " : " AND t.deleted_at IS NULL AND t.status='SUCCEEDED' ") + """
                ORDER BY s.available_at,s.task_id LIMIT 1 FOR UPDATE
                """);
            if (rows.isEmpty()) return null;
            var row = rows.getFirst();
            String task = row.get("task_id").toString();
            String claim = UUID.randomUUID().toString();
            jdbc.update("""
                UPDATE evidence_index_sync SET claim_id=?,claim_until=?,status='INDEXING',updated_at=CURRENT_TIMESTAMP
                WHERE task_id=?
                """, claim, Timestamp.from(Instant.now().plusSeconds(660)), task);
            return new Work(task, ((Number) row.get("user_id")).longValue(),
                ((Number) row.get("desired_sequence")).longValue(), ((Number) row.get("content_revision")).longValue(),
                ((Number) row.get("attempts")).intValue(), claim, deleted);
        });
    }

    private void deliver(Work work) {
        try {
            List<CourseEvidence> items = work.deleted() ? List.of() : evidence.current(work.taskId(), work.ownerId())
                .stream().filter(CourseEvidence::retrievable).toList();
            // ensureSnapshot can append UPSERT; release this claim and consume its committed sequence next poll.
            if (!jdbc.queryForObject("SELECT desired_sequence FROM evidence_index_sync WHERE task_id=?", Long.class,
                    work.taskId()).equals(work.sequence())) {
                release(work);
                return;
            }
            if (items.stream().anyMatch(item -> item.revision() != work.revision())) {
                release(work);
                return;
            }
            var result = client.sync(work.taskId(), work.ownerId(), work.revision(), work.sequence(), items, work.deleted());
            int changed = jdbc.update("""
                UPDATE evidence_index_sync SET synced_sequence=?,indexed_revision=?,index_version=?,status=?,attempts=0,
                    available_at=?,claim_id=NULL,claim_until=NULL,last_error=NULL,updated_at=CURRENT_TIMESTAMP
                WHERE task_id=? AND claim_id=? AND desired_sequence=?
                """, work.sequence(), work.revision(), result.path("index_version").asText(),
                work.deleted() ? "DELETED" : "READY", Timestamp.from(Instant.now().plusSeconds(300)),
                work.taskId(), work.claimId(), work.sequence());
            if (changed == 0) release(work);
        } catch (Exception failure) {
            if (failure instanceof InterruptedException) Thread.currentThread().interrupt();
            int changed = jdbc.update("""
                UPDATE evidence_index_sync SET status='FAILED',attempts=attempts+1,available_at=?,
                    claim_id=NULL,claim_until=NULL,last_error=?,updated_at=CURRENT_TIMESTAMP
                WHERE task_id=? AND claim_id=? AND desired_sequence=?
                """, Timestamp.from(Instant.now().plusSeconds(Math.min(300, 3L << Math.min(work.attempts(), 6)))),
                failure.getClass().getSimpleName(), work.taskId(), work.claimId(), work.sequence());
            if (changed == 0) release(work);
            log.warn("Evidence sync failed: taskId={}, sequence={}, type={}", work.taskId(), work.sequence(), failure.getClass().getSimpleName());
        }
    }

    private void release(Work work) {
        jdbc.update("""
            UPDATE evidence_index_sync SET claim_id=NULL,claim_until=NULL,status='PENDING',available_at=CURRENT_TIMESTAMP
            WHERE task_id=? AND claim_id=?
            """, work.taskId(), work.claimId());
    }

    public IndexStatus status(String taskId, Long ownerId) {
        var rows = jdbc.queryForList("""
            SELECT t.content_revision,s.status,s.desired_sequence,s.synced_sequence,s.indexed_revision,s.index_version,
                s.attempts,s.last_error,s.updated_at
            FROM analysis_task t LEFT JOIN evidence_index_sync s ON t.id=s.task_id AND t.user_id=s.user_id
            WHERE t.id=? AND t.user_id=? AND t.deleted_at IS NULL
            """, taskId, ownerId);
        if (rows.isEmpty()) throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        var row = rows.getFirst();
        String state = !client.enabled() ? "DISABLED" : row.get("status") == null ? "PENDING" : row.get("status").toString();
        long revision = ((Number) row.get("content_revision")).longValue();
        Long indexed = row.get("indexed_revision") instanceof Number n ? n.longValue() : null;
        if ("READY".equals(state) && (!Long.valueOf(revision).equals(indexed)
                || !row.get("desired_sequence").equals(row.get("synced_sequence")))) state = "PENDING";
        return new IndexStatus(state, revision, indexed, (String) row.get("index_version"),
            row.get("attempts") instanceof Number n ? n.intValue() : 0, (String) row.get("last_error"),
            row.get("updated_at") == null ? null : row.get("updated_at").toString());
    }

    public record IndexStatus(String status, long revision, Long indexedRevision, String indexVersion,
                              int attempts, String lastError, String updatedAt) { }
    private record Work(String taskId, Long ownerId, long sequence, long revision, int attempts, String claimId, boolean deleted) { }
}
