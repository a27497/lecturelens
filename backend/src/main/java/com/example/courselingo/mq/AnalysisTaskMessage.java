package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Instant;

public record AnalysisTaskMessage(
    String taskId,
    String uploadId,
    Long userId,
    String targetLanguage,
    String requestId,
    String traceId,
    Instant createdAt
) {

    public void validate() {
        if (isBlank(taskId)
            || isBlank(uploadId)
            || userId == null
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
