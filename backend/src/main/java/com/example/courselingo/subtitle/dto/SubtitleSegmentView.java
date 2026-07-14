package com.example.courselingo.subtitle.dto;

import java.time.LocalDateTime;

public record SubtitleSegmentView(
    String taskId,
    int segmentIndex,
    long startMillis,
    long endMillis,
    String language,
    String text,
    String provider,
    LocalDateTime createdAt,
    LocalDateTime updatedAt
) {
}
