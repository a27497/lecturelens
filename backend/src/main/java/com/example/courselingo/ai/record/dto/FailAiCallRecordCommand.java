package com.example.courselingo.ai.record.dto;

public record FailAiCallRecordCommand(
    Long recordId,
    String taskId,
    Long userId,
    Long durationMillis,
    String errorCode,
    String errorMessage,
    Boolean retryable,
    String requestFingerprint,
    String responseFingerprint
) {
}
