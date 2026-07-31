package com.example.courselingo.result.dto;

import java.time.LocalDateTime;

public record ResultAiCallRecord(
    Long id,
    String callType,
    String stage,
    String provider,
    String model,
    String status,
    Long durationMillis,
    Long providerDurationMillis,
    Integer batchCount,
    Integer retryCount,
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    Integer inputUnits,
    Integer outputUnits,
    LocalDateTime createdAt
) {

    public ResultAiCallRecord(
        Long id,
        String callType,
        String stage,
        String provider,
        String model,
        String status,
        Long durationMillis,
        Long providerDurationMillis,
        Integer batchCount,
        Integer retryCount,
        Integer promptTokens,
        Integer completionTokens,
        Integer totalTokens,
        LocalDateTime createdAt
    ) {
        this(id, callType, stage, provider, model, status, durationMillis, providerDurationMillis,
            batchCount, retryCount, promptTokens, completionTokens, totalTokens, null, null, createdAt);
    }

    public ResultAiCallRecord(
        Long id,
        String callType,
        String stage,
        String provider,
        String model,
        String status,
        Long durationMillis,
        Integer promptTokens,
        Integer completionTokens,
        Integer totalTokens,
        LocalDateTime createdAt
    ) {
        this(
            id,
            callType,
            stage,
            provider,
            model,
            status,
            durationMillis,
            null,
            null,
            null,
            promptTokens,
            completionTokens,
            totalTokens,
            null,
            null,
            createdAt
        );
    }
}
