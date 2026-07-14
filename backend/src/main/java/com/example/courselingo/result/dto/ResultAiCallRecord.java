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
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    LocalDateTime createdAt
) {
}
