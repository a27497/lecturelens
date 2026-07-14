package com.example.courselingo.chapter.dto;

import java.util.List;

public record CourseChapterResponse(
    Long id,
    int chapterIndex,
    String title,
    String summary,
    List<String> keywords,
    long startTimeMillis,
    long endTimeMillis,
    String timeText,
    List<CourseChapterEvidenceItem> evidence,
    CourseChapterUsage usage
) {
}
