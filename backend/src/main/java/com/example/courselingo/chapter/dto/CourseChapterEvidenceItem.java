package com.example.courselingo.chapter.dto;

public record CourseChapterEvidenceItem(
    int index,
    long startTimeMillis,
    long endTimeMillis,
    String timeText,
    String text
) {
}
