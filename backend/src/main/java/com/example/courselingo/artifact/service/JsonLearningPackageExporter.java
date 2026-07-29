package com.example.courselingo.artifact.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.GlossaryItem;
import com.example.courselingo.learning.dto.KeyPointItem;
import com.example.courselingo.learning.dto.LearningPackageView;
import com.example.courselingo.learning.dto.QaItem;
import com.example.courselingo.subtitle.dto.SubtitleSegmentView;
import com.example.courselingo.subtitle.dto.SubtitleTranslationSegmentView;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import org.springframework.stereotype.Component;

@Component
public class JsonLearningPackageExporter {

    private static final String SCHEMA_VERSION = "1.0";
    private static final TypeReference<List<KeyPointItem>> KEY_POINTS_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<List<GlossaryItem>> GLOSSARY_TYPE = new TypeReference<>() {
    };
    private static final TypeReference<List<QaItem>> QA_TYPE = new TypeReference<>() {
    };

    private final ObjectMapper objectMapper;

    public JsonLearningPackageExporter(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper;
    }

    public String export(
        String taskId,
        String targetLanguage,
        List<SubtitleSegmentView> sourceSubtitles,
        List<SubtitleTranslationSegmentView> translatedSubtitles,
        LearningPackageView learningPackage
    ) {
        return export(taskId, targetLanguage, sourceSubtitles, translatedSubtitles, learningPackage, List.of());
    }

    public String export(
        String taskId,
        String targetLanguage,
        List<SubtitleSegmentView> sourceSubtitles,
        List<SubtitleTranslationSegmentView> translatedSubtitles,
        LearningPackageView learningPackage,
        List<ArtifactMultimodalTimelineItem> multimodalTimeline
    ) {
        JsonArtifactPayload payload = payload(
            taskId,
            targetLanguage,
            sourceSubtitles,
            translatedSubtitles,
            learningPackage,
            multimodalTimeline
        );
        try {
            return objectMapper.writeValueAsString(payload);
        } catch (JsonProcessingException exception) {
            throw validationFailure("JSON artifact content is invalid");
        }
    }

    private JsonArtifactPayload payload(
        String taskId,
        String targetLanguage,
        List<SubtitleSegmentView> sourceSubtitles,
        List<SubtitleTranslationSegmentView> translatedSubtitles,
        LearningPackageView learningPackage,
        List<ArtifactMultimodalTimelineItem> multimodalTimeline
    ) {
        if (learningPackage == null) {
            throw validationFailure("JSON learning package is required");
        }
        List<JsonArtifactPayload.SubtitleItem> subtitleItems = subtitleItems(
            sourceSubtitles == null ? List.of() : sourceSubtitles,
            translatedSubtitles == null ? List.of() : translatedSubtitles
        );
        List<JsonArtifactPayload.MultimodalTimelineItem> timelineItems = timelineItems(
            multimodalTimeline,
            subtitleItems
        );
        if (subtitleItems.isEmpty() && timelineItems.isEmpty()) {
            throw validationFailure("JSON course evidence is required");
        }
        return new JsonArtifactPayload(
            SCHEMA_VERSION,
            validateText(taskId),
            validateText(targetLanguage),
            subtitleItems,
            learningPackageItem(learningPackage),
            timelineItems
        );
    }

    private List<JsonArtifactPayload.MultimodalTimelineItem> timelineItems(
        List<ArtifactMultimodalTimelineItem> timeline,
        List<JsonArtifactPayload.SubtitleItem> subtitles
    ) {
        List<JsonArtifactPayload.MultimodalTimelineItem> result = (timeline == null ? List.<ArtifactMultimodalTimelineItem>of() : timeline)
            .stream()
            .filter(java.util.Objects::nonNull)
            .sorted(Comparator
                .comparingLong(ArtifactMultimodalTimelineItem::startMillis)
                .thenComparing(item -> item.segmentIndex() == null ? Integer.MAX_VALUE : item.segmentIndex()))
            .map(this::timelineItem)
            .filter(this::hasTimelineEvidence)
            .toList();
        if (!result.isEmpty()) {
            return result;
        }
        return subtitles.stream()
            .map(item -> new JsonArtifactPayload.MultimodalTimelineItem(
                item.index(),
                item.startMillis(),
                item.endMillis(),
                formatRange(item.startMillis(), item.endMillis()),
                item.sourceText(),
                item.translatedText(),
                "",
                "",
                "",
                List.of(),
                List.of(),
                new JsonArtifactPayload.SourceStatusItem(
                    fallbackSourceStatus(item),
                    Map.of(),
                    false
                ),
                null
            ))
            .toList();
    }

    private static Map<String, String> fallbackSourceStatus(JsonArtifactPayload.SubtitleItem item) {
        Map<String, String> status = new java.util.LinkedHashMap<>();
        status.put("asr", "AVAILABLE");
        status.put("translation", item.translatedText().isBlank() ? "MISSING" : "AVAILABLE");
        status.put("visual", "MISSING");
        return java.util.Collections.unmodifiableMap(status);
    }

    private JsonArtifactPayload.MultimodalTimelineItem timelineItem(ArtifactMultimodalTimelineItem item) {
        com.example.courselingo.fusion.VideoSegmentSourceStatus sourceStatus = item.sourceStatus();
        return new JsonArtifactPayload.MultimodalTimelineItem(
            item.segmentIndex(),
            Math.max(0L, item.startMillis()),
            Math.max(Math.max(0L, item.startMillis()), item.endMillis()),
            optionalText(item.timeText()),
            optionalText(item.asrText()),
            optionalText(item.translatedText()),
            optionalText(item.ocrText()),
            optionalText(item.visualSummary()),
            optionalText(item.fusedSummary()),
            item.keywords().stream().map(this::optionalText).filter(value -> !value.isBlank()).distinct().toList(),
            item.evidenceKeyframeIds().stream().filter(java.util.Objects::nonNull).distinct().sorted().toList(),
            new JsonArtifactPayload.SourceStatusItem(
                sourceStatus.sources(),
                sourceStatus.confidenceComponents(),
                sourceStatus.degraded()
            ),
            item.confidence() == null || !Double.isFinite(item.confidence())
                ? null
                : Math.max(0.0d, Math.min(item.confidence(), 1.0d))
        );
    }

    private boolean hasTimelineEvidence(JsonArtifactPayload.MultimodalTimelineItem item) {
        return !item.asrText().isBlank()
            || !item.translatedText().isBlank()
            || !item.ocrText().isBlank()
            || !item.visualSummary().isBlank()
            || !item.fusedSummary().isBlank()
            || !item.keywords().isEmpty()
            || !item.evidenceKeyframeIds().isEmpty();
    }

    private static String formatRange(long startMillis, long endMillis) {
        return formatTime(startMillis) + " - " + formatTime(endMillis);
    }

    private static String formatTime(long millis) {
        long seconds = Math.max(0L, millis / 1000L);
        return "%02d:%02d:%02d".formatted(seconds / 3600L, (seconds % 3600L) / 60L, seconds % 60L);
    }

    private List<JsonArtifactPayload.SubtitleItem> subtitleItems(
        List<SubtitleSegmentView> sourceSubtitles,
        List<SubtitleTranslationSegmentView> translatedSubtitles
    ) {
        Map<Integer, SubtitleTranslationSegmentView> translationsByIndex = new HashMap<>();
        for (SubtitleTranslationSegmentView translation : translatedSubtitles) {
            if (translation == null || translationsByIndex.put(translation.segmentIndex(), translation) != null) {
                throw validationFailure("JSON subtitle segments are inconsistent");
            }
        }
        List<JsonArtifactPayload.SubtitleItem> items = new ArrayList<>();
        java.util.Set<Integer> seenSourceIndexes = new java.util.HashSet<>();
        for (SubtitleSegmentView source : sourceSubtitles.stream()
            .sorted(Comparator.comparingInt(SubtitleSegmentView::segmentIndex))
            .toList()) {
            if (source == null) {
                throw validationFailure("JSON subtitle segments are inconsistent");
            }
            seenSourceIndexes.add(source.segmentIndex());
            SubtitleTranslationSegmentView translation = translationsByIndex.get(source.segmentIndex());
            if (translation != null
                && (translation.startMillis() != source.startMillis()
                    || translation.endMillis() != source.endMillis())) {
                throw validationFailure("JSON subtitle segments are inconsistent");
            }
            if (source.startMillis() < 0 || source.endMillis() < source.startMillis()) {
                throw validationFailure("JSON subtitle time range is invalid");
            }
            items.add(new JsonArtifactPayload.SubtitleItem(
                source.segmentIndex(),
                source.startMillis(),
                source.endMillis(),
                validateText(source.text()),
                translation == null ? "" : validateText(translation.translatedText())
            ));
        }
        if (!seenSourceIndexes.containsAll(translationsByIndex.keySet())) {
            throw validationFailure("JSON subtitle segments are inconsistent");
        }
        return items;
    }

    private JsonArtifactPayload.LearningPackageItem learningPackageItem(LearningPackageView learningPackage) {
        List<KeyPointItem> keyPoints = readJson(learningPackage.keyPointsJson(), KEY_POINTS_TYPE);
        List<GlossaryItem> glossary = readJson(learningPackage.glossaryJson(), GLOSSARY_TYPE);
        List<QaItem> qa = readJson(learningPackage.qaJson(), QA_TYPE);
        if (keyPoints.isEmpty()) {
            throw validationFailure("JSON key points are required");
        }
        return new JsonArtifactPayload.LearningPackageItem(
            validateText(learningPackage.title()),
            validateText(learningPackage.summary()),
            keyPoints.stream()
                .sorted(Comparator.comparingInt(KeyPointItem::index))
                .map(item -> new JsonArtifactPayload.KeyPointItem(item.index(), validateText(item.text())))
                .toList(),
            glossary.stream()
                .map(this::optionalGlossaryItem)
                .filter(item -> !item.isEmpty())
                .map(item -> new JsonArtifactPayload.GlossaryItem(
                    item.term(),
                    item.definition(),
                    item.translation()
                ))
                .toList(),
            qa.stream()
                .map(item -> new JsonArtifactPayload.QaItem(
                    validateText(item.question()),
                    validateText(item.answer())
                ))
                .toList()
        );
    }

    private <T> List<T> readJson(String json, TypeReference<List<T>> typeReference) {
        if (json == null || json.isBlank()) {
            throw validationFailure("JSON learning package content is invalid");
        }
        try {
            List<T> items = objectMapper.readValue(json, typeReference);
            return items == null ? List.of() : items;
        } catch (JsonProcessingException exception) {
            throw validationFailure("JSON learning package content is invalid");
        }
    }

    private String validateText(String value) {
        String normalized = normalizeText(value);
        if (normalized.isBlank() || ArtifactSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure("JSON artifact content is invalid");
        }
        return normalized;
    }

    private OptionalGlossaryItem optionalGlossaryItem(GlossaryItem item) {
        if (item == null) {
            return OptionalGlossaryItem.empty();
        }
        String term = optionalText(item.term());
        String definition = optionalText(item.definition());
        String translation = optionalText(item.translation());
        if (term.isBlank() && definition.isBlank() && translation.isBlank()) {
            return OptionalGlossaryItem.empty();
        }
        return new OptionalGlossaryItem(term, definition, translation);
    }

    private String optionalText(String value) {
        String normalized = normalizeText(value);
        if (!normalized.isBlank() && ArtifactSensitiveDataValidator.containsSensitiveData(normalized)) {
            throw validationFailure("JSON artifact content is invalid");
        }
        return normalized;
    }

    private String normalizeText(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder builder = new StringBuilder();
        boolean previousSpace = false;
        for (int i = 0; i < value.length(); i++) {
            char current = value.charAt(i);
            boolean asSpace = Character.isWhitespace(current) || Character.isISOControl(current);
            if (asSpace) {
                if (!previousSpace) {
                    builder.append(' ');
                    previousSpace = true;
                }
            } else {
                builder.append(current);
                previousSpace = false;
            }
        }
        return builder.toString().trim();
    }

    private BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private record OptionalGlossaryItem(String term, String definition, String translation) {

        private static OptionalGlossaryItem empty() {
            return new OptionalGlossaryItem("", "", "");
        }

        private boolean isEmpty() {
            return term.isBlank() && definition.isBlank() && translation.isBlank();
        }
    }
}
