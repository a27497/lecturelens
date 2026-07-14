package com.example.courselingo.subtitle.service;

public interface SubtitleTranslationService {

    int translateTaskSubtitles(TranslateSubtitleCommand command);

    default SubtitleTranslationAiCallResult translateTaskSubtitlesWithAiCallRecord(
        TranslateSubtitleCommand command
    ) {
        int savedCount = translateTaskSubtitles(command);
        return new SubtitleTranslationAiCallResult(
            savedCount,
            "subtitle-translation-service",
            null,
            null,
            null,
            null,
            null,
            null,
            savedCount,
            null,
            null
        );
    }

    int deleteTranslations(String taskId, Long userId, String targetLanguage);
}
