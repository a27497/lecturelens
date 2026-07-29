package com.example.courselingo.vision.analysis;

import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import com.example.courselingo.subtitle.mapper.SubtitleSegmentMapper;
import com.example.courselingo.subtitle.mapper.SubtitleTranslationSegmentMapper;
import java.util.List;
import java.util.Objects;
import java.util.stream.Collectors;
import org.springframework.stereotype.Service;

@Service
public class VisionPromptContextBuilder {

    private static final long CONTEXT_RADIUS_MILLIS = 30_000L;
    private static final int MAX_CONTEXT_CHARS = 6_000;

    private final SubtitleSegmentMapper subtitleMapper;
    private final SubtitleTranslationSegmentMapper translationMapper;

    public VisionPromptContextBuilder(
        SubtitleSegmentMapper subtitleMapper,
        SubtitleTranslationSegmentMapper translationMapper
    ) {
        this.subtitleMapper = Objects.requireNonNull(subtitleMapper, "subtitleMapper is required");
        this.translationMapper = Objects.requireNonNull(translationMapper, "translationMapper is required");
    }

    public String build(String taskId, Long userId, long timestampMillis, String targetLanguage) {
        long start = Math.max(0L, timestampMillis - CONTEXT_RADIUS_MILLIS);
        long end = timestampMillis + CONTEXT_RADIUS_MILLIS;
        List<SubtitleSegment> subtitles = subtitleMapper.selectByTaskIdAndUserId(taskId, userId);
        List<SubtitleTranslationSegment> translations = targetLanguage == null || targetLanguage.isBlank()
            ? List.of()
            : translationMapper.selectByTaskIdUserIdAndTargetLanguage(taskId, userId, targetLanguage.strip());
        String asr = join(subtitles.stream()
            .filter(item -> overlaps(item.getStartMillis(), item.getEndMillis(), start, end))
            .map(SubtitleSegment::getText)
            .toList());
        String translated = join(translations.stream()
            .filter(item -> overlaps(item.getStartMillis(), item.getEndMillis(), start, end))
            .map(SubtitleTranslationSegment::getTranslatedText)
            .toList());
        return limit("Task language: " + clean(targetLanguage)
            + "\nASR [-30s,+30s]: " + asr
            + "\nTranslation [-30s,+30s]: " + translated);
    }

    private static boolean overlaps(Long itemStart, Long itemEnd, long start, long end) {
        long safeStart = itemStart == null ? 0L : Math.max(0L, itemStart);
        long safeEnd = itemEnd == null ? safeStart : Math.max(safeStart, itemEnd);
        return safeEnd >= start && safeStart <= end;
    }

    private static String join(List<String> values) {
        return values == null ? "" : values.stream()
            .map(VisionPromptContextBuilder::clean)
            .filter(value -> !value.isBlank())
            .distinct()
            .collect(Collectors.joining(" "));
    }

    private static String clean(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    private static String limit(String value) {
        String cleaned = clean(value.replace('\n', ' '));
        return cleaned.length() <= MAX_CONTEXT_CHARS ? cleaned : cleaned.substring(0, MAX_CONTEXT_CHARS);
    }
}
