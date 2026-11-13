package com.example.courselingo.task.service;

import com.example.courselingo.ai.llm.TranslationFailure;
import com.example.courselingo.common.exception.BusinessException;
import java.sql.Timestamp;
import java.time.Instant;
import java.util.Collections;
import java.util.IdentityHashMap;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;
import java.util.Set;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;

/**
 * Subtitles-ready learning. A course is learnable when it SUCCEEDED, or while it is RUNNING after the
 * current run published its subtitles. Background stages (translation, learning package, download
 * files) then record their own outcome instead of failing the whole course.
 *
 * <p>The switch only controls whether a run opens learning early. The gate predicate is evaluated
 * everywhere unconditionally: with the switch off {@code learning_ready_at} stays NULL and the
 * predicate is exactly the historical {@code status='SUCCEEDED'} rule.
 */
@Service
public class LearningAvailability {
    public static final String TRANSLATION = "TRANSLATION";
    public static final String LEARNING_PACKAGE = "LEARNING_PACKAGE";
    public static final String ARTIFACTS = "ARTIFACTS";
    public static final String SUCCEEDED = "SUCCEEDED";
    public static final String FAILED = "FAILED";

    private static final Set<String> STAGES = Set.of(TRANSLATION, LEARNING_PACKAGE, ARTIFACTS);
    private static final Set<TranslationFailure.Reason> RUN_FATAL = Set.of(
        TranslationFailure.Reason.CANCELED,
        TranslationFailure.Reason.SOURCE_CHANGED,
        TranslationFailure.Reason.SNAPSHOT_INVALID,
        TranslationFailure.Reason.ACCOUNTING_INCOMPLETE,
        TranslationFailure.Reason.DEADLINE_EXCEEDED
    );

    private final JdbcTemplate jdbc;
    private final boolean enabled;

    public LearningAvailability(JdbcTemplate jdbc,
                                @Value("${courselingo.pipeline.early-learning.enabled:false}") boolean enabled) {
        this.jdbc = jdbc;
        this.enabled = enabled;
    }

    /** SQL predicate for a learnable course over the analysis_task alias {@code t}. */
    public static String learnableSql(String alias) {
        return "(" + alias + ".status='SUCCEEDED' OR (" + alias + ".status='RUNNING' AND "
            + alias + ".learning_ready_at IS NOT NULL))";
    }

    public static boolean learnable(Object status, Object learningReadyAt) {
        return "SUCCEEDED".equals(status) || ("RUNNING".equals(status) && learningReadyAt != null);
    }

    public boolean enabled() {
        return enabled;
    }

    /**
     * Opens learning for the current run once its subtitles are stored. Only the active execution can
     * open it, and only when at least one subtitle segment exists. Returns whether the course is open.
     */
    public boolean openAfterSubtitles(String taskId, Long userId) {
        if (!enabled) return false;
        var execution = PipelineExecutionScope.current();
        String fence = execution == null ? "" : """
             AND EXISTS (SELECT 1 FROM task_execution e WHERE e.task_id=t.id AND e.protocol_version=2
                 AND e.execution_epoch=? AND e.event_id=? AND e.completed_at IS NULL AND e.lease_until>=CURRENT_TIMESTAMP)
            """;
        Object[] args = execution == null
            ? new Object[] {now(), taskId, userId}
            : new Object[] {now(), taskId, userId, execution.epoch(), execution.eventId()};
        jdbc.update("""
            UPDATE analysis_task t SET learning_ready_at=?
            WHERE t.id=? AND t.user_id=? AND t.deleted_at IS NULL AND t.status='RUNNING' AND t.learning_ready_at IS NULL
              AND EXISTS (SELECT 1 FROM subtitle_segment s WHERE s.task_id=t.id AND s.user_id=t.user_id)
            """ + fence, args);
        return isOpen(taskId, userId);
    }

    public boolean isOpen(String taskId, Long userId) {
        var rows = jdbc.queryForList(
            "SELECT status,learning_ready_at FROM analysis_task WHERE id=? AND user_id=? AND deleted_at IS NULL",
            taskId, userId);
        return !rows.isEmpty() && learnable(rows.getFirst().get("status"), rows.getFirst().get("learning_ready_at"));
    }

    /**
     * A new run starts with no background outcome; stale results of an earlier run must not show. This
     * runs even with the switch off so outcomes left behind before switching it off cannot linger.
     */
    public void resetStages(String taskId, Long userId) {
        jdbc.update("DELETE FROM task_stage_outcome WHERE task_id=? AND user_id=?", taskId, userId);
    }

    /** Records the outcome of one background stage while this course is still running. */
    public void recordStage(String taskId, Long userId, String stage, String status, String errorCode) {
        if (!STAGES.contains(stage) || !Set.of(SUCCEEDED, FAILED).contains(status)) {
            throw new IllegalArgumentException("unknown background stage outcome");
        }
        String code = errorCode == null ? null : errorCode.length() > 64 ? errorCode.substring(0, 64) : errorCode;
        Timestamp at = now();
        int updated = jdbc.update("""
            UPDATE task_stage_outcome SET status=?,error_code=?,updated_at=? WHERE task_id=? AND user_id=? AND stage=?
            """, status, code, at, taskId, userId, stage);
        if (updated == 0) {
            jdbc.update("""
                INSERT INTO task_stage_outcome(task_id,user_id,stage,status,error_code,updated_at)
                SELECT t.id,t.user_id,?,?,?,? FROM analysis_task t WHERE t.id=? AND t.user_id=? AND t.deleted_at IS NULL
                """, stage, status, code, at, taskId, userId);
        }
    }

    public Map<String, Outcome> outcomes(String taskId, Long userId) {
        var result = new LinkedHashMap<String, Outcome>();
        for (var row : jdbc.queryForList(
                "SELECT stage,status,error_code FROM task_stage_outcome WHERE task_id=? AND user_id=? ORDER BY stage",
                taskId, userId)) {
            result.put((String) row.get("stage"), new Outcome((String) row.get("status"), (String) row.get("error_code")));
        }
        return Map.copyOf(result);
    }

    /**
     * Failures that end the run regardless of stage: cancellation, a lost lease or deadline, a changed
     * source, an invalid policy snapshot, or incomplete cost accounting.
     */
    public static boolean runFatal(Throwable failure) {
        Set<Throwable> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        for (Throwable current = failure; current != null && visited.add(current); current = current.getCause()) {
            if (current instanceof InterruptedException || current instanceof java.util.concurrent.CancellationException) return true;
            if (current instanceof TranslationFailure translation && RUN_FATAL.contains(translation.reason())) return true;
            if (current instanceof BusinessException business && switch (business.errorCode()) {
                case TASK_INVALID_STATUS, TASK_NOT_FOUND -> true;
                default -> false;
            }) return true;
        }
        return false;
    }

    /** Bounded, non-sensitive failure code for a stage outcome. */
    public static String failureCode(Throwable failure) {
        Set<Throwable> visited = Collections.newSetFromMap(new IdentityHashMap<>());
        for (Throwable current = failure; current != null && visited.add(current); current = current.getCause()) {
            if (current instanceof TranslationFailure translation) return "TRANSLATION_" + translation.observationReason();
            if (current instanceof BusinessException business) return business.errorCode().code();
        }
        return failure == null ? "UNKNOWN" : failure.getClass().getSimpleName().toUpperCase(Locale.ROOT);
    }

    private static Timestamp now() {
        return Timestamp.from(Instant.now());
    }

    public record Outcome(String status, String errorCode) { }
}
