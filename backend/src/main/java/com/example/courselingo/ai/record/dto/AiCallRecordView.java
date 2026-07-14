package com.example.courselingo.ai.record.dto;

import com.example.courselingo.ai.record.domain.AiCallRecordStatus;
import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;
import java.time.LocalDateTime;

public record AiCallRecordView(
    Long id,
    String taskId,
    AiCallType callType,
    AiCallStage stage,
    String provider,
    String model,
    AiCallRecordStatus status,
    LocalDateTime startedAt,
    LocalDateTime finishedAt,
    Long durationMillis,
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    Integer inputUnits,
    Integer outputUnits,
    String requestFingerprint,
    String responseFingerprint,
    String errorCode,
    String errorMessage,
    Boolean retryable,
    LocalDateTime createdAt,
    LocalDateTime updatedAt
) {
}
