package com.example.courselingo.task.dto;

import java.util.List;

public record TaskListResponse(
    List<TaskSummaryResponse> items,
    int page,
    int pageSize,
    long total
) {
}
