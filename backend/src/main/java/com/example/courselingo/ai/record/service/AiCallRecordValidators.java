package com.example.courselingo.ai.record.service;

import com.example.courselingo.ai.record.dto.CompleteAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.FailAiCallRecordCommand;
import com.example.courselingo.ai.record.dto.StartAiCallRecordCommand;
import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;

final class AiCallRecordValidators {

    private AiCallRecordValidators() {
    }

    static ValidatedStartAiCallRecordCommand validateStart(
        StartAiCallRecordCommand command,
        AiCallRecordSanitizer sanitizer
    ) {
        if (command == null) {
            throw validationFailure();
        }
        String taskId = validateRequiredString(command.taskId(), 64, sanitizer);
        Long userId = validateUserId(command.userId());
        if (command.callType() == null || command.stage() == null) {
            throw validationFailure();
        }
        String provider = validateRequiredString(command.provider(), 64, sanitizer);
        String model = validateOptionalString(command.model(), 128, sanitizer);
        String requestFingerprint = validateFingerprint(command.requestFingerprint(), sanitizer);
        Integer inputUnits = validateNonNegative(command.inputUnits());
        return new ValidatedStartAiCallRecordCommand(
            taskId,
            userId,
            command.callType(),
            command.stage(),
            provider,
            model,
            requestFingerprint,
            inputUnits
        );
    }

    static ValidatedCompleteAiCallRecordCommand validateComplete(
        CompleteAiCallRecordCommand command,
        AiCallRecordSanitizer sanitizer
    ) {
        if (command == null) {
            throw validationFailure();
        }
        return new ValidatedCompleteAiCallRecordCommand(
            validateRecordId(command.recordId()),
            validateRequiredString(command.taskId(), 64, sanitizer),
            validateUserId(command.userId()),
            validateNonNegative(command.durationMillis()),
            validateNonNegative(command.promptTokens()),
            validateNonNegative(command.completionTokens()),
            validateNonNegative(command.totalTokens()),
            validateNonNegative(command.inputUnits()),
            validateNonNegative(command.outputUnits()),
            validateFingerprint(command.requestFingerprint(), sanitizer),
            validateFingerprint(command.responseFingerprint(), sanitizer)
        );
    }

    static ValidatedFailAiCallRecordCommand validateFail(
        FailAiCallRecordCommand command,
        AiCallRecordSanitizer sanitizer
    ) {
        if (command == null) {
            throw validationFailure();
        }
        return new ValidatedFailAiCallRecordCommand(
            validateRecordId(command.recordId()),
            validateRequiredString(command.taskId(), 64, sanitizer),
            validateUserId(command.userId()),
            validateNonNegative(command.durationMillis()),
            validateOptionalString(command.errorCode(), 64, sanitizer),
            sanitizer.sanitizeErrorMessage(command.errorMessage()),
            command.retryable(),
            validateFingerprint(command.requestFingerprint(), sanitizer),
            validateFingerprint(command.responseFingerprint(), sanitizer)
        );
    }

    static ValidatedAiCallRecordScope validateScope(String taskId, Long userId, AiCallRecordSanitizer sanitizer) {
        return new ValidatedAiCallRecordScope(
            validateRequiredString(taskId, 64, sanitizer),
            validateUserId(userId)
        );
    }

    private static Long validateRecordId(Long id) {
        if (id == null || id <= 0) {
            throw validationFailure();
        }
        return id;
    }

    private static Long validateUserId(Long userId) {
        if (userId == null || userId <= 0) {
            throw validationFailure();
        }
        return userId;
    }

    private static String validateRequiredString(String value, int maxLength, AiCallRecordSanitizer sanitizer) {
        String normalized = validateOptionalString(value, maxLength, sanitizer);
        if (normalized == null) {
            throw validationFailure();
        }
        return normalized;
    }

    private static String validateOptionalString(String value, int maxLength, AiCallRecordSanitizer sanitizer) {
        if (value == null) {
            return null;
        }
        String normalized = value.trim();
        if (normalized.isEmpty() || normalized.length() > maxLength || sanitizer.containsSensitiveData(normalized)) {
            throw validationFailure();
        }
        return normalized;
    }

    private static String validateFingerprint(String value, AiCallRecordSanitizer sanitizer) {
        return validateOptionalString(value, 128, sanitizer);
    }

    private static Integer validateNonNegative(Integer value) {
        if (value != null && value < 0) {
            throw validationFailure();
        }
        return value;
    }

    private static Long validateNonNegative(Long value) {
        if (value != null && value < 0) {
            throw validationFailure();
        }
        return value;
    }

    private static BusinessException validationFailure() {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, "AI call record input is invalid");
    }
}
