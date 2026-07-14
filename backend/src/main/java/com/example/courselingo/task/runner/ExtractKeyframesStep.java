package com.example.courselingo.task.runner;

import com.example.courselingo.common.logging.SafeLogSanitizer;
import com.example.courselingo.task.entity.TaskLog;
import com.example.courselingo.task.mapper.TaskLogMapper;
import com.example.courselingo.vision.keyframe.VideoKeyframeProperties;
import com.example.courselingo.vision.keyframe.VideoKeyframeScanCommand;
import com.example.courselingo.vision.keyframe.VideoKeyframeScanService;
import java.nio.file.Path;
import java.nio.file.Files;
import java.io.IOException;
import java.time.Clock;
import java.time.LocalDateTime;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class ExtractKeyframesStep implements PipelineAnalysisTaskStep {

    private static final Logger LOGGER = LoggerFactory.getLogger(ExtractKeyframesStep.class);

    private final VideoKeyframeScanService keyframeScanService;
    private final PipelineRunnerWorkspace workspace;
    private final VideoKeyframeProperties properties;
    private final TaskLogMapper taskLogMapper;
    private final Clock clock;

    public ExtractKeyframesStep(
        VideoKeyframeScanService keyframeScanService,
        PipelineRunnerWorkspace workspace,
        VideoKeyframeProperties properties,
        TaskLogMapper taskLogMapper,
        Clock clock
    ) {
        this.keyframeScanService = keyframeScanService;
        this.workspace = workspace;
        this.properties = properties == null ? new VideoKeyframeProperties() : properties;
        this.taskLogMapper = taskLogMapper;
        this.clock = clock == null ? Clock.systemUTC() : clock;
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        if (!properties.isEnabled()) {
            return;
        }
        try {
            Path sourcePath = context.requireUploadedSourcePath();
            Path outputDirectory = workspace.keyframeOutputDirectory(context);
            ensureOutputDirectory(outputDirectory);
            keyframeScanService.scan(new VideoKeyframeScanCommand(
                context.taskId(),
                context.userId(),
                sourcePath,
                outputDirectory
            ));
        } catch (Exception exception) {
            writeWarning(context, exception);
            LOGGER.warn(
                "event=keyframe_scan_skipped taskId={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                exception.getClass().getSimpleName()
            );
        }
    }

    private static void ensureOutputDirectory(Path outputDirectory) throws IOException {
        Files.createDirectories(outputDirectory);
    }

    private void writeWarning(PipelineAnalysisTaskStepContext context, Exception exception) {
        if (taskLogMapper == null) {
            return;
        }
        TaskLog log = new TaskLog();
        log.setTaskId(context.taskId());
        log.setUserId(context.userId());
        log.setLevel("WARN");
        log.setStage(PipelineAnalysisTaskStepName.EXTRACT_KEYFRAMES.name());
        log.setMessage("Keyframe scan skipped; ASR and LLM pipeline continues");
        log.setDetail(SafeLogSanitizer.sanitizeAndLimit(exception.getMessage()));
        log.setCreatedAt(LocalDateTime.ofInstant(clock.instant(), clock.getZone()));
        try {
            taskLogMapper.insert(log);
        } catch (RuntimeException logException) {
            LOGGER.warn(
                "event=keyframe_scan_warning_log_failed taskId={} errorType={}",
                SafeLogSanitizer.sanitize(context.taskId()),
                logException.getClass().getSimpleName()
            );
        }
    }
}
