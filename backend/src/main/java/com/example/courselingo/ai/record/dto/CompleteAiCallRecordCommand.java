package com.example.courselingo.ai.record.dto;

public record CompleteAiCallRecordCommand(
    Long recordId,
    String taskId,
    Long userId,
    Long durationMillis,
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    Integer inputUnits,
    Integer outputUnits,
    String requestFingerprint,
    String responseFingerprint,
    Long providerDurationMillis,
    Integer batchCount,
    Integer retryCount
) {

    public CompleteAiCallRecordCommand(
        Long recordId,
        String taskId,
        Long userId,
        Long durationMillis,
        Integer promptTokens,
        Integer completionTokens,
        Integer totalTokens,
        Integer inputUnits,
        Integer outputUnits,
        String requestFingerprint,
        String responseFingerprint
    ) {
        this(
            recordId,
            taskId,
            userId,
            durationMillis,
            promptTokens,
            completionTokens,
            totalTokens,
            inputUnits,
            outputUnits,
            requestFingerprint,
            responseFingerprint,
            null,
            null,
            null
        );
    }
}
