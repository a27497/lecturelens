package com.example.courselingo.ai.record.dto;

import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;

public record StartAiCallRecordCommand(
    String taskId,
    Long userId,
    AiCallType callType,
    AiCallStage stage,
    String provider,
    String model,
    String requestFingerprint,
    Integer inputUnits
) {
}
