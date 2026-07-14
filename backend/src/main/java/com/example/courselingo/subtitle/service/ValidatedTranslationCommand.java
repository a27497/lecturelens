package com.example.courselingo.subtitle.service;

record ValidatedTranslationCommand(
    String taskId,
    Long userId,
    String sourceLanguage,
    String targetLanguage,
    String requestId
) {
}
