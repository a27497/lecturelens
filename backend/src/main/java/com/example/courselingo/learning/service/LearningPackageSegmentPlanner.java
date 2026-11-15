package com.example.courselingo.learning.service;

import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

/**
 * Groups timed cues into chapter-sized windows. Cues are never split across chapters.
 * The default window matches course-chapter windows (240s) so materials and chapter
 * navigation share the same segmentation unit when persisted chapters are not yet available.
 */
final class LearningPackageSegmentPlanner {

    private LearningPackageSegmentPlanner() {
    }

    record Chapter(
        int chapterIndex,
        long startMillis,
        long endMillis,
        List<SubtitleSegment> sources,
        List<SubtitleTranslationSegment> translations
    ) {
        Chapter {
            sources = sources == null ? List.of() : List.copyOf(sources);
            translations = translations == null ? List.of() : List.copyOf(translations);
        }
    }

    static int windowMillis(LearningPackageProperties properties) {
        int seconds = properties == null ? 240 : properties.segmentWindowSeconds();
        return Math.max(60, Math.min(seconds, 600)) * 1_000;
    }

    static List<Chapter> plan(
        List<SubtitleSegment> sources,
        List<SubtitleTranslationSegment> translations,
        LearningPackageProperties properties
    ) {
        if (sources == null || sources.isEmpty()) {
            return List.of();
        }
        Map<Integer, SubtitleTranslationSegment> byIndex = translations == null
            ? Map.of()
            : translations.stream()
                .filter(Objects::nonNull)
                .filter(segment -> segment.getSegmentIndex() != null)
                .collect(Collectors.toMap(
                    SubtitleTranslationSegment::getSegmentIndex,
                    segment -> segment,
                    (first, ignored) -> first
                ));
        List<SubtitleSegment> ordered = sources.stream()
            .filter(Objects::nonNull)
            .sorted(Comparator
                .comparing(SubtitleSegment::getStartMillis, Comparator.nullsLast(Long::compareTo))
                .thenComparing(SubtitleSegment::getSegmentIndex, Comparator.nullsLast(Integer::compareTo)))
            .toList();
        int window = windowMillis(properties);
        List<Chapter> chapters = new ArrayList<>();
        List<SubtitleSegment> bucket = new ArrayList<>();
        long chapterStart = -1;
        for (SubtitleSegment cue : ordered) {
            long start = cueStart(cue);
            if (bucket.isEmpty()) {
                chapterStart = start;
                bucket.add(cue);
                continue;
            }
            if (start >= chapterStart + window) {
                chapters.add(close(chapters.size(), chapterStart, bucket, byIndex));
                bucket = new ArrayList<>();
                chapterStart = start;
            }
            bucket.add(cue);
        }
        if (!bucket.isEmpty()) {
            chapters.add(close(chapters.size(), chapterStart, bucket, byIndex));
        }
        return List.copyOf(chapters);
    }

    private static Chapter close(
        int chapterIndex,
        long chapterStart,
        List<SubtitleSegment> sources,
        Map<Integer, SubtitleTranslationSegment> byIndex
    ) {
        long end = sources.stream()
            .map(segment -> segment.getEndMillis() == null ? cueStart(segment) : segment.getEndMillis())
            .max(Long::compareTo)
            .orElse(chapterStart);
        List<SubtitleTranslationSegment> translated = sources.stream()
            .map(SubtitleSegment::getSegmentIndex)
            .map(byIndex::get)
            .filter(Objects::nonNull)
            .toList();
        return new Chapter(chapterIndex, chapterStart, Math.max(end, chapterStart), List.copyOf(sources), translated);
    }

    private static long cueStart(SubtitleSegment segment) {
        return segment.getStartMillis() == null ? 0L : Math.max(0L, segment.getStartMillis());
    }
}
