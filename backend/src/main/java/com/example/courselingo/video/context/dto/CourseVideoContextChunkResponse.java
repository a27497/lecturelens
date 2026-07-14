package com.example.courselingo.video.context.dto;

import java.util.List;

public record CourseVideoContextChunkResponse(
    Integer chunkIndex,
    Long startMillis,
    Long endMillis,
    String timeText,
    String summary,
    List<String> keywords,
    String sourceTextPreview,
    String translatedTextPreview,
    List<CourseVideoContextEvidenceItem> evidence
) {
}
