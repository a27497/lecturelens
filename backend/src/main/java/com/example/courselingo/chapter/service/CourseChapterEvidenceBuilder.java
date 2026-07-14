package com.example.courselingo.chapter.service;

import com.example.courselingo.chapter.dto.CourseChapterEvidenceItem;
import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.mapper.VideoSegmentMapper;
import com.example.courselingo.learning.domain.LearningPackage;
import com.example.courselingo.learning.mapper.LearningPackageMapper;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Service;

@Service
public class CourseChapterEvidenceBuilder {

    private final SubtitleSegmentMapper subtitleSegmentMapper;
    private final SubtitleTranslationSegmentMapper translationSegmentMapper;
    private final VideoSegmentMapper videoSegmentMapper;
    private final LearningPackageMapper learningPackageMapper;
    private final CourseChapterProperties properties;

    public CourseChapterEvidenceBuilder(
        SubtitleSegmentMapper subtitleSegmentMapper,
        SubtitleTranslationSegmentMapper translationSegmentMapper,
        VideoSegmentMapper videoSegmentMapper,
        LearningPackageMapper learningPackageMapper,
        CourseChapterProperties properties
    ) {
        this.subtitleSegmentMapper = Objects.requireNonNull(subtitleSegmentMapper, "subtitleSegmentMapper is required");
        this.translationSegmentMapper = Objects.requireNonNull(translationSegmentMapper, "translationSegmentMapper is required");
        this.videoSegmentMapper = Objects.requireNonNull(videoSegmentMapper, "videoSegmentMapper is required");
        this.learningPackageMapper = Objects.requireNonNull(learningPackageMapper, "learningPackageMapper is required");
        this.properties = properties == null ? new CourseChapterProperties() : properties;
    }

    public CourseChapterEvidenceBundle build(String taskId, Long userId, String targetLanguage) {
        List<SubtitleSegment> subtitles = subtitleSegmentMapper.selectByTaskIdAndUserId(taskId, userId);
        Map<Integer, SubtitleTranslationSegment> translations = translationMap(
            translationSegmentMapper.selectByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage)
        );
        List<VideoSegment> videoSegments = videoSegmentMapper.selectByTaskIdAndUserId(taskId, userId);
        List<TextUnit> units = new ArrayList<>();
        for (SubtitleSegment subtitle : subtitles) {
            String text = cleanText(subtitle.getText());
            String translated = translations.containsKey(subtitle.getSegmentIndex())
                ? cleanText(translations.get(subtitle.getSegmentIndex()).getTranslatedText())
                : "";
            String combined = combineSubtitleText(text, translated);
            if (!combined.isBlank()) {
                units.add(new TextUnit(start(subtitle.getStartMillis()), end(subtitle.getStartMillis(), subtitle.getEndMillis()), combined));
            }
        }
        for (VideoSegment segment : videoSegments) {
            String asrText = cleanText(segment.getAsrText());
            if (!asrText.isBlank()) {
                units.add(new TextUnit(start(segment.getStartMillis()), end(segment.getStartMillis(), segment.getEndMillis()), "本段语音原文：" + asrText));
            }
        }
        units = units.stream()
            .filter(unit -> unit.endMillis() > unit.startMillis())
            .sorted(Comparator.comparingLong(TextUnit::startMillis).thenComparingLong(TextUnit::endMillis))
            .toList();
        return new CourseChapterEvidenceBundle(toWindows(units), globalContext(taskId, userId, targetLanguage));
    }

    private List<CourseChapterEvidenceItem> toWindows(List<TextUnit> units) {
        if (units.isEmpty()) {
            return List.of();
        }
        long windowMillis = properties.getWindowSeconds() * 1000L;
        long firstStart = Math.max(0L, units.getFirst().startMillis());
        long lastEnd = units.stream().mapToLong(TextUnit::endMillis).max().orElse(firstStart);
        List<CourseChapterEvidenceItem> evidence = new ArrayList<>();
        int index = 0;
        for (long start = firstStart; start < lastEnd && evidence.size() < properties.getMaxEvidenceItems(); start += windowMillis) {
            long windowStart = start;
            long windowEnd = Math.min(windowStart + windowMillis, lastEnd);
            String text = units.stream()
                .filter(unit -> unit.endMillis() > windowStart && unit.startMillis() < windowEnd)
                .map(TextUnit::text)
                .reduce("", (left, right) -> appendLimited(left, right, properties.getMaxCharsPerWindow()));
            text = cleanText(text);
            if (!text.isBlank()) {
                evidence.add(new CourseChapterEvidenceItem(index++, windowStart, windowEnd, formatRange(windowStart, windowEnd), text));
            }
        }
        return evidence;
    }

    private String globalContext(String taskId, Long userId, String targetLanguage) {
        LearningPackage learningPackage = learningPackageMapper.selectByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage);
        if (learningPackage == null) {
            return "";
        }
        return truncate(cleanText(String.join(" ", cleanText(learningPackage.getSummary()), cleanText(learningPackage.getGlossaryJson()))), 1600);
    }

    private static Map<Integer, SubtitleTranslationSegment> translationMap(List<SubtitleTranslationSegment> rows) {
        Map<Integer, SubtitleTranslationSegment> result = new LinkedHashMap<>();
        for (SubtitleTranslationSegment row : rows == null ? List.<SubtitleTranslationSegment>of() : rows) {
            if (row.getSegmentIndex() != null) {
                result.putIfAbsent(row.getSegmentIndex(), row);
            }
        }
        return result;
    }

    private static String combineSubtitleText(String source, String translated) {
        if (!translated.isBlank() && !source.isBlank()) {
            return "字幕译文：" + translated + " 原文：" + source;
        }
        if (!translated.isBlank()) {
            return "字幕译文：" + translated;
        }
        return source.isBlank() ? "" : "本段语音原文：" + source;
    }

    private static String appendLimited(String current, String next, int limit) {
        String cleanedNext = cleanText(next);
        if (cleanedNext.isBlank() || current.length() >= limit) {
            return current;
        }
        String candidate = current.isBlank() ? cleanedNext : current + " " + cleanedNext;
        return truncate(candidate, limit);
    }

    private static long start(Long value) {
        return Math.max(0L, value == null ? 0L : value);
    }

    private static long end(Long start, Long end) {
        long safeStart = start(start);
        long safeEnd = end == null ? safeStart + 1000L : Math.max(safeStart + 1L, end);
        return safeEnd;
    }

    private static String cleanText(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    private static String truncate(String value, int limit) {
        String cleaned = cleanText(value);
        return cleaned.length() <= limit ? cleaned : cleaned.substring(0, limit);
    }

    private static String formatRange(long start, long end) {
        return formatTime(start) + " - " + formatTime(end);
    }

    private static String formatTime(long millis) {
        long totalSeconds = Math.max(0L, millis / 1000L);
        long hours = totalSeconds / 3600L;
        long minutes = (totalSeconds % 3600L) / 60L;
        long seconds = totalSeconds % 60L;
        return "%02d:%02d:%02d".formatted(hours, minutes, seconds);
    }

    private record TextUnit(long startMillis, long endMillis, String text) {
    }
}
