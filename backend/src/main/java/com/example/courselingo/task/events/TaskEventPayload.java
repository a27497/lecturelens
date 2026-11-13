package com.example.courselingo.task.events;

import java.time.Instant;

public record TaskEventPayload(
    String taskId,
    String status,
    Integer progressPercent,
    String currentStage,
    String errorCode,
    String errorMessage,
    Instant updatedAt,
    Integer completedChunks,
    Integer totalChunks,
    Integer currentChunkIndex,
    String stepDetail,
    /** True when study, Q&A and the Agent are available (SUCCEEDED, or subtitles ready while RUNNING). */
    Boolean learningReady
) {

    public TaskEventPayload(
        String taskId,
        String status,
        Integer progressPercent,
        String currentStage,
        String errorCode,
        String errorMessage,
        Instant updatedAt,
        Integer completedChunks,
        Integer totalChunks,
        Integer currentChunkIndex,
        String stepDetail
    ) {
        this(taskId, status, progressPercent, currentStage, errorCode, errorMessage, updatedAt,
            completedChunks, totalChunks, currentChunkIndex, stepDetail, null);
    }

    public TaskEventPayload(
        String taskId,
        String status,
        Integer progressPercent,
        String currentStage,
        String errorCode,
        String errorMessage,
        Instant updatedAt
    ) {
        this(taskId, status, progressPercent, currentStage, errorCode, errorMessage, updatedAt, null, null, null, null, null);
    }
}
