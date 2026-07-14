package com.example.courselingo.task.runner;

import java.nio.file.Path;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.task.runner")
public record AnalysisTaskRunnerProperties(Path workspaceDir) {

    public AnalysisTaskRunnerProperties() {
        this(defaultWorkspaceDir());
    }

    public AnalysisTaskRunnerProperties {
        if (workspaceDir == null) {
            workspaceDir = defaultWorkspaceDir();
        }
    }

    Path normalizedWorkspaceDir() {
        return workspaceDir.toAbsolutePath().normalize();
    }

    private static Path defaultWorkspaceDir() {
        return Path.of(System.getProperty("java.io.tmpdir"), "courselingo", "runner");
    }
}
