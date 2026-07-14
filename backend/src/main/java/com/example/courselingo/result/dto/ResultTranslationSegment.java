package com.example.courselingo.result.dto;

public record ResultTranslationSegment(
    int segmentIndex,
    long startMillis,
    long endMillis,
    String sourceLanguage,
    String targetLanguage,
    String translatedText
) {
}
