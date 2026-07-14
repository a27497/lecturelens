package com.example.courselingo.artifact.service;

import java.util.List;

public record JsonArtifactPayload(
    String schemaVersion,
    String taskId,
    String targetLanguage,
    List<SubtitleItem> subtitles,
    LearningPackageItem learningPackage
) {

    public record SubtitleItem(
        int index,
        long startMillis,
        long endMillis,
        String sourceText,
        String translatedText
    ) {
    }

    public record LearningPackageItem(
        String title,
        String summary,
        List<KeyPointItem> keyPoints,
        List<GlossaryItem> glossary,
        List<QaItem> qa
    ) {
    }

    public record KeyPointItem(
        int index,
        String text
    ) {
    }

    public record GlossaryItem(
        String term,
        String definition,
        String translation
    ) {
    }

    public record QaItem(
        String question,
        String answer
    ) {
    }
}
