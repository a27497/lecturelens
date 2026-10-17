package com.example.courselingo.subtitle.service;

record ValidatedTranslationCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId,
        com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {
    ValidatedTranslationCommand(
            String taskId,
            Long userId,
            String sourceLanguage,
            String targetLanguage,
            String requestId) {
        this(taskId, userId, sourceLanguage, targetLanguage, requestId, null);
    }

    ValidatedTranslationCommand withExecution(
            com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {
        return new ValidatedTranslationCommand(
                taskId, userId, sourceLanguage, targetLanguage, requestId, execution);
    }
}
