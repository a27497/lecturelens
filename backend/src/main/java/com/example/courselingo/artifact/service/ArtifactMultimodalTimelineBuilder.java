package com.example.courselingo.artifact.service;

import com.example.courselingo.fusion.VideoSegment;
import com.example.courselingo.fusion.VideoSegmentEvidence;
import com.example.courselingo.fusion.VideoSegmentSourceStatus;
import com.example.courselingo.vision.ocr.OcrTextQualityEvaluator;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.Comparator;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import org.springframework.stereotype.Component;

@Component
public class ArtifactMultimodalTimelineBuilder {

    private static final int MAX_TIMELINE_ITEMS = 240;
    private static final TypeReference<List<String>> STRING_LIST_TYPE = new TypeReference<>() {
    };

    private final ObjectMapper objectMapper;

    public ArtifactMultimodalTimelineBuilder(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public List<ArtifactMultimodalTimelineItem> build(List<VideoSegment> segments) {
        if (segments == null || segments.isEmpty()) {
            return List.of();
        }
        Map<TimelineKey, ArtifactMultimodalTimelineItem> unique = new LinkedHashMap<>();
        segments.stream()
            .filter(Objects::nonNull)
            .sorted(Comparator
                .comparing(VideoSegment::getStartMillis, Comparator.nullsLast(Long::compareTo))
                .thenComparing(VideoSegment::getSegmentIndex, Comparator.nullsLast(Integer::compareTo))
            .thenComparing(VideoSegment::getId, Comparator.nullsLast(Long::compareTo)))
            .map(this::toItem)
            .filter(this::hasEvidence)
            .forEach(item -> unique.putIfAbsent(new TimelineKey(
                item.startMillis(),
                item.endMillis(),
                item.asrText(),
                item.translatedText(),
                item.ocrText(),
                item.visualSummary(),
                item.fusedSummary()
            ), item));
        return unique.values().stream().limit(MAX_TIMELINE_ITEMS).toList();
    }

    private ArtifactMultimodalTimelineItem toItem(VideoSegment segment) {
        long start = Math.max(0L, segment.getStartMillis() == null ? 0L : segment.getStartMillis());
        long end = Math.max(start, segment.getEndMillis() == null ? start : segment.getEndMillis());
        VideoSegmentEvidence evidence = parse(segment.getEvidenceJson(), VideoSegmentEvidence.class, null);
        VideoSegmentSourceStatus sourceStatus = parse(
            segment.getSourceStatusJson(),
            VideoSegmentSourceStatus.class,
            VideoSegmentSourceStatus.empty()
        );
        String persistedOcr = clean(segment.getOcrText());
        boolean usefulOcr = OcrTextQualityEvaluator.isUseful(persistedOcr, null);
        String fusedSummary = clean(segment.getFusedSummary());
        return new ArtifactMultimodalTimelineItem(
            segment.getSegmentIndex(),
            start,
            end,
            firstNonBlank(segment.getTimeText(), formatRange(start, end)),
            clean(segment.getAsrText()),
            clean(segment.getTranslatedText()),
            usefulOcr ? persistedOcr : "",
            clean(segment.getVisualSummary()),
            usefulOcr ? fusedSummary : clean(OcrTextQualityEvaluator.withoutOcrEvidenceClause(fusedSummary)),
            parseStrings(segment.getKeywordsJson()),
            evidence == null ? List.of() : evidence.keyframeIds(),
            sourceStatus,
            segment.getConfidence()
        );
    }

    private boolean hasEvidence(ArtifactMultimodalTimelineItem item) {
        return !item.asrText().isBlank()
            || !item.translatedText().isBlank()
            || !item.ocrText().isBlank()
            || !item.visualSummary().isBlank()
            || !item.fusedSummary().isBlank()
            || !item.keywords().isEmpty()
            || !item.evidenceKeyframeIds().isEmpty();
    }

    private List<String> parseStrings(String json) {
        try {
            List<String> values = json == null || json.isBlank()
                ? List.of()
                : objectMapper.readValue(json, STRING_LIST_TYPE);
            return values == null ? List.of() : values.stream().map(ArtifactMultimodalTimelineBuilder::clean)
                .filter(value -> !value.isBlank()).distinct().toList();
        } catch (Exception ignored) {
            return List.of();
        }
    }

    private <T> T parse(String json, Class<T> type, T fallback) {
        try {
            return json == null || json.isBlank() ? fallback : objectMapper.readValue(json, type);
        } catch (Exception ignored) {
            return fallback;
        }
    }

    private static String clean(String value) {
        return value == null ? "" : value.replaceAll("\\s+", " ").strip();
    }

    private static String firstNonBlank(String first, String fallback) {
        return first == null || first.isBlank() ? fallback : clean(first);
    }

    private static String formatRange(long start, long end) {
        return formatTime(start) + " - " + formatTime(end);
    }

    private static String formatTime(long millis) {
        long totalSeconds = millis / 1000L;
        return "%02d:%02d:%02d".formatted(
            totalSeconds / 3600L,
            (totalSeconds % 3600L) / 60L,
            totalSeconds % 60L
        );
    }

    private record TimelineKey(
        long startMillis,
        long endMillis,
        String asrText,
        String translatedText,
        String ocrText,
        String visualSummary,
        String fusedSummary
    ) {
    }
}
