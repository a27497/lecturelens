package com.example.courselingo.task.runner;

import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.fusion.VideoSegmentFusionService;
import com.example.courselingo.fusion.VideoSegmentProperties;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.TaskLogMapper;
import java.time.Clock;
import java.time.LocalDateTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class FuseVideoSegmentsStep implements PipelineAnalysisTaskStep {

    private static final Logger LOGGER = LoggerFactory.getLogger(FuseVideoSegmentsStep.class);

    private final VideoSegmentFusionService videoSegmentFusionService;
    private final VideoSegmentProperties properties;
    private final TaskLogMapper taskLogMapper;
    private final Clock clock;

    public FuseVideoSegmentsStep(
        VideoSegmentFusionService videoSegmentFusionService,
        VideoSegmentProperties properties,
        TaskLogMapper taskLogMapper,
        Clock clock
    ) {
        this.videoSegmentFusionService = videoSegmentFusionService;
        this.properties = properties == null ? new VideoSegmentProperties() : properties;
        this.taskLogMapper = taskLogMapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        if (!properties.isEnabled()) {
            return;
        }
        try {
            videoSegmentFusionService.fuse(context.taskId(), context.userId());
        } catch (Exception exception) {
            writeWarning(context, exception);
            LOGGER.warn(
                "event=video_segment_fusion_skipped taskId={} errorType={}",
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
        log.setStage(PipelineAnalysisTaskStepName.FUSE_VIDEO_SEGMENTS.name());
        log.setMessage("Video segment fusion skipped; ASR and LLM pipeline continues");
        log.setDetail(SafeLogSanitizer.sanitizeAndLimit(exception.getMessage()));
        log.setCreatedAt(LocalDateTime.ofInstant(clock.instant(), clock.getZone()));
        try {
            taskLogMapper.insert(log);
        } catch (RuntimeException logException) {
            LOGGER.warn(
                "event=video_segment_fusion_warning_log_failed taskId={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                logException.getClass().getSimpleName()
            );
        }
    }
}
