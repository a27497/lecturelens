package com.example.courselingo.learning.service;

record ValidatedLearningPackageCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId
) {
}
