package com.example.courselingo.qa.dto;

public record CourseQaEvidenceItem(
    String sourceType,
    String sourceId,
    Long startTimeMillis,
    Long endTimeMillis,
    String timeText,
    String snippet,
    String translatedSnippet,
    Double confidence
) {
}
