package com.example.courselingo.task.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.LocalDateTime;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record TaskSummaryResponse(
    String taskId,
    String uploadId,
    String targetLanguage,
    String status,
    Integer progressPercent,
    String currentStage,
    String errorCode,
    String errorMessage,
    Integer retryCount,
    Integer maxRetryCount,
    LocalDateTime createdAt,
    LocalDateTime updatedAt,
    LocalDateTime startedAt,
    LocalDateTime finishedAt
) {
}
