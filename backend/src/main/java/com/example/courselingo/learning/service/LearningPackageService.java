package com.example.courselingo.learning.service;

public interface LearningPackageService {

    int generateLearningPackage(GenerateLearningPackageCommand command);

    default LearningPackageAiCallResult generateLearningPackageWithAiCallRecord(
        GenerateLearningPackageCommand command
    ) {
        int savedCount = generateLearningPackage(command);
        return new LearningPackageAiCallResult(
            savedCount,
            "learning-package-service",
            null,
            null,
            null,
            null,
            null,
            null,
            savedCount,
            null,
            null
        );
    }

    int deleteLearningPackage(String taskId, Long userId, String targetLanguage);
}
