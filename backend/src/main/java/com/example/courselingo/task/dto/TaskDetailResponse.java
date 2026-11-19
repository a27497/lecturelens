package com.example.courselingo.task.dto;

import com.fasterxml.jackson.annotation.JsonInclude;
import java.time.Instant;

@JsonInclude(JsonInclude.Include.NON_NULL)
public record TaskDetailResponse(
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
    /** True when study, Q&A and the Agent are available (SUCCEEDED, or subtitles ready while RUNNING). */
    Boolean learningReady,
    /** Owner-only display name: the uploaded file name without its extension; null when unknown. */
    String courseName
) {
    public TaskDetailResponse(String taskId, String uploadId, String targetLanguage, String status, Integer progressPercent,
                              String currentStage, String errorCode, String errorMessage, Integer retryCount,
                              Integer maxRetryCount, Instant createdAt, Instant updatedAt, Instant startedAt,
                              Instant finishedAt, Boolean learningReady) {
        this(taskId, uploadId, targetLanguage, status, progressPercent, currentStage, errorCode, errorMessage,
            retryCount, maxRetryCount, createdAt, updatedAt, startedAt, finishedAt, learningReady, null);
    }

    public TaskDetailResponse(String taskId, String uploadId, String targetLanguage, String status, Integer progressPercent,
                              String currentStage, String errorCode, String errorMessage, Integer retryCount,
                              Integer maxRetryCount, Instant createdAt, Instant updatedAt, Instant startedAt,
                              Instant finishedAt) {
        this(taskId, uploadId, targetLanguage, status, progressPercent, currentStage, errorCode, errorMessage,
            retryCount, maxRetryCount, createdAt, updatedAt, startedAt, finishedAt, null, null);
    }
}
