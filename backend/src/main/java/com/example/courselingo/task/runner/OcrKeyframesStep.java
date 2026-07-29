package com.example.courselingo.task.runner;

import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.vision.ocr.VideoKeyframeOcrScanService;
import com.example.courselingo.vision.ocr.VisionOcrProperties;
import java.time.Clock;
import java.time.LocalDateTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OcrKeyframesStep implements PipelineAnalysisTaskStep {

    private static final Logger LOGGER = LoggerFactory.getLogger(OcrKeyframesStep.class);

    private final VideoKeyframeOcrScanService ocrScanService;
    private final VisionOcrProperties properties;
    private final TaskLogMapper taskLogMapper;
    private final Clock clock;

    public OcrKeyframesStep(
        VideoKeyframeOcrScanService ocrScanService,
        VisionOcrProperties properties,
        TaskLogMapper taskLogMapper,
        Clock clock
    ) {
        this.ocrScanService = ocrScanService;
        this.properties = properties == null ? new VisionOcrProperties() : properties;
        this.taskLogMapper = taskLogMapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.OCR_KEYFRAMES;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        if (context.hasVisionBranchHandle()) {
            awaitAdaptiveVisionBranch(context);
            return;
        }
        if (!properties.isEnabled()) {
            failWhenBothBranchesAreUnavailable(context, null);
            return;
        }
        try {
            ocrScanService.scan(context.taskId(), context.userId());
            context.setVisionBranchResult(VisionPipelineBranchResult.succeeded());
        } catch (Exception exception) {
            context.setVisionBranchResult(VisionPipelineBranchResult.failed(exception));
            writeWarning(context, exception);
            LOGGER.warn(
                "event=keyframe_ocr_skipped taskId={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                exception.getClass().getSimpleName()
            );
            if (properties.isFailTaskOnError()) {
                throw exception;
            }
            failWhenBothBranchesAreUnavailable(context, exception);
        }
    }

    private void awaitAdaptiveVisionBranch(PipelineAnalysisTaskStepContext context) {
        VisionPipelineBranchResult result;
        try {
            result = context.awaitVisionBranch();
        } catch (InterruptedException exception) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("vision preprocessing wait was interrupted", exception);
        }
        if (result.isSucceeded()) {
            return;
        }
        Exception warning = result.failure() instanceof Exception exception
            ? exception
            : new IllegalStateException("vision preprocessing branch failed");
        writeWarning(context, warning);
        LOGGER.warn(
            "event=vision_preprocessing_degraded taskId={} status={} errorType={}",
            SafeLogSanitizer.sanitize(context.taskId()),
            result.status(),
            warning.getClass().getSimpleName()
        );
        if (!context.asrBranchFailed()) {
            context.markVisionBranchDegraded();
        }
        failWhenBothBranchesAreUnavailable(context, warning);
    }

    private static void failWhenBothBranchesAreUnavailable(
        PipelineAnalysisTaskStepContext context,
        Exception visionFailure
    ) {
        if (!context.asrBranchFailed()) {
            return;
        }
        context.setVisionBranchResult(VisionPipelineBranchResult.failed(
            visionFailure == null ? new IllegalStateException("visual evidence is unavailable") : visionFailure
        ));
        IllegalStateException bothFailed = new IllegalStateException(
            "ASR and vision preprocessing branches both failed",
            context.asrBranchFailure()
        );
        if (visionFailure != null) {
            bothFailed.addSuppressed(visionFailure);
        }
        throw bothFailed;
    }

    private void writeWarning(PipelineAnalysisTaskStepContext context, Exception exception) {
        if (taskLogMapper == null) {
            return;
        }
        TaskLog log = new TaskLog();
        log.setTaskId(context.taskId());
        log.setUserId(context.userId());
        log.setLevel("WARN");
        log.setStage(PipelineAnalysisTaskStepName.OCR_KEYFRAMES.name());
        log.setMessage("Keyframe OCR skipped; ASR and LLM pipeline continues");
        log.setDetail(SafeLogSanitizer.sanitizeAndLimit(exception.getMessage()));
        log.setCreatedAt(LocalDateTime.ofInstant(clock.instant(), clock.getZone()));
        try {
            taskLogMapper.insert(log);
        } catch (RuntimeException logException) {
            LOGGER.warn(
                "event=keyframe_ocr_warning_log_failed taskId={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                logException.getClass().getSimpleName()
            );
        }
    }
}
