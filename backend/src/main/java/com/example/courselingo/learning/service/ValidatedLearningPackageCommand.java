package com.example.courselingo.learning.service;

record ValidatedLearningPackageCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId,
        com.example.courselingo.systemmodel.SystemModelExecutionRef execution,
    boolean sourceOnly) {
    ValidatedLearningPackageCommand(String taskId, Long userId, String sourceLanguage,
            String targetLanguage, String requestId,
            com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {
        this(taskId, userId, sourceLanguage, targetLanguage, requestId, execution, false);
    }
    ValidatedLearningPackageCommand(
            String taskId,
            Long userId,
            String sourceLanguage,
            String targetLanguage,
            String requestId) {
        this(taskId, userId, sourceLanguage, targetLanguage, requestId, null);
    }

    ValidatedLearningPackageCommand withExecution(
            com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {
        return new ValidatedLearningPackageCommand(
                taskId, userId, sourceLanguage, targetLanguage, requestId, execution, sourceOnly);
    }
}
