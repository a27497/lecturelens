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
    String responseFingerprint,
    Integer promptTokens,Integer completionTokens,Integer totalTokens
) {
    public FailAiCallRecordCommand(Long recordId,String taskId,Long userId,Long durationMillis,String errorCode,String errorMessage,
        Boolean retryable,String requestFingerprint,String responseFingerprint) {
        this(recordId,taskId,userId,durationMillis,errorCode,errorMessage,retryable,requestFingerprint,responseFingerprint,null,null,null);
    }
}
