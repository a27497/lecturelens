package com.example.courselingo.subtitle.service;

record ValidatedTranslationScope(
    String taskId,
    Long userId,
    String targetLanguage
) {
}
