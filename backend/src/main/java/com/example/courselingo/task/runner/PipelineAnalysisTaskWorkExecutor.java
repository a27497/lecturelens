package com.example.courselingo.task.runner;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.common.logging.SafeLogSanitizer;
import java.time.Instant;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.EnumSet;
import java.util.List;
import java.util.Objects;
import java.util.Set;
import com.example.courselingo.vision.keyframe.VideoKeyframeEvidenceLifecycleService;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class PipelineAnalysisTaskWorkExecutor implements AnalysisTaskWorkExecutor {

    private static final Logger LOGGER = LoggerFactory.getLogger(PipelineAnalysisTaskWorkExecutor.class);

    private final List<PipelineAnalysisTaskStep> steps;
    private final List<PipelineAnalysisTaskStepName> stepNames;
    private final PipelineAnalysisTaskStep aiCallRecordStep;
    private final PipelineTaskProgressReporter progressReporter;
    private final PipelineRunnerWorkspace workspace;
    private final VideoKeyframeEvidenceLifecycleService evidenceLifecycleService;

    public PipelineAnalysisTaskWorkExecutor(List<PipelineAnalysisTaskStep> steps) {
        this(steps, PipelineTaskProgressReporter.NOOP, null, null);
    }

    public PipelineAnalysisTaskWorkExecutor(
        List<PipelineAnalysisTaskStep> steps,
        PipelineTaskProgressReporter progressReporter
    ) {
        this(steps, progressReporter, null, null);
    }

    PipelineAnalysisTaskWorkExecutor(
        List<PipelineAnalysisTaskStep> steps,
        PipelineTaskProgressReporter progressReporter,
        PipelineRunnerWorkspace workspace
    ) {
        this(steps, progressReporter, workspace, null);
    }

    PipelineAnalysisTaskWorkExecutor(
        List<PipelineAnalysisTaskStep> steps,
        PipelineTaskProgressReporter progressReporter,
        PipelineRunnerWorkspace workspace,
        VideoKeyframeEvidenceLifecycleService evidenceLifecycleService
    ) {
        this.steps = normalizeSteps(steps);
        this.stepNames = this.steps.stream()
            .map(PipelineAnalysisTaskStep::name)
            .toList();
        this.aiCallRecordStep = this.steps.stream()
            .filter(step -> step.name() == PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD)
            .findFirst()
            .orElse(null);
        this.progressReporter = progressReporter == null ? PipelineTaskProgressReporter.NOOP : progressReporter;
        this.workspace = workspace;
        this.evidenceLifecycleService = evidenceLifecycleService;
    }

    public static PipelineAnalysisTaskWorkExecutor skeleton() {
        List<PipelineAnalysisTaskStep> steps = PipelineAnalysisTaskStepName.ordered().stream()
            .map(NoopPipelineAnalysisTaskStep::new)
            .map(PipelineAnalysisTaskStep.class::cast)
            .toList();
        return new PipelineAnalysisTaskWorkExecutor(steps);
    }

    public List<PipelineAnalysisTaskStepName> stepNames() {
        return stepNames;
    }

    @Override
    public AnalysisTaskWorkResult execute(AnalysisTaskExecutionContext context) {
        validateContext(context);
        List<PipelineAnalysisTaskStepName> completed = new ArrayList<>();
        PipelineAnalysisTaskStepContext stepContext = new PipelineAnalysisTaskStepContext(
            context,
            completed
        );
        boolean completedSuccessfully = false;
        try {
            for (PipelineAnalysisTaskStep step : steps) {
                if (step.name() == PipelineAnalysisTaskStepName.EXTRACT_AUDIO) {
                    stepContext.markAsrBranchRunning();
                }
                long stepStartedNanos = System.nanoTime();
                Instant startedAt = Instant.now();
                progressReporter.stepStarted(step.name(), stepContext);
                LOGGER.info(
                    "event=pipeline_step_started taskId={} stepName={} started={}",
                    SafeLogSanitizer.sanitize(context.taskId()),
                    step.name(),
                    startedAt
                );
                try {
                    step.execute(stepContext);
                    completed.add(step.name());
                    if (step.name() == PipelineAnalysisTaskStepName.TRANSLATE_SUBTITLES
                        && !stepContext.asrBranchFailed()) {
                        stepContext.markAsrBranchSucceeded();
                    }
                    long durationMillis = elapsedMillis(stepStartedNanos);
                    Instant completedAt = Instant.now();
                    progressReporter.stepCompleted(step.name(), stepContext, durationMillis);
                    LOGGER.info(
                        "event=pipeline_step_completed taskId={} stepName={} started={} completed={} durationMillis={}",
                        SafeLogSanitizer.sanitize(context.taskId()),
                        step.name(),
                        startedAt,
                        completedAt,
                        durationMillis
                    );
                } catch (PipelineAnalysisTaskStepException exception) {
                    LOGGER.warn(
                        "event=pipeline_step_failed taskId={} stepName={} started={} completed={} durationMillis={} errorType={}",
                        SafeLogSanitizer.sanitize(context.taskId()),
                        step.name(),
                        startedAt,
                        Instant.now(),
                        elapsedMillis(stepStartedNanos),
                        exception.getClass().getSimpleName()
                    );
                    if (canDegradeAsrBranch(step.name(), exception, stepContext)) {
                        stepContext.setAsrBranchFailure(exception);
                        continue;
                    }
                    flushPendingAiCallRecordsAfterFailure(step, stepContext, exception);
                    throw exception;
                } catch (RuntimeException exception) {
                    LOGGER.warn(
                        "event=pipeline_step_failed taskId={} stepName={} started={} completed={} durationMillis={} errorType={}",
                        SafeLogSanitizer.sanitize(context.taskId()),
                        step.name(),
                        startedAt,
                        Instant.now(),
                        elapsedMillis(stepStartedNanos),
                        exception.getClass().getSimpleName()
                    );
                    PipelineAnalysisTaskStepException wrapped = new PipelineAnalysisTaskStepException(
                        step.name(),
                        exception
                    );
                    if (canDegradeAsrBranch(step.name(), exception, stepContext)) {
                        stepContext.setAsrBranchFailure(wrapped);
                        continue;
                    }
                    flushPendingAiCallRecordsAfterFailure(step, stepContext, wrapped);
                    throw wrapped;
                }
            }
            if (stepContext.asrBranchFailed()) {
                if (!stepContext.hasUsableVisionEvidence()) {
                    throw new PipelineAnalysisTaskStepException(
                        PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS,
                        new IllegalStateException("ASR and usable visual evidence are both unavailable")
                    );
                }
                completedSuccessfully = true;
                return AnalysisTaskWorkResult.degradedVisualOnly();
            }
            if (stepContext.visionBranchFailed()) {
                completedSuccessfully = true;
                return AnalysisTaskWorkResult.degradedAsrOnly();
            }
            completedSuccessfully = true;
            return new AnalysisTaskWorkResult(true, null, null);
        } finally {
            stepContext.cancelVisionBranchAndAwaitExit();
            if (!completedSuccessfully && evidenceLifecycleService != null) {
                cleanupFailedTaskEvidence(stepContext);
            }
            if (workspace != null) {
                boolean cleaned = workspace.cleanupTaskWorkspace(stepContext);
                LOGGER.info(
                    "event=pipeline_workspace_cleanup taskId={} success={}",
                    SafeLogSanitizer.sanitize(context.taskId()),
                    cleaned
                );
            }
        }
    }

    private void cleanupFailedTaskEvidence(PipelineAnalysisTaskStepContext context) {
        try {
            int deleted = evidenceLifecycleService.cleanupTaskEvidence(context.taskId(), context.userId());
            LOGGER.info(
                "event=pipeline_failed_evidence_cleanup taskId={} deletedRows={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                deleted
            );
        } catch (RuntimeException cleanupFailure) {
            LOGGER.warn(
                "event=pipeline_failed_evidence_cleanup_failed taskId={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                cleanupFailure.getClass().getSimpleName()
            );
        }
    }

    private static boolean canDegradeAsrBranch(
        PipelineAnalysisTaskStepName stepName,
        Throwable failure,
        PipelineAnalysisTaskStepContext context
    ) {
        if (!context.hasVisionBranchHandle() || Thread.currentThread().isInterrupted() || isCancellation(failure)) {
            return false;
        }
        return stepName == PipelineAnalysisTaskStepName.EXTRACT_AUDIO
            || stepName == PipelineAnalysisTaskStepName.TRANSCRIBE
            || stepName == PipelineAnalysisTaskStepName.PERSIST_SUBTITLES;
    }

    private static boolean isCancellation(Throwable failure) {
        Set<Throwable> visited = java.util.Collections.newSetFromMap(new java.util.IdentityHashMap<>());
        Throwable current = failure;
        while (current != null && visited.add(current)) {
            if (current instanceof InterruptedException || current instanceof java.util.concurrent.CancellationException) {
                return true;
            }
            if (current instanceof BusinessException businessException
                && businessException.errorCode() == ErrorCode.TASK_INVALID_STATUS) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static long elapsedMillis(long startedNanos) {
        return java.time.Duration.ofNanos(System.nanoTime() - startedNanos).toMillis();
    }

    private void flushPendingAiCallRecordsAfterFailure(
        PipelineAnalysisTaskStep failedStep,
        PipelineAnalysisTaskStepContext context,
        PipelineAnalysisTaskStepException original
    ) {
        if (aiCallRecordStep == null
            || failedStep.name() == PipelineAnalysisTaskStepName.WRITE_AI_CALL_RECORD
            || context.pendingAiCallRecords().isEmpty()) {
            return;
        }
        try {
            aiCallRecordStep.execute(context);
        } catch (RuntimeException flushFailure) {
            original.addSuppressed(flushFailure);
        }
    }

    private static List<PipelineAnalysisTaskStep> normalizeSteps(List<PipelineAnalysisTaskStep> steps) {
        if (steps == null || steps.isEmpty()) {
            throw new IllegalArgumentException("pipeline steps are required");
        }
        List<PipelineAnalysisTaskStep> checked = steps.stream()
            .map(step -> Objects.requireNonNull(step, "pipeline step must not be null"))
            .toList();

        Set<PipelineAnalysisTaskStepName> seen = EnumSet.noneOf(PipelineAnalysisTaskStepName.class);
        for (PipelineAnalysisTaskStep step : checked) {
            if (step.name() == null) {
                throw new IllegalArgumentException("pipeline step name is required");
            }
            if (!seen.add(step.name())) {
                throw new IllegalArgumentException("duplicate pipeline step: " + step.name());
            }
        }
        if (!seen.containsAll(PipelineAnalysisTaskStepName.ordered())) {
            throw new IllegalArgumentException("pipeline steps must cover every skeleton boundary");
        }
        return checked.stream()
            .sorted(Comparator.comparingInt(step -> step.name().ordinal()))
            .toList();
    }

    private static void validateContext(AnalysisTaskExecutionContext context) {
        if (context == null) {
            throw new IllegalArgumentException("analysis task context is required");
        }
        requireText(context.taskId(), "task id is required");
        requireText(context.uploadId(), "upload id is required");
        if (context.userId() == null) {
            throw new IllegalArgumentException("user id is required");
        }
        requireText(context.targetLanguage(), "target language is required");
        requireText(context.requestId(), "request id is required");
    }

    private static void requireText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException(message);
        }
    }
}
