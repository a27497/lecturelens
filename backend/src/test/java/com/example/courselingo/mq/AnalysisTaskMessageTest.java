package com.example.courselingo.mq;

import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Instant;
import org.junit.jupiter.api.Test;

class AnalysisTaskMessageTest {

    @Test
    void validatesRequiredFields() {
        assertInvalid(message(null, "up_1", 1L, "zh-CN", "req_1", "trace_1", Instant.parse("2026-06-27T10:00:00Z")));
        assertInvalid(message("task_1", null, 1L, "zh-CN", "req_1", "trace_1", Instant.parse("2026-06-27T10:00:00Z")));
        assertInvalid(message("task_1", "up_1", null, "zh-CN", "req_1", "trace_1", Instant.parse("2026-06-27T10:00:00Z")));
        assertInvalid(message("task_1", "up_1", 1L, null, "req_1", "trace_1", Instant.parse("2026-06-27T10:00:00Z")));
        assertInvalid(message("task_1", "up_1", 1L, "zh-CN", null, "trace_1", Instant.parse("2026-06-27T10:00:00Z")));
        assertInvalid(message("task_1", "up_1", 1L, "zh-CN", "req_1", null, Instant.parse("2026-06-27T10:00:00Z")));
        assertInvalid(message("task_1", "up_1", 1L, "zh-CN", "req_1", "trace_1", null));
    }

    private static void assertInvalid(AnalysisTaskMessage message) {
        assertThatThrownBy(message::validate)
            .isInstanceOf(BusinessException.class)
            .extracting("errorCode")
            .isEqualTo(ErrorCode.COMMON_VALIDATION_FAILED);
    }

    private static AnalysisTaskMessage message(
        String taskId,
        String uploadId,
        Long userId,
        String targetLanguage,
        String requestId,
        String traceId,
        Instant createdAt
    ) {
        return new AnalysisTaskMessage(taskId, uploadId, userId, targetLanguage, requestId, traceId, createdAt);
    }
}
