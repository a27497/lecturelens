package com.example.courselingo.learning.service;

public record GenerateLearningPackageCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId,
        com.example.courselingo.systemmodel.SystemModelExecutionRef execution,
    boolean sourceOnly) {
    public GenerateLearningPackageCommand(String taskId, Long userId, String sourceLanguage,
            String targetLanguage, String requestId,
            com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {
        this(taskId, userId, sourceLanguage, targetLanguage, requestId, execution, false);
    }
    public GenerateLearningPackageCommand(
            String taskId,
            Long userId,
            String sourceLanguage,
            String targetLanguage,
            String requestId) {
        this(taskId, userId, sourceLanguage, targetLanguage, requestId, null);
    }
}
