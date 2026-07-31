package com.example.courselingo.task.runner;

public record AnalysisTaskExecutionContext(
    String taskId,
    String uploadId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId
) {
    public AnalysisTaskExecutionContext(
        String taskId,
        String uploadId,
        Long userId,
        String targetLanguage,
        String requestId
    ) {
        this(taskId, uploadId, userId, "auto", targetLanguage, requestId);
    }
}
