package com.example.courselingo.subtitle.service;

public record TranslateSubtitleCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId
) {
}
