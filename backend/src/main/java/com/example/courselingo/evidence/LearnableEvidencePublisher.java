package com.example.courselingo.evidence;

import com.example.courselingo.task.service.LearnableSourcePublication;
import com.example.courselingo.task.service.LearningAvailability;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.stream.Collectors;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.support.TransactionSynchronization;
import org.springframework.transaction.support.TransactionSynchronizationManager;

/**
 * Keeps study sessions valid while a learnable course completes in the background. When a derived source
 * changes only by addition, the new evidence joins the current revision's snapshot (existing evidence IDs,
 * payloads and the revision are unchanged) and the index re-syncs the same revision. Replacements and
 * deletions still advance the revision exactly as before.
 */
@Service
public class LearnableEvidencePublisher implements LearnableSourcePublication {
    private static final Logger log = LoggerFactory.getLogger(LearnableEvidencePublisher.class);
    private final JdbcTemplate jdbc;
    private final CourseEvidenceService evidence;

    public LearnableEvidencePublisher(JdbcTemplate jdbc, CourseEvidenceService evidence) {
        this.jdbc = jdbc;
        this.evidence = evidence;
    }

    @Override
    public boolean deferIfLearnable(String taskId, Long userId) {
        if (!TransactionSynchronizationManager.isSynchronizationActive()) return false;
        var rows = jdbc.queryForList(
            "SELECT status,learning_ready_at FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL",
            taskId, userId);
        // Only a course that opened learning early while still running has sessions to protect here.
        if (rows.isEmpty() || !"RUNNING".equals(rows.getFirst().get("status"))
                || !LearningAvailability.learnable(rows.getFirst().get("status"), rows.getFirst().get("learning_ready_at"))) {
            return false;
        }
        String key = LearnableEvidencePublisher.class.getName() + ":" + taskId + ":" + userId;
        if (TransactionSynchronizationManager.hasResource(key)) return true;
        TransactionSynchronizationManager.bindResource(key, Boolean.TRUE);
        TransactionSynchronizationManager.registerSynchronization(new TransactionSynchronization() {
            @Override public void beforeCommit(boolean readOnly) { publish(taskId, userId); }
            @Override public void afterCompletion(int status) {
                if (TransactionSynchronizationManager.hasResource(key)) TransactionSynchronizationManager.unbindResource(key);
            }
        });
        return true;
    }

    /** Runs in the writer's transaction after all of its source rows are written. */
    void publish(String taskId, Long userId) {
        long revision = jdbc.queryForObject(
            "SELECT content_revision FROM analysis_task WHERE id=? AND user_id=? FOR UPDATE", Long.class, taskId, userId);
        List<CourseEvidence> fresh = evidence.collect(taskId, userId, revision);
        // Locking reads: see snapshots committed after this transaction's read view was taken.
        boolean snapshot = !jdbc.queryForList(
            "SELECT revision FROM course_evidence_snapshot WHERE task_id=? AND user_id=? AND revision=? FOR UPDATE",
            taskId, userId, revision).isEmpty();
        List<CourseEvidence> stored = jdbc.query(
            "SELECT payload FROM course_evidence WHERE task_id=? AND user_id=? AND revision=? FOR UPDATE",
            (rs, n) -> evidence.decode(rs.getString(1)), taskId, userId, revision);
        Map<String, CourseEvidence> current = new HashMap<>();
        for (var item : fresh) current.put(item.evidenceId(), item);
        // Every evidence item a session may already cite must still exist unchanged.
        if (stored.stream().anyMatch(item -> !item.equals(current.get(item.evidenceId())))) {
            invalidate(taskId, userId);
            log.info("Learnable source change is not additive; revision advanced: taskId={}", taskId);
            return;
        }
        var known = stored.stream().map(CourseEvidence::evidenceId).collect(Collectors.toSet());
        var added = fresh.stream().filter(item -> !known.contains(item.evidenceId())).toList();
        if (snapshot && added.isEmpty()) return;
        for (CourseEvidence item : added) jdbc.update("""
            INSERT INTO course_evidence(evidence_id,task_id,user_id,revision,source_type,source_id,start_ms,end_ms,payload)
            VALUES (?,?,?,?,?,?,?,?,?)
            """, item.evidenceId(), taskId, userId, item.revision(), item.sourceType(), item.sourceId(),
            item.startMs(), item.endMs(), evidence.encode(item));
        String manifest = CourseEvidenceService.hash(fresh.stream().map(CourseEvidence::evidenceId).sorted().collect(Collectors.joining()));
        if (snapshot) {
            jdbc.update("UPDATE course_evidence_snapshot SET manifest_hash=? WHERE task_id=? AND user_id=? AND revision=?",
                manifest, taskId, userId, revision);
        } else {
            jdbc.update("""
                INSERT INTO course_evidence_snapshot(task_id,revision,user_id,manifest_hash,created_at)
                VALUES (?,?,?,?,CURRENT_TIMESTAMP)
                """, taskId, revision, userId, manifest);
        }
        EvidenceChangeLog.append(jdbc, taskId, userId, revision, "UPSERT");
        log.info("Learnable evidence extended in place: taskId={}, revision={}, added={}", taskId, revision, added.size());
    }

    private void invalidate(String taskId, Long userId) {
        jdbc.update("UPDATE analysis_task SET content_revision=content_revision+1 WHERE id=? AND user_id=?", taskId, userId);
        EvidenceChangeLog.append(jdbc, taskId, userId, null, "INVALIDATE");
    }
}
