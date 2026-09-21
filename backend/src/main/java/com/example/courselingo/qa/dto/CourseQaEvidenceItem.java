package com.example.courselingo.qa.dto;

public record CourseQaEvidenceItem(
    String sourceType,
    String sourceId,
    Long startTimeMillis,
    Long endTimeMillis,
    String timeText,
    String snippet,
    String translatedSnippet,
    Double confidence,
    String evidenceId,
    Long revision
) {
    public CourseQaEvidenceItem(String sourceType, String sourceId, Long startTimeMillis, Long endTimeMillis,
                                String timeText, String snippet, String translatedSnippet, Double confidence) {
        this(sourceType, sourceId, startTimeMillis, endTimeMillis, timeText, snippet, translatedSnippet, confidence, null, null);
    }
}
