package com.example.courselingo.task.dto;

public record TaskBatchDeleteResponse(
    int requestedCount,
    int deletedCount
) {
}
