package com.example.courselingo.ai.record.service;

record ValidatedCompleteAiCallRecordCommand(
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
