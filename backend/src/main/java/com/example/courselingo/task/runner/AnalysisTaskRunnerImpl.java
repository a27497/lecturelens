package com.example.courselingo.task.runner;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.common.metrics.BusinessMetrics;
import com.example.courselingo.common.tracing.TracingContext;
import com.example.courselingo.common.tracing.TracingContextFactory;
import com.example.courselingo.common.tracing.TracingContextHolder;
import com.example.courselingo.common.tracing.TracingScope;
import com.example.courselingo.dispatch.BoundedTaskExecutor;
import com.example.courselingo.mq.AnalysisTaskMessage;
import com.example.courselingo.task.dto.AnalysisTaskStateChangeCommand;
import com.example.courselingo.task.entity.AnalysisTask;
import com.example.courselingo.task.claim.TaskClaimResult;
import com.example.courselingo.task.claim.TaskClaimService;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.model.AnalysisTaskStage;
import com.example.courselingo.task.model.AnalysisTaskStatus;
import com.example.courselingo.task.service.AnalysisTaskStateService;
import java.time.Duration;
import java.util.Objects;
import java.util.regex.Pattern;
import org.springframework.beans.factory.annotation.Autowired;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class AnalysisTaskRunnerImpl implements AnalysisTaskRunner {

    private static final Logger log = LoggerFactory.getLogger(AnalysisTaskRunnerImpl.class);
    private static final int ERROR_MESSAGE_LIMIT = 1024;
    private static final Pattern SENSITIVE_WORDS = Pattern.compile(
        "(?i)access\\s*token|refresh\\s*token|api\\s*key|secret\\s*key|token|secret"
    );
    private static final Pattern WINDOWS_PATH = Pattern.compile("[A-Za-z]:\\\\\\S*");
    private static final Pattern UNIX_HOME_PATH = Pattern.compile("/(?:home|Users)/\\S*");

    private final AnalysisTaskMapper analysisTaskMapper;
    private final AnalysisTaskStateService stateService;
    private final AnalysisTaskWorkExecutor workExecutor;
    private final BoundedTaskExecutor boundedTaskExecutor;
    private final TaskClaimService taskClaimService;
    private final BusinessMetrics businessMetrics;

    @Autowired
    public AnalysisTaskRunnerImpl(
        AnalysisTaskMapper analysisTaskMapper,
        AnalysisTaskStateService stateService,
        AnalysisTaskWorkExecutor workExecutor,
        BoundedTaskExecutor boundedTaskExecutor,
        TaskClaimService taskClaimService,
        BusinessMetrics businessMetrics
    ) {
        this.analysisTaskMapper = analysisTaskMapper;
        this.stateService = stateService;
        this.workExecutor = workExecutor;
        this.boundedTaskExecutor = boundedTaskExecutor;
        this.taskClaimService = taskClaimService;
        this.businessMetrics = businessMetrics == null ? BusinessMetrics.noop() : businessMetrics;
    }

    public AnalysisTaskRunnerImpl(
        AnalysisTaskMapper analysisTaskMapper,
        AnalysisTaskStateService stateService,
        AnalysisTaskWorkExecutor workExecutor,
        BoundedTaskExecutor boundedTaskExecutor,
        TaskClaimService taskClaimService
    ) {
        this(
            analysisTaskMapper,
            stateService,
            workExecutor,
            boundedTaskExecutor,
            taskClaimService,
            BusinessMetrics.noop()
        );
    }

    @Override
    public void run(AnalysisTaskMessage message) {
        try (TracingScope ignored = openMessageTracing(message)) {
            long startedNanos = System.nanoTime();
            String outcome = "failure";
            businessMetrics.incrementTaskRunner("run", "start");
            logRunnerBoundary("runner_run_requested", message, "start");
            try {
                AnalysisTask task = loadAndValidate(message);
                AnalysisTaskStatus status = AnalysisTaskStatus.fromDatabaseValue(task.getStatus());
                if (status != AnalysisTaskStatus.QUEUED) {
                    throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
                }

                acquireClaim(message);
                try {
                    changeState(message, AnalysisTaskStatus.RUNNING, task.getProgressPercent(), AnalysisTaskStage.EXTRACT_AUDIO,
                        null, null);
                    executeWork(message);
                    outcome = "success";
                    logRunnerBoundary("runner_run_completed", message, "success");
                } finally {
                    taskClaimService.release(message.taskId(), message.requestId());
                }
            } finally {
                businessMetrics.incrementTaskRunner("run", outcome);
                businessMetrics.recordTaskRunnerDuration("run", outcome, Duration.ofNanos(System.nanoTime() - startedNanos));
            }
        }
    }

    @Override
    public void retry(AnalysisTaskMessage message) {
        try (TracingScope ignored = openMessageTracing(message)) {
            String outcome = "failure";
            businessMetrics.incrementTaskRunner("retry", "start");
            try {
                logRunnerBoundary("runner_retry_requested", message, "start");
                AnalysisTask task = loadAndValidate(message);
                AnalysisTaskStatus status = AnalysisTaskStatus.fromDatabaseValue(task.getStatus());
                if (status != AnalysisTaskStatus.RETRYING) {
                    throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
                }

                changeState(message, AnalysisTaskStatus.QUEUED, task.getProgressPercent(), AnalysisTaskStage.QUEUED,
                    null, null);
                run(message);
                outcome = "success";
            } finally {
                businessMetrics.incrementTaskRunner("retry", outcome);
            }
        }
    }

    @Override
    public void cancel(AnalysisTaskMessage message) {
        try (TracingScope ignored = openMessageTracing(message)) {
            String outcome = "failure";
            businessMetrics.incrementTaskRunner("cancel", "start");
            try {
                logRunnerBoundary("runner_cancel_requested", message, "start");
                AnalysisTask task = loadAndValidate(message);
                AnalysisTaskStatus status = AnalysisTaskStatus.fromDatabaseValue(task.getStatus());
                if (status == AnalysisTaskStatus.SUCCEEDED
                    || status == AnalysisTaskStatus.FAILED
                    || status == AnalysisTaskStatus.CANCELED) {
                    throw new BusinessException(ErrorCode.TASK_INVALID_STATUS);
                }

                changeState(message, AnalysisTaskStatus.CANCELED, task.getProgressPercent(), AnalysisTaskStage.FAILED,
                    null, null);
                taskClaimService.release(message.taskId(), message.requestId());
                logRunnerBoundary("runner_cancel_completed", message, "success");
                outcome = "success";
            } finally {
                businessMetrics.incrementTaskRunner("cancel", outcome);
            }
        }
    }

    private static TracingScope openMessageTracing(AnalysisTaskMessage message) {
        if (message == null || isBlank(message.traceId()) || isBlank(message.requestId())) {
            return TracingContextHolder.open(TracingContextFactory.create());
        }
        return TracingContextHolder.open(new TracingContext(message.traceId(), message.requestId()));
    }

    private static void logRunnerBoundary(String event, AnalysisTaskMessage message, String outcome) {
        log.info(
            "event={} taskId={} requestId={} stage=runner outcome={}",
            event,
            message == null ? "" : SafeLogSanitizer.sanitize(message.taskId()),
            message == null ? "" : SafeLogSanitizer.sanitize(message.requestId()),
            outcome
        );
    }

    private void acquireClaim(AnalysisTaskMessage message) {
        TaskClaimResult result = taskClaimService.tryAcquire(message.taskId(), message.requestId());
        if (!result.acquired()) {
            throw new BusinessException(ErrorCode.TASK_DUPLICATE_CLAIMED);
        }
    }

    private void executeWork(AnalysisTaskMessage message) {
        AnalysisTaskExecutionContext context = new AnalysisTaskExecutionContext(
            message.taskId(),
            message.uploadId(),
            message.userId(),
            message.targetLanguage(),
            message.requestId()
        );

        AnalysisTaskWorkResult result;
        try {
            result = boundedTaskExecutor.submitAndWait(
                message.taskId(),
                message.requestId(),
                () -> workExecutor.execute(context)
            );
        } catch (Exception exception) {
            if (isRetryableExecutorException(exception)) {
                throw exception;
            }
            String sanitized = sanitizeAndLimit(exception.getMessage());
            changeState(message, AnalysisTaskStatus.FAILED, null, failureStage(exception, sanitized),
                ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code(), sanitized);
            throw new BusinessException(ErrorCode.TASK_RUNNER_EXECUTION_FAILED, sanitized, exception);
        }

        if (result == null || !result.success()) {
            String errorCode = result == null || isBlank(result.errorCode())
                ? ErrorCode.TASK_RUNNER_EXECUTION_FAILED.code()
                : result.errorCode();
            String errorMessage = result == null ? "Analysis task work executor failed" : result.errorMessage();
            changeState(message, AnalysisTaskStatus.FAILED, null, failureStage(null, errorMessage),
                errorCode, sanitizeAndLimit(errorMessage));
            return;
        }

        changeState(message, AnalysisTaskStatus.SUCCEEDED, 100, AnalysisTaskStage.DONE, null, null);
    }

    private static AnalysisTaskStage failureStage(Exception exception, String errorMessage) {
        if (exception instanceof PipelineAnalysisTaskStepException stepException) {
            return failureStage(stepException.stepName());
        }
        if (errorMessage != null && errorMessage.contains(PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES.name())) {
            return AnalysisTaskStage.TRANSLATE;
        }
        return AnalysisTaskStage.FAILED;
    }

    private static AnalysisTaskStage failureStage(PipelineAnalysisTaskStepName stepName) {
        if (stepName == null) {
            return AnalysisTaskStage.FAILED;
        }
        return switch (stepName) {
            case EXTRACT_AUDIO -> AnalysisTaskStage.EXTRACT_AUDIO;
            case TRANSCRIBE, PERSIST_SUBTITLES -> AnalysisTaskStage.ASR;
            case TRANSLATE_SUBTITLES -> AnalysisTaskStage.TRANSLATE;
            case GENERATE_LEARNING_PACKAGE -> AnalysisTaskStage.GENERATE_LEARNING_PACKAGE;
            case GENERATE_ARTIFACTS, WRITE_AI_CALL_RECORD -> AnalysisTaskStage.GENERATE_ARTIFACTS;
            default -> AnalysisTaskStage.FAILED;
        };
    }

    private AnalysisTask loadAndValidate(AnalysisTaskMessage message) {
        if (message == null) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        message.validate();

        AnalysisTask task = analysisTaskMapper.selectByIdAndUserId(message.taskId(), message.userId());
        if (task == null) {
            throw new BusinessException(ErrorCode.TASK_NOT_FOUND);
        }
        if (!Objects.equals(task.getUploadId(), message.uploadId())) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        if (!Objects.equals(task.getTargetLanguage(), message.targetLanguage())) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
        return task;
    }

    private void changeState(
        AnalysisTaskMessage message,
        AnalysisTaskStatus status,
        Integer progress,
        AnalysisTaskStage stage,
        String errorCode,
        String errorMessage
    ) {
        stateService.changeState(AnalysisTaskStateChangeCommand.builder()
            .taskId(message.taskId())
            .userId(message.userId())
            .targetStatus(status)
            .progressPercent(progress)
            .stage(stage)
            .errorCode(errorCode)
            .errorMessage(errorMessage)
            .build());
    }

    private static String sanitizeAndLimit(String value) {
        if (value == null) {
            return null;
        }
        String sanitized = SENSITIVE_WORDS.matcher(value).replaceAll("[redacted]");
        sanitized = WINDOWS_PATH.matcher(sanitized).replaceAll("[path]");
        sanitized = UNIX_HOME_PATH.matcher(sanitized).replaceAll("[path]");
        if (sanitized.length() <= ERROR_MESSAGE_LIMIT) {
            return sanitized;
        }
        return sanitized.substring(0, ERROR_MESSAGE_LIMIT);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }

    private static boolean isRetryableExecutorException(Exception exception) {
        return exception instanceof BusinessException businessException
            && (businessException.errorCode() == ErrorCode.TASK_EXECUTOR_BUSY
                || businessException.errorCode() == ErrorCode.TASK_EXECUTOR_SHUTDOWN);
    }
}
