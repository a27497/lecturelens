package com.example.courselingo.task.runner;

import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.task.mapper.AnalysisTaskMapper;
import com.example.courselingo.task.progress.TaskProgressSnapshot;
import com.example.courselingo.task.progress.TaskProgressSnapshotService;
import java.time.Clock;
import java.time.Instant;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

final class DefaultPipelineTaskProgressReporter implements PipelineTaskProgressReporter {

    private static final Logger LOGGER = LoggerFactory.getLogger(DefaultPipelineTaskProgressReporter.class);

    private final AnalysisTaskMapper analysisTaskMapper;
    private final TaskProgressSnapshotService progressSnapshotService;
    private final Clock clock;

    DefaultPipelineTaskProgressReporter(
        AnalysisTaskMapper analysisTaskMapper,
        TaskProgressSnapshotService progressSnapshotService,
        Clock clock
    ) {
        this.analysisTaskMapper = analysisTaskMapper;
        this.progressSnapshotService = progressSnapshotService;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    public void stepStarted(PipelineAnalysisTaskStepName stepName, PipelineAnalysisTaskStepContext context) {
        refresh(stepName, context, progressAtStart(stepName));
    }

    @Override
    public void stepCompleted(
        PipelineAnalysisTaskStepName stepName,
        PipelineAnalysisTaskStepContext context,
        long durationMillis
    ) {
        refresh(stepName, context, progressAtCompletion(stepName));
    }

    private void refresh(PipelineAnalysisTaskStepName stepName, PipelineAnalysisTaskStepContext context, int progress) {
        if (stepName == null || context == null) {
            return;
        }
        String currentStage = stepName.name();
        int normalizedProgress = Math.max(0, Math.min(99, progress));
        int updated;
        try {
            updated = analysisTaskMapper.updateRunningProgressByIdAndUserId(
                context.taskId(),
                context.userId(),
                normalizedProgress,
                currentStage
            );
        } catch (RuntimeException exception) {
            LOGGER.warn(
                "event=pipeline_progress_mysql_refresh_failed taskId={} stepName={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                SafeLogSanitizer.sanitize(currentStage),
                exception.getClass().getSimpleName()
            );
            return;
        }
        if (updated != 1) {
            LOGGER.warn(
                "event=pipeline_progress_mysql_refresh_rejected taskId={} stepName={} updatedRows={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                SafeLogSanitizer.sanitize(currentStage),
                updated
            );
            return;
        }
        try {
            progressSnapshotService.save(new TaskProgressSnapshot(
                context.taskId(),
                "RUNNING",
                normalizedProgress,
                currentStage,
                null,
                null,
                Instant.now(clock)
            ));
        } catch (RuntimeException exception) {
            LOGGER.warn(
                "event=pipeline_progress_snapshot_refresh_failed taskId={} stepName={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                SafeLogSanitizer.sanitize(currentStage),
                exception.getClass().getSimpleName()
            );
        }
    }

    private static int progressAtStart(PipelineAnalysisTaskStepName stepName) {
        return switch (stepName) {
            case VALIDATE_TASK -> 1;
            case RESOLVE_UPLOADED_SOURCE -> 5;
            case EXTRACT_KEYFRAMES -> 10;
            case EXTRACT_AUDIO -> 13;
            case TRANSCRIBE -> 20;
            case PERSIST_SUBTITLES -> 55;
            case TRANSLATE_SUBTITLES -> 60;
            case GENERATE_LEARNING_PACKAGE -> 72;
            case GENERATE_ARTIFACTS -> 88;
            case OCR_KEYFRAMES -> 95;
            case ANALYZE_KEYFRAMES -> 97;
            case FUSE_VIDEO_SEGMENTS -> 98;
            case WRITE_AI_CALL_RECORD -> 98;
            case UPDATE_TASK_PROGRESS_STATUS -> 98;
        };
    }

    private static int progressAtCompletion(PipelineAnalysisTaskStepName stepName) {
        return switch (stepName) {
            case VALIDATE_TASK -> 5;
            case RESOLVE_UPLOADED_SOURCE -> 10;
            case EXTRACT_KEYFRAMES -> 13;
            case EXTRACT_AUDIO -> 20;
            case TRANSCRIBE -> 55;
            case PERSIST_SUBTITLES -> 60;
            case TRANSLATE_SUBTITLES -> 72;
            case GENERATE_LEARNING_PACKAGE -> 88;
            case GENERATE_ARTIFACTS -> 95;
            case OCR_KEYFRAMES -> 97;
            case ANALYZE_KEYFRAMES -> 98;
            case FUSE_VIDEO_SEGMENTS -> 98;
            case WRITE_AI_CALL_RECORD -> 98;
            case UPDATE_TASK_PROGRESS_STATUS -> 99;
        };
    }
}
