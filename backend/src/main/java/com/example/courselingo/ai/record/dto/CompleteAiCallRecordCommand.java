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
    String responseFingerprint
) {
}
