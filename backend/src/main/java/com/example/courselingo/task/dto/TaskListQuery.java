package com.example.courselingo.task.dto;

public record TaskListQuery(
    String status,
    Integer page,
    Integer pageSize
) {
}
