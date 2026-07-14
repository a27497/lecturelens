package com.example.courselingo.ai.record.service;

record ValidatedFailAiCallRecordCommand(
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
