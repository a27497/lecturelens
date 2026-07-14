package com.example.courselingo.chapter.dto;

public record CourseChapterUsage(
    String provider,
    String model,
    Integer promptTokens,
    Integer completionTokens,
    Integer totalTokens,
    Long durationMillis
) {
}
