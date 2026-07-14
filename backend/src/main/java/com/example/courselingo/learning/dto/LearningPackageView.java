package com.example.courselingo.learning.dto;

import java.time.LocalDateTime;

public record LearningPackageView(
    String taskId,
    String sourceLanguage,
    String targetLanguage,
    String title,
    String summary,
    String keyPointsJson,
    String glossaryJson,
    String qaJson,
    String provider,
    String schemaVersion,
    LocalDateTime createdAt,
    LocalDateTime updatedAt
) {
}
