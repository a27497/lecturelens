package com.example.courselingo.result.dto;

public record ResultSubtitleSegment(
    int segmentIndex,
    long startMillis,
    long endMillis,
    String language,
    String sourceText
) {
}
