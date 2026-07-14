package com.example.courselingo.task.runner;

import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import com.example.courselingo.ai.record.service.AiCallRecordSanitizer;

record PipelineAiCallRecord(
    AiCallType callType,
    AiCallStage stage,
    String provider,
    String model,
    boolean success,
    Long durationMillis,
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    Integer inputUnits,
    Integer outputUnits,
    String errorCode,
    String errorMessage,
    Boolean retryable,
    String requestFingerprint,
    String responseFingerprint
) {

    private static final AiCallRecordSanitizer SANITIZER = new AiCallRecordSanitizer();

    static PipelineAiCallRecord succeeded(
        AiCallType callType,
        AiCallStage stage,
        String provider,
        String model,
        Long durationMillis,
        Integer promptTokens,
        Integer completionTokens,
        Integer totalTokens,
        Integer inputUnits,
        Integer outputUnits,
        String requestFingerprint,
        String responseFingerprint
    ) {
        return new PipelineAiCallRecord(
            callType,
            stage,
            safeProvider(provider, callType, stage),
            safeOptional(model),
            true,
            nonNegative(durationMillis),
            nonNegative(promptTokens),
            nonNegative(completionTokens),
            nonNegative(totalTokens),
            nonNegative(inputUnits),
            nonNegative(outputUnits),
            null,
            null,
            null,
            safeOptional(requestFingerprint),
            safeOptional(responseFingerprint)
        );
    }

    static PipelineAiCallRecord failed(
        AiCallType callType,
        AiCallStage stage,
        String provider,
        String model,
        Long durationMillis,
        String errorCode,
        String errorMessage,
        Boolean retryable,
        String requestFingerprint,
        String responseFingerprint
    ) {
        return new PipelineAiCallRecord(
            callType,
            stage,
            safeProvider(provider, callType, stage),
            safeOptional(model),
            false,
            nonNegative(durationMillis),
            null,
            null,
            null,
            null,
            null,
            safeOptional(errorCode),
            SANITIZER.sanitizeErrorMessage(errorMessage),
            retryable,
            safeOptional(requestFingerprint),
            safeOptional(responseFingerprint)
        );
    }

    @Override
    public String toString() {
        return "PipelineAiCallRecord{"
            + "callType=" + callType
            + ", stage=" + stage
            + ", provider=" + provider
            + ", model=" + model
            + ", success=" + success
            + ", durationMillis=" + durationMillis
            + ", promptTokens=" + promptTokens
            + ", completionTokens=" + completionTokens
            + ", totalTokens=" + totalTokens
            + ", inputUnits=" + inputUnits
            + ", outputUnits=" + outputUnits
            + ", errorCode=" + errorCode
            + ", errorMessage=[redacted]"
            + '}';
    }

    private static String safeProvider(String provider, AiCallType callType, AiCallStage stage) {
        String fallback = switch (callType) {
            case ASR -> "asr-provider";
            case LLM -> stage == AiCallStage.LEARNING_PACKAGE
                ? "learning-package-service"
                : "subtitle-translation-service";
        };
        String normalized = safeOptional(provider);
        return normalized == null ? fallback : normalized;
    }

    private static String safeOptional(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String normalized = value.strip();
        return SANITIZER.containsSensitiveData(normalized) ? null : normalized;
    }

    private static Long nonNegative(Long value) {
        if (value == null || value < 0) {
            return null;
        }
        return value;
    }

    private static Integer nonNegative(Integer value) {
        if (value == null || value < 0) {
            return null;
        }
        return value;
    }
}
