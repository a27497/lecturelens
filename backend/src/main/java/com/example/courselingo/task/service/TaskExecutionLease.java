package com.example.courselingo.task.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.mq.AnalysisTaskMessage;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.support.TransactionTemplate;

/** A crashed task becomes explicitly FAILED. Retries use new task IDs, never reuse an old worker's workspace. */
@Service
public class TaskExecutionLease {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;
    private final ConcurrentHashMap<String, String> active = new ConcurrentHashMap<>();

    public TaskExecutionLease(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        transaction = new TransactionTemplate(manager);
    }

    public void open(AnalysisTaskMessage message) {
        transaction.executeWithoutResult(status -> {
            var rows = jdbc.queryForList("""
                SELECT status FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE
                """, message.taskId(), message.userId());
            if (rows.isEmpty() || !"QUEUED".equals(rows.getFirst().get("status"))) throw rejected();
            if (!jdbc.queryForList("SELECT task_id FROM task_execution WHERE task_id=?", message.taskId()).isEmpty()) {
                throw rejected();
            }
            jdbc.update("INSERT INTO task_execution(task_id,event_id,lease_until) VALUES (?,?,?)",
                message.taskId(), message.requestId(), Timestamp.from(Instant.now().plusSeconds(90)));
        });
        active.put(message.taskId(), message.requestId());
    }

    /** Serialize final success with recovery and logical deletion, and reject expired workers immediately. */
    public void publishSuccess(AnalysisTaskMessage message, Runnable publish) {
        transaction.executeWithoutResult(status -> {
            if (jdbc.queryForList("SELECT id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",
                message.taskId(), message.userId()).isEmpty()) throw rejected();
            if (jdbc.queryForList("""
                SELECT task_id FROM task_execution WHERE task_id=? AND event_id=? AND completed_at IS NULL
                AND lease_until>=CURRENT_TIMESTAMP FOR UPDATE
                """, message.taskId(), message.requestId()).isEmpty()) throw rejected();
            publish.run();
        });
    }

    public void close(AnalysisTaskMessage message) {
        active.remove(message.taskId(), message.requestId());
        jdbc.update("""
            UPDATE task_execution SET lease_until=CURRENT_TIMESTAMP,
            completed_at=CASE WHEN EXISTS(SELECT 1 FROM analysis_task WHERE id=? AND status IN ('SUCCEEDED','FAILED','CANCELED'))
            THEN CURRENT_TIMESTAMP ELSE NULL END WHERE task_id=? AND event_id=?
            """, message.taskId(),
            message.taskId(), message.requestId());
    }

    @Scheduled(fixedDelayString = "${courselingo.task.lease.heartbeat-millis:15000}")
    public void heartbeat() {
        active.forEach((taskId, eventId) -> jdbc.update("""
            UPDATE task_execution SET lease_until=? WHERE task_id=? AND event_id=?
            AND completed_at IS NULL AND lease_until>=CURRENT_TIMESTAMP
            """, Timestamp.from(Instant.now().plusSeconds(90)), taskId, eventId));
    }

    @Scheduled(fixedDelayString = "${courselingo.task.lease.recovery-millis:30000}")
    public void recoverExpired() {
        transaction.executeWithoutResult(status -> {
            var rows = jdbc.queryForList("""
                SELECT t.id FROM analysis_task t JOIN task_execution e ON t.id=e.task_id
                WHERE e.lease_until<CURRENT_TIMESTAMP AND e.completed_at IS NULL
                  AND t.status IN ('QUEUED','RUNNING') AND t.deleted_at IS NULL
                ORDER BY t.id LIMIT 100 FOR UPDATE SKIP LOCKED
                """);
            for (var row : rows) {
                String taskId = (String) row.get("id");
                jdbc.update("""
                    UPDATE analysis_task SET status='FAILED',content_revision=content_revision+1,
                    error_code='TASK_EXECUTION_INTERRUPTED',error_message='Worker lease expired; create a retry task',
                    finished_at=CURRENT_TIMESTAMP WHERE id=?
                    """, taskId);
                jdbc.update("UPDATE task_execution SET completed_at=CURRENT_TIMESTAMP WHERE task_id=?", taskId);
            }
        });
    }

    private static BusinessException rejected() { return new BusinessException(ErrorCode.TASK_INVALID_STATUS); }
}
