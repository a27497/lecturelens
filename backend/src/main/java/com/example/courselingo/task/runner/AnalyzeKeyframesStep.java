package com.example.courselingo.task.runner;

import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.vision.analysis.VisionAnalysisProperties;
import com.example.courselingo.vision.analysis.VisionAnalysisService;
import java.time.Clock;
import java.time.LocalDateTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class AnalyzeKeyframesStep implements PipelineAnalysisTaskStep {

    private static final Logger LOGGER = LoggerFactory.getLogger(AnalyzeKeyframesStep.class);

    private final VisionAnalysisService visionAnalysisService;
    private final VisionAnalysisProperties properties;
    private final TaskLogMapper taskLogMapper;
    private final Clock clock;

    public AnalyzeKeyframesStep(
        VisionAnalysisService visionAnalysisService,
        VisionAnalysisProperties properties,
        TaskLogMapper taskLogMapper,
        Clock clock
    ) {
        this.visionAnalysisService = visionAnalysisService;
        this.properties = properties == null ? new VisionAnalysisProperties() : properties;
        this.taskLogMapper = taskLogMapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        if (!properties.isEnabled()) {
            return;
        }
        try {
            visionAnalysisService.scan(context.taskId(), context.userId());
        } catch (Exception exception) {
            writeWarning(context, exception);
            LOGGER.warn(
                "event=keyframe_visual_analysis_skipped taskId={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                exception.getClass().getSimpleName()
            );
            if (properties.isFailTaskOnError()) {
                throw exception;
            }
        }
    }

    private void writeWarning(PipelineAnalysisTaskStepContext context, Exception exception) {
        if (taskLogMapper == null) {
            return;
        }
        TaskLog log = new TaskLog();
        log.setTaskId(context.taskId());
        log.setUserId(context.userId());
        log.setLevel("WARN");
        log.setStage(PipelineAnalysisTaskStepName.ANALYZE_KEYFRAMES.name());
        log.setMessage("Keyframe visual analysis skipped; ASR and LLM pipeline continues");
        log.setDetail(SafeLogSanitizer.sanitizeAndLimit(exception.getMessage()));
        log.setCreatedAt(LocalDateTime.ofInstant(clock.instant(), clock.getZone()));
        try {
            taskLogMapper.insert(log);
        } catch (RuntimeException logException) {
            LOGGER.warn(
                "event=keyframe_visual_analysis_warning_log_failed taskId={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                logException.getClass().getSimpleName()
            );
        }
    }
}
