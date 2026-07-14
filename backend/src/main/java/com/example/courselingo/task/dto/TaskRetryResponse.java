package com.example.courselingo.task.dto;

public record TaskRetryResponse(
    String originalTaskId,
    String newTaskId,
    String status,
    String message
) {
}
