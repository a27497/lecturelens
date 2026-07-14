package com.example.courselingo.video.context.dto;

public record CourseVideoContextEvidenceItem(
    String sourceType,
    Integer segmentIndex,
    Long startMillis,
    Long endMillis,
    String timeText,
    String textPreview,
    String translatedPreview
) {
}
