package com.example.courselingo.task.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.List;
import java.util.UUID;
import java.util.function.Supplier;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.TransactionDefinition;
import org.springframework.transaction.support.TransactionTemplate;

/** Short transactions serialize publication with deletion and source replacement, never with model I/O. */
@Service
public class GenerationFence {
    private final JdbcTemplate jdbc;
    private final TransactionTemplate transaction;

    public GenerationFence(JdbcTemplate jdbc, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        transaction = new TransactionTemplate(manager);
        transaction.setPropagationBehavior(TransactionDefinition.PROPAGATION_REQUIRES_NEW);
    }

    public Ticket begin(String taskId, Long userId, String scope) {
        return transaction.execute(status -> {
            long revision = lockActive(taskId, userId);
            String generation = UUID.randomUUID().toString();
            // Append-only QA needs source fencing, but must not invalidate another user's concurrent question.
            if (scope != null) {
                int updated = jdbc.update("UPDATE task_generation SET generation_id=? WHERE task_id=? AND scope=?",
                    generation, taskId, scope);
                if (updated == 0) jdbc.update("INSERT INTO task_generation(task_id,scope,generation_id) VALUES (?,?,?)",
                    taskId, scope, generation);
            }
            return new Ticket(taskId, userId, revision, scope, generation);
        });
    }

    public <T> T commit(Ticket ticket, Supplier<T> persist) {
        return transaction.execute(status -> {
            if (lockActive(ticket.taskId(), ticket.userId()) != ticket.revision()) throw stale();
            if (ticket.scope() != null) {
                String current = jdbc.queryForObject(
                    "SELECT generation_id FROM task_generation WHERE task_id=? AND scope=?", String.class,
                    ticket.taskId(), ticket.scope());
                if (!ticket.generation().equals(current)) throw stale();
            }
            return persist.get();
        });
    }

    public <T> T recordFailure(Ticket ticket, Supplier<T> persist) {
        return transaction.execute(status -> {
            List<Long> owners = jdbc.queryForList(
                "SELECT user_id FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",
                Long.class, ticket.taskId(), ticket.userId());
            if (owners.isEmpty()) return null; // Do not recreate content after deletion.
            return persist.get();
        });
    }

    /** Called inside a source writer's transaction, before replacing source rows. */
    public void sourceChanging(String taskId, Long userId) {
        if (!org.springframework.transaction.support.TransactionSynchronizationManager.isActualTransactionActive()) {
            throw new IllegalStateException("Source replacement requires a transaction");
        }
        lockActive(taskId, userId);
        jdbc.update("UPDATE analysis_task SET content_revision=content_revision+1 WHERE id=? AND user_id=?", taskId, userId);
        com.example.courselingo.evidence.EvidenceChangeLog.append(jdbc, taskId, userId, null, "INVALIDATE");
    }

    private long lockActive(String taskId, Long userId) {
        var rows = jdbc.queryForList(
            "SELECT content_revision,status FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL FOR UPDATE",
            taskId, userId);
        if (rows.isEmpty()) throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        var task = rows.getFirst();
        if (List.of("FAILED", "CANCELED").contains(task.get("status"))) throw stale();
        if ("RUNNING".equals(task.get("status")) && !jdbc.queryForList(
            "SELECT task_id FROM task_execution WHERE task_id=? AND (lease_until<CURRENT_TIMESTAMP OR completed_at IS NOT NULL)",
            taskId).isEmpty()) throw stale();
        return ((Number) task.get("content_revision")).longValue();
    }

    private static BusinessException stale() {
        return new BusinessException(ErrorCode.TASK_INVALID_STATUS, "Task or source changed while generating; retry the operation");
    }

    public record Ticket(String taskId, Long userId, long revision, String scope, String generation) { }
}
