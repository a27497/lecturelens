package com.example.courselingo.subtitle.service;

public record TranslateSubtitleCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId,
        com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {
    public TranslateSubtitleCommand(
            String taskId,
            Long userId,
            String sourceLanguage,
            String targetLanguage,
            String requestId) {
        this(taskId, userId, sourceLanguage, targetLanguage, requestId, null);
    }
}
