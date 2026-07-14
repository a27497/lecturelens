package com.example.courselingo.ai.record.service;

import com.example.courselingo.ai.record.domain.AiCallStage;
import com.example.courselingo.ai.record.domain.AiCallType;

record ValidatedStartAiCallRecordCommand(
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
