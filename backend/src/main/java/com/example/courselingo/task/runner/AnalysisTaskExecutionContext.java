package com.example.courselingo.task.runner;

public record AnalysisTaskExecutionContext(
    String taskId,
    String uploadId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId,
        com.example.courselingo.systemmodel.SystemModelExecutionRef systemModels) {
    public AnalysisTaskExecutionContext(
            String taskId,
            String uploadId,
            Long userId,
            String sourceLanguage,
            String targetLanguage,
            String requestId) {
        this(taskId, uploadId, userId, sourceLanguage, targetLanguage, requestId, null);
    }

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
