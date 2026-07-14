package com.example.courselingo.task.progress;

import java.time.Instant;

public record TaskProgressSnapshot(
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

    public TaskProgressSnapshot(
        String taskId,
        String status,
        Integer progressPercent,
        String currentStage,
        String errorCode,
        String errorMessage,
        Instant updatedAt
    ) {
        this(taskId, status, progressPercent, currentStage, errorCode, errorMessage, updatedAt, null, null, null, null);
    }
}
