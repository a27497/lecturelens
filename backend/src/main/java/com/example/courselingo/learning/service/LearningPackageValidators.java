package com.example.courselingo.learning.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

final class LearningPackageValidators {

    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final int MAX_LANGUAGE_LENGTH = 32;

    private LearningPackageValidators() {
    }

    static ValidatedLearningPackageCommand validateCommand(GenerateLearningPackageCommand command) {
        if (command == null) {
            throw validationFailure("Learning package command is required");
        }
        String taskId = requiredText(command.taskId(), "Task ID is required");
        if (taskId.length() > MAX_TASK_ID_LENGTH) {
            throw validationFailure("Task ID is invalid");
        }
        validateUserId(command.userId());
        String sourceLanguage = validateLanguage(command.sourceLanguage(), "Source language is required");
        String targetLanguage = validateLanguage(command.targetLanguage(), "Target language is required");
        String requestId = requiredText(command.requestId(), "Request ID is required");
        return new ValidatedLearningPackageCommand(
            taskId,
            command.userId(),
            sourceLanguage,
            targetLanguage,
            requestId
        );
    }

    static ValidatedLearningPackageScope validateScope(String taskId, Long userId, String targetLanguage) {
        String normalizedTaskId = requiredText(taskId, "Task ID is required");
        if (normalizedTaskId.length() > MAX_TASK_ID_LENGTH) {
            throw validationFailure("Task ID is invalid");
        }
        validateUserId(userId);
        return new ValidatedLearningPackageScope(
            normalizedTaskId,
            userId,
            validateLanguage(targetLanguage, "Target language is required")
        );
    }

    private static void validateUserId(Long userId) {
        if (userId == null || userId <= 0) {
            throw validationFailure("User ID is required");
        }
    }

    private static String validateLanguage(String language, String message) {
        String normalized = requiredText(language, message);
        if (normalized.length() > MAX_LANGUAGE_LENGTH) {
            throw validationFailure("Language is invalid");
        }
        return normalized;
    }

    private static String requiredText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw validationFailure(message);
        }
        return value.strip();
    }

    static BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }
}
