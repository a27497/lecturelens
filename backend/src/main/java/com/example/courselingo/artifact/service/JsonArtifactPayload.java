package com.example.courselingo.artifact.service;

import java.util.List;

public record JsonArtifactPayload(
    String schemaVersion,
    String taskId,
    String targetLanguage,
    List<SubtitleItem> subtitles,
    LearningPackageItem learningPackage,
    List<MultimodalTimelineItem> multimodalTimeline
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

    public record MultimodalTimelineItem(
        Integer segmentIndex,
        long startMillis,
        long endMillis,
        String timeText,
        String asrText,
        String translatedText,
        String ocrText,
        String visualSummary,
        String fusedSummary,
        List<String> keywords,
        List<Long> evidenceKeyframeIds,
        SourceStatusItem sourceStatus,
        Double confidence
    ) {
    }

    public record SourceStatusItem(
        java.util.Map<String, String> sources,
        java.util.Map<String, Double> confidenceComponents,
        boolean degraded
    ) {
    }
}
