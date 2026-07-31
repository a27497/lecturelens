package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Instant;

public record AnalysisTaskMessage(
    String taskId,
    String uploadId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId,
    String traceId,
    Instant createdAt
) {

    public AnalysisTaskMessage {
        // Preserve compatibility with messages produced before source-language
        // selection existed. New producers always send the explicit user choice.
        if (isBlank(sourceLanguage)) {
            sourceLanguage = "auto";
        }
    }

    public AnalysisTaskMessage(
        String taskId,
        String uploadId,
        Long userId,
        String targetLanguage,
        String requestId,
        String traceId,
        Instant createdAt
    ) {
        this(taskId, uploadId, userId, "auto", targetLanguage, requestId, traceId, createdAt);
    }

    public void validate() {
        if (isBlank(taskId)
            || isBlank(uploadId)
            || userId == null
            || isBlank(sourceLanguage)
            || isBlank(targetLanguage)
            || isBlank(requestId)
            || isBlank(traceId)
            || createdAt == null) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
