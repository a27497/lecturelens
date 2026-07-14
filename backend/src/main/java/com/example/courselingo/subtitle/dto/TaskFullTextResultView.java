package com.example.courselingo.subtitle.dto;

import java.time.LocalDateTime;

public record TaskFullTextResultView(
    String taskId,
    String sourceLanguage,
    String targetLanguage,
    String sourceFullText,
    String translatedFullText,
    String provider,
    LocalDateTime createdAt,
    LocalDateTime updatedAt
) {
}
