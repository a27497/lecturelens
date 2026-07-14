package com.example.courselingo.task.runner;

public record AnalysisTaskExecutionContext(
    String taskId,
    String uploadId,
    Long userId,
    String targetLanguage,
    String requestId
) {
}
