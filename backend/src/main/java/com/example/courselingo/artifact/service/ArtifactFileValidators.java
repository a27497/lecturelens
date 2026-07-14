package com.example.courselingo.artifact.service;

import com.example.courselingo.artifact.domain.ArtifactType;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.Arrays;

final class ArtifactFileValidators {

    private static final int MAX_TASK_ID_LENGTH = 64;
    private static final int MAX_LANGUAGE_LENGTH = 32;
    private static final int MAX_CONTENT_TYPE_LENGTH = 128;
    private static final int MAX_CONTENT_BYTES = 10 * 1024 * 1024;

    private ArtifactFileValidators() {
    }

    static ValidatedArtifactFileCommand validateCommand(SaveArtifactFileCommand command) {
        if (command == null) {
            throw validationFailure("Artifact save command is required");
        }
        String taskId = validateKeySegment(command.taskId(), MAX_TASK_ID_LENGTH, "Task ID is required", "Task ID is invalid");
        validateUserId(command.userId());
        ArtifactType artifactType = validateArtifactType(command.artifactType());
        String language = validateKeySegment(command.language(), MAX_LANGUAGE_LENGTH, "Language is required", "Language is invalid");
        String fileName = ArtifactFileNameSanitizer.validateFileName(command.fileName());
        String contentType = requiredText(command.contentType(), "Content type is required");
        if (contentType.length() > MAX_CONTENT_TYPE_LENGTH
            || containsControlCharacter(contentType)
            || ArtifactSensitiveDataValidator.containsSensitiveData(contentType)) {
            throw validationFailure("Content type is invalid");
        }
        byte[] contentBytes = command.contentBytes();
        if (contentBytes == null || contentBytes.length == 0) {
            throw validationFailure("Artifact content is required");
        }
        if (contentBytes.length > MAX_CONTENT_BYTES) {
            throw validationFailure("Artifact content is too large");
        }
        return new ValidatedArtifactFileCommand(
            taskId,
            command.userId(),
            artifactType,
            language,
            fileName,
            contentType,
            Arrays.copyOf(contentBytes, contentBytes.length)
        );
    }

    static ValidatedArtifactFileScope validateScope(
        String taskId,
        Long userId,
        ArtifactType artifactType,
        String language
    ) {
        String normalizedTaskId = validateKeySegment(taskId, MAX_TASK_ID_LENGTH, "Task ID is required", "Task ID is invalid");
        validateUserId(userId);
        ArtifactType normalizedArtifactType = validateArtifactType(artifactType);
        String normalizedLanguage = validateKeySegment(language, MAX_LANGUAGE_LENGTH, "Language is required", "Language is invalid");
        return new ValidatedArtifactFileScope(normalizedTaskId, userId, normalizedArtifactType, normalizedLanguage);
    }

    static ValidatedArtifactTaskScope validateTaskScope(String taskId, Long userId) {
        String normalizedTaskId = validateKeySegment(taskId, MAX_TASK_ID_LENGTH, "Task ID is required", "Task ID is invalid");
        validateUserId(userId);
        return new ValidatedArtifactTaskScope(normalizedTaskId, userId);
    }

    private static ArtifactType validateArtifactType(ArtifactType artifactType) {
        if (artifactType == null) {
            throw validationFailure("Artifact type is required");
        }
        return artifactType;
    }

    private static void validateUserId(Long userId) {
        if (userId == null || userId <= 0) {
            throw validationFailure("User ID is required");
        }
    }

    private static String validateKeySegment(String value, int maxLength, String missingMessage, String invalidMessage) {
        String normalized = requiredText(value, missingMessage);
        if (normalized.length() > maxLength
            || normalized.contains("/")
            || normalized.contains("\\")
            || normalized.contains("..")
            || normalized.contains(":")
            || containsControlCharacter(normalized)
            || ArtifactSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure(invalidMessage);
        }
        return normalized;
    }

    private static String requiredText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw validationFailure(message);
        }
        return value.strip();
    }

    private static boolean containsControlCharacter(String value) {
        for (int index = 0; index < value.length(); index++) {
            if (Character.isISOControl(value.charAt(index))) {
                return true;
            }
        }
        return false;
    }

    static BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }
}
