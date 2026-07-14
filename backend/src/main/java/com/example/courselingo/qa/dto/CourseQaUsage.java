package com.example.courselingo.qa.dto;

public record CourseQaUsage(
    String provider,
    String model,
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    Long durationMillis
) {
}
