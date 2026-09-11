package com.example.courselingo.task.service;

import com.example.courselingo.mq.*;
import com.example.courselingo.vision.keyframe.VideoKeyframeEvidenceLifecycleService;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.UUID;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.scheduling.annotation.Scheduled;
import org.springframework.stereotype.Service;
import org.springframework.transaction.PlatformTransactionManager;
import org.springframework.transaction.annotation.Propagation;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.transaction.support.TransactionTemplate;

/** Database intent is committed with business state; network delivery happens after commit. */
@Service
@Primary
public class DurableTaskOutbox implements AnalysisTaskMessageProducer {
    private static final Logger log = LoggerFactory.getLogger(DurableTaskOutbox.class);
    private final JdbcTemplate jdbc;
    private final ObjectMapper json;
    private final RocketMqAnalysisTaskMessageProducer transport;
    private final VideoKeyframeEvidenceLifecycleService cleanup;
    private final TransactionTemplate transaction;

    public DurableTaskOutbox(JdbcTemplate jdbc, ObjectMapper json, RocketMqAnalysisTaskMessageProducer transport,
                             VideoKeyframeEvidenceLifecycleService cleanup, PlatformTransactionManager manager) {
        this.jdbc = jdbc;
        this.json = json;
        this.transport = transport;
        this.cleanup = cleanup;
        transaction = new TransactionTemplate(manager);
    }

    @Override
    @Transactional(propagation = Propagation.MANDATORY)
    public void send(AnalysisTaskMessageTag tag, AnalysisTaskMessage message) {
        message.validate();
        String eventId = UUID.randomUUID().toString();
        var event = new AnalysisTaskMessage(message.taskId(), message.uploadId(), message.userId(),
            message.sourceLanguage(), message.targetLanguage(), eventId, message.traceId(), message.createdAt());
        try {
            insert(eventId, message.taskId(), message.userId(), tag.name(), json.writeValueAsString(event));
        } catch (com.fasterxml.jackson.core.JsonProcessingException exception) {
            throw new IllegalStateException("Cannot serialize task event", exception);
        }
    }

    @Transactional(propagation = Propagation.MANDATORY)
    public void enqueueCleanup(String taskId, Long userId) {
        com.example.courselingo.evidence.EvidenceChangeLog.append(jdbc, taskId, userId, null, "DELETE");
        insert(UUID.randomUUID().toString(), taskId, userId, "CLEANUP_EVIDENCE", "{}");
    }

    private void insert(String id, String taskId, Long userId, String type, String payload) {
        jdbc.update("""
            INSERT INTO task_outbox(event_id,task_id,user_id,event_type,payload,status,attempts,available_at,created_at)
            VALUES (?,?,?,?,?,'PENDING',0,CURRENT_TIMESTAMP,CURRENT_TIMESTAMP)
            """, id, taskId, userId, type, payload);
    }

    @Scheduled(fixedDelayString = "${courselingo.task.outbox.poll-millis:1000}")
    public void dispatch() {
        for (int i = 0; i < 20; i++) {
            Event event = claim();
            if (event == null) return;
            try {
                if (event.type().equals("CLEANUP_EVIDENCE")) {
                    // Logical deletion has already committed. The object keys remain until cleanup succeeds.
                    cleanup.cleanupTaskEvidence(event.taskId(), event.userId());
                    transaction.executeWithoutResult(status -> {
                        jdbc.update("DELETE FROM course_evidence WHERE task_id=? AND user_id=?", event.taskId(), event.userId());
                        jdbc.update("DELETE FROM course_evidence_snapshot WHERE task_id=? AND user_id=?", event.taskId(), event.userId());
                    });
                } else {
                    transport.send(AnalysisTaskMessageTag.valueOf(event.type()),
                        json.readValue(event.payload(), AnalysisTaskMessage.class));
                }
                jdbc.update("""
                    UPDATE task_outbox SET status='SENT',completed_at=CURRENT_TIMESTAMP,claim_until=NULL,last_error=NULL
                    WHERE event_id=? AND claim_id=? AND status='DELIVERING'
                    """, event.id(), event.claimId());
            } catch (Exception exception) {
                fail(event, exception);
            }
        }
    }

    private Event claim() {
        return transaction.execute(status -> {
            var rows = jdbc.queryForList("""
                SELECT * FROM task_outbox
                WHERE (status='PENDING' AND available_at<=CURRENT_TIMESTAMP)
                   OR (status='DELIVERING' AND claim_until<CURRENT_TIMESTAMP)
                ORDER BY created_at,event_id LIMIT 1 FOR UPDATE SKIP LOCKED
                """);
            if (rows.isEmpty()) return null;
            var row = rows.getFirst();
            String id = (String) row.get("event_id");
            String claimId = UUID.randomUUID().toString();
            int attempts = ((Number) row.get("attempts")).intValue() + 1;
            jdbc.update("""
                UPDATE task_outbox SET status='DELIVERING',claim_id=?,claim_until=?,attempts=? WHERE event_id=?
                """, claimId, Timestamp.from(Instant.now().plusSeconds(300)), attempts, id);
            return new Event(id, (String) row.get("task_id"), ((Number) row.get("user_id")).longValue(),
                (String) row.get("event_type"), (String) row.get("payload"), attempts, claimId);
        });
    }

    private void fail(Event event, Exception exception) {
        boolean exhausted = !event.type().equals("CLEANUP_EVIDENCE") && event.attempts() >= 8;
        transaction.executeWithoutResult(status -> {
            int updated = jdbc.update("""
                UPDATE task_outbox SET status=?,available_at=?,claim_until=NULL,last_error=?
                WHERE event_id=? AND claim_id=? AND status='DELIVERING'
                """, exhausted ? "DEAD" : "PENDING",
                Timestamp.from(Instant.now().plusSeconds(Math.min(300, 1L << Math.min(event.attempts(), 8)))),
                exception.getClass().getSimpleName(), event.id(), event.claimId());
            if (updated == 1 && exhausted && event.type().equals("ANALYSIS_CREATED")) {
                jdbc.update("""
                    UPDATE analysis_task SET status='FAILED',error_code='MQ_DELIVERY_EXHAUSTED',
                    error_message='Task delivery failed; create a retry task',finished_at=CURRENT_TIMESTAMP
                    WHERE id=? AND user_id=? AND status='QUEUED' AND deleted_at IS NULL
                    """, event.taskId(), event.userId());
            }
        });
        log.warn("event=outbox_delivery_failed eventId={} taskId={} attempt={} exhausted={} errorType={}",
            event.id(), event.taskId(), event.attempts(), exhausted, exception.getClass().getSimpleName());
    }

    private record Event(String id, String taskId, Long userId, String type, String payload, int attempts, String claimId) { }
}
