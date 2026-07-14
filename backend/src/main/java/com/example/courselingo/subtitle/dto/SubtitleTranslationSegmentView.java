package com.example.courselingo.subtitle.dto;

import java.time.LocalDateTime;

public record SubtitleTranslationSegmentView(
    String taskId,
    int segmentIndex,
    long startMillis,
    long endMillis,
    String sourceLanguage,
    String targetLanguage,
    String translatedText,
    String provider,
    LocalDateTime createdAt,
    LocalDateTime updatedAt
) {
}
