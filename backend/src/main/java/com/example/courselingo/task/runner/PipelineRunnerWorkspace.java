package com.example.courselingo.task.runner;

import java.nio.file.Path;
import java.util.regex.Pattern;

public class PipelineRunnerWorkspace {

    private static final Pattern SAFE_SEGMENT = Pattern.compile("[^A-Za-z0-9._-]");
    private static final int MAX_SEGMENT_LENGTH = 80;

    private final Path workspaceRoot;

    public PipelineRunnerWorkspace(AnalysisTaskRunnerProperties properties) {
        this.workspaceRoot = properties.normalizedWorkspaceDir();
    }

    public Path audioOutputDirectory(PipelineAnalysisTaskStepContext context) {
        return taskWorkspace(context)
            .resolve("audio")
            .toAbsolutePath()
            .normalize();
    }

    public Path keyframeOutputDirectory(PipelineAnalysisTaskStepContext context) {
        return taskWorkspace(context)
            .resolve("keyframes")
            .toAbsolutePath()
            .normalize();
    }

    public Path asrChunksOutputDirectory(PipelineAnalysisTaskStepContext context) {
        return taskWorkspace(context)
            .resolve("asr-chunks")
            .toAbsolutePath()
            .normalize();
    }

    private Path taskWorkspace(PipelineAnalysisTaskStepContext context) {
        Path path = workspaceRoot
            .resolve(safeSegment(context.userId()))
            .resolve(safeSegment(context.taskId()))
            .resolve(safeSegment(context.requestId()))
            .toAbsolutePath()
            .normalize();
        if (!path.startsWith(workspaceRoot)) {
            throw new IllegalStateException("pipeline workspace path is invalid");
        }
        return path;
    }

    private static String safeSegment(Object value) {
        if (value == null) {
            return "unknown";
        }
        String sanitized = SAFE_SEGMENT.matcher(String.valueOf(value)).replaceAll("_");
        if (sanitized.isBlank()) {
            return "unknown";
        }
        if (sanitized.length() > MAX_SEGMENT_LENGTH) {
            return sanitized.substring(0, MAX_SEGMENT_LENGTH);
        }
        return sanitized;
    }
}
