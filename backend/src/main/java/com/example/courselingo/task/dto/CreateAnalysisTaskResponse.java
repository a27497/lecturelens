package com.example.courselingo.task.dto;

public record CreateAnalysisTaskResponse(
    String taskId,
    String uploadId,
    String status,
    String targetLanguage
) {
}
