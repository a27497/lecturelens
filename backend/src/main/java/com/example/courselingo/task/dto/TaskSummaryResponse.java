package com.example.courselingo.task.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;

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
    Instant createdAt,
    Instant updatedAt,
    Instant startedAt,
    Instant finishedAt,
    /** Owner-only display name: the uploaded file name without its extension; null when unknown. */
    String courseName
) {
    public TaskSummaryResponse(String taskId, String uploadId, String targetLanguage, String status, Integer progressPercent,
                               String currentStage, String errorCode, String errorMessage, Integer retryCount,
                               Integer maxRetryCount, Instant createdAt, Instant updatedAt, Instant startedAt,
                               Instant finishedAt) {
        this(taskId, uploadId, targetLanguage, status, progressPercent, currentStage, errorCode, errorMessage,
            retryCount, maxRetryCount, createdAt, updatedAt, startedAt, finishedAt, null);
    }
}
