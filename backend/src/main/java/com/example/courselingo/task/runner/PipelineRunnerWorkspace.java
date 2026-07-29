package com.example.courselingo.task.runner;

import java.io.IOException;
import java.nio.file.DirectoryNotEmptyException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Comparator;
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

    public Path visionAnalysisDirectory(PipelineAnalysisTaskStepContext context) {
        return taskWorkspace(context)
            .resolve("vision-analysis")
            .toAbsolutePath()
            .normalize();
    }

    public Path asrChunksOutputDirectory(PipelineAnalysisTaskStepContext context) {
        return taskWorkspace(context)
            .resolve("asr-chunks")
            .toAbsolutePath()
            .normalize();
    }

    boolean cleanupTaskWorkspace(PipelineAnalysisTaskStepContext context) {
        Path requestWorkspace = taskWorkspace(context);
        Path taskDirectory = requestWorkspace.getParent();
        Path userDirectory = taskDirectory == null ? null : taskDirectory.getParent();
        try {
            if (Files.exists(requestWorkspace)) {
                try (var paths = Files.walk(requestWorkspace)) {
                    for (Path path : paths.sorted(Comparator.reverseOrder()).toList()) {
                        Files.deleteIfExists(path);
                    }
                }
            }
            deleteIfEmpty(taskDirectory);
            deleteIfEmpty(userDirectory);
            return true;
        } catch (IOException exception) {
            return false;
        }
    }

    private static void deleteIfEmpty(Path directory) throws IOException {
        if (directory == null) {
            return;
        }
        try {
            Files.deleteIfExists(directory);
        } catch (DirectoryNotEmptyException ignored) {
            // Another request or task still owns content below this scoped parent.
        }
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
