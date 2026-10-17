package com.example.courselingo.learning.service;

record ValidatedLearningPackageCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId,
        com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {
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
                taskId, userId, sourceLanguage, targetLanguage, requestId, execution);
    }
}
