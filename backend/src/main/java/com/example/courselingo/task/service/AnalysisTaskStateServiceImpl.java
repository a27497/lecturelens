package com.example.courselingo.task.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.task.dto.AnalysisTaskStateChangeCommand;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

@Service
public class AnalysisTaskStateServiceImpl implements AnalysisTaskStateService {

    private static final Logger log = LoggerFactory.getLogger(AnalysisTaskStateServiceImpl.class);
    private static final int ERROR_MESSAGE_LIMIT = 1024;
    private static final int LOG_MESSAGE_LIMIT = 1024;
    private static final Pattern SENSITIVE_WORDS = Pattern.compile(
        "(?i)access\\s*token|refresh\\s*token|api\\s*key|secret\\s*key|token|secret"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S*");
    private static final Pattern UNIX_HOME_PATH = Pattern.compile("/(?:home|Users)/\\S*");

    private final AnalysisTaskMapper analysisTaskMapper;
    private final TaskLogMapper taskLogMapper;
    private final AnalysisTaskStateMachine stateMachine;
    private final Clock clock;
    private final TaskProgressSnapshotService progressSnapshotService;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public AnalysisTaskStateServiceImpl(
        AnalysisTaskMapper analysisTaskMapper,
        TaskLogMapper taskLogMapper,
        AnalysisTaskStateMachine stateMachine,
        TaskProgressSnapshotService progressSnapshotService,
        BusinessMetrics businessMetrics
    ) {
        this(
            analysisTaskMapper,
            taskLogMapper,
            stateMachine,
            Clock.systemDefaultZone(),
            progressSnapshotService,
            businessMetrics
        );
    }

    public AnalysisTaskStateServiceImpl(
        AnalysisTaskMapper analysisTaskMapper,
        TaskLogMapper taskLogMapper,
        AnalysisTaskStateMachine stateMachine,
        Clock clock,
        TaskProgressSnapshotService progressSnapshotService
    ) {
        this(
            analysisTaskMapper,
            taskLogMapper,
            stateMachine,
            clock,
            progressSnapshotService,
            BusinessMetrics.noop()
        );
    }

    public AnalysisTaskStateServiceImpl(
        AnalysisTaskMapper analysisTaskMapper,
        TaskLogMapper taskLogMapper,
        AnalysisTaskStateMachine stateMachine,
        Clock clock,
        TaskProgressSnapshotService progressSnapshotService,
        BusinessMetrics businessMetrics
    ) {
        this.analysisTaskMapper = analysisTaskMapper;
        this.taskLogMapper = taskLogMapper;
        this.stateMachine = stateMachine;
        this.clock = clock;
        this.progressSnapshotService = progressSnapshotService;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    @Override
    @Transactional
    public void changeState(AnalysisTaskStateChangeCommand command) {
        validateCommand(command);

        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(command.getTaskId(), command.getUserId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }

        AnalysisTaskStatus currentStatus = AnalysisTaskStatus.fromDatabaseValue(task.getStatus());
        AnalysisTaskStatus targetStatus = command.getTargetStatus();
        stateMachine.assertTransition(currentStatus, targetStatus);

        LocalDateTime now = now();
        Integer progress = normalizeProgress(targetStatus, command.getProgressPercent(), task.getProgressPercent());
        String sanitizedErrorMessage = sanitizeAndLimit(command.getErrorMessage(), ERROR_MESSAGE_LIMIT);

        task.setStatus(targetStatus.name());
        task.setProgressPercent(progress);
        task.setCurrentStage(command.getStage() == null ? null : command.getStage().name());
        task.setErrorCode(limit(command.getErrorCode(), 64));
        task.setErrorMessage(sanitizedErrorMessage);
        if (targetStatus == AnalysisTaskStatus.RUNNING && task.getStartedAt() == null) {
            task.setStartedAt(now);
        }
        if (isTerminal(targetStatus)) {
            task.setFinishedAt(now);
        }

        int updated = analysisTaskMapper.updateStateByIdAndUserId(task);
        if (updated != 1) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }

        taskLogMapper.insert(buildTaskLog(command, currentStatus, targetStatus, sanitizedErrorMessage, now));
        log.info(
            "event=task_state_changed taskId={} fromStatus={} toStatus={} stage={} outcome=success",
            SafeLogSanitizer.sanitize(command.getTaskId()),
            currentStatus.name(),
            targetStatus.name(),
            command.getStage() == null ? "" : command.getStage().name()
        );
        businessMetrics.incrementTaskStateTransition(currentStatus.name(), targetStatus.name(), "success");
        refreshProgressSnapshot(task, now);
    }

    private void validateCommand(AnalysisTaskStateChangeCommand command) {
        if (command == null
            || command.getTaskId() == null
            || command.getTaskId().isBlank()
            || command.getUserId() == null
            || command.getTargetStatus() == null) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        Integer progress = command.getProgressPercent();
        if (progress != null && (progress < 0 || progress > 100)) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        if (command.getTargetStatus() == AnalysisTaskStatus.SUCCEEDED
            && progress != null
            && progress != 100) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
    }

    private Integer normalizeProgress(
        AnalysisTaskStatus targetStatus,
        Integer requestedProgress,
        Integer currentProgress
    ) {
        if (targetStatus == AnalysisTaskStatus.SUCCEEDED) {
            return 100;
        }
        return requestedProgress == null ? currentProgress : requestedProgress;
    }

    private TaskLog buildTaskLog(
        AnalysisTaskStateChangeCommand command,
        AnalysisTaskStatus currentStatus,
        AnalysisTaskStatus targetStatus,
        String sanitizedErrorMessage,
        LocalDateTime now
    ) {
        TaskLog log = new TaskLog();
        log.setTaskId(command.getTaskId());
        log.setUserId(command.getUserId());
        log.setLevel(targetStatus == AnalysisTaskStatus.FAILED ? "ERROR" : "INFO");
        log.setStage(command.getStage() == null ? null : command.getStage().name());
        String message = currentStatus.name() + " -> " + targetStatus.name();
        if (sanitizedErrorMessage != null && !sanitizedErrorMessage.isBlank()) {
            message = message + ": " + sanitizedErrorMessage;
        }
        log.setMessage(limit(message, LOG_MESSAGE_LIMIT));
        log.setCreatedAt(now);
        return log;
    }

    private boolean isTerminal(AnalysisTaskStatus status) {
        return status == AnalysisTaskStatus.SUCCEEDED
            || status == AnalysisTaskStatus.FAILED
            || status == AnalysisTaskStatus.CANCELED;
    }

    private LocalDateTime now() {
        return LocalDateTime.ofInstant(clock.instant(), clock.getZone());
    }

    private void refreshProgressSnapshot(AnalysisTask task, LocalDateTime updatedAt) {
        try {
            progressSnapshotService.save(new TaskProgressSnapshot(
                task.getId(),
                task.getStatus(),
                task.getProgressPercent(),
                task.getCurrentStage(),
                task.getErrorCode(),
                task.getErrorMessage(),
                updatedAt.atZone(clock.getZone()).toInstant()
            ));
        } catch (RuntimeException exception) {
            log.warn("Task progress snapshot refresh failed for taskId={}", task.getId(), exception);
        }
    }

    private String sanitizeAndLimit(String value, int limit) {
        if (value == null) {
            return null;
        }
        String sanitized = SENSITIVE_WORDS.matcher(value).replaceAll("[redacted]");
        sanitized = WINDOWS_PATH.matcher(sanitized).replaceAll("[path]");
        sanitized = UNIX_HOME_PATH.matcher(sanitized).replaceAll("[path]");
        return limit(sanitized, limit);
    }

    private String limit(String value, int limit) {
        if (value == null || value.length() <= limit) {
            return value;
        }
        return value.substring(0, limit);
    }
}
