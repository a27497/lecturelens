package com.example.courselingo.learning.service;

public record GenerateLearningPackageCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId
) {
}
