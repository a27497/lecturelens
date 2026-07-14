package com.example.courselingo.subtitle.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import org.springframework.stereotype.Component;

@Component
public class SubtitleTranslationResponseParser {

    private final ObjectMapper objectMapper;

    public SubtitleTranslationResponseParser() {
        this(new ObjectMapper());
    }

    SubtitleTranslationResponseParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
    }

    public List<ParsedTranslationSegment> parse(String content, List<SubtitleSegment> sourceSegments) {
        if (content == null || content.isBlank()) {
            throw validationFailure("EMPTY_RESPONSE Translation response is invalid");
        }
        SourceIndexes sourceIndexes = sourceIndexes(sourceSegments);
        JsonNode segmentsNode = readSegments(content);
        if (!segmentsNode.isArray() || segmentsNode.isEmpty()) {
            throw validationFailure("UNEXPECTED_SCHEMA Translation response segments are invalid");
        }

        Map<Integer, String> translatedByReturnedIndex = new HashMap<>();
        for (JsonNode node : segmentsNode) {
            int index = readIndex(node);
            if (translatedByReturnedIndex.containsKey(index)) {
                if (!sourceIndexes.localIndexes().contains(index) && !sourceIndexes.originalIndexes().contains(index)) {
                    throw validationFailure("UNKNOWN_INDEX Translation response segment index is invalid");
                }
                throw validationFailure("DUPLICATE_INDEX Translation response contains duplicate segment index");
            }
            translatedByReturnedIndex.put(index, readText(node));
        }

        IndexScheme scheme = resolveIndexScheme(translatedByReturnedIndex.keySet(), sourceIndexes);
        List<ParsedTranslationSegment> parsed = new ArrayList<>(sourceSegments.size());
        for (SubtitleSegment source : sourceIndexes.batchSources()) {
            parsed.add(new ParsedTranslationSegment(
                source.getSegmentIndex(),
                translatedByReturnedIndex.get(scheme.returnedIndexFor(source, sourceIndexes))
            ));
        }
        return List.copyOf(parsed);
    }

    static BatchOutputFailure classifyBatchOutputException(Throwable error) {
        Throwable current = error;
        int depth = 0;
        while (current != null && depth < 16) {
            if (current instanceof BusinessException businessException
                && businessException.errorCode() == ErrorCode.AI_PROVIDER_TIMEOUT) {
                return BatchOutputFailure.none();
            }
            String message = current.getMessage();
            if (isNonRetryableInfrastructureMessage(message)) {
                return BatchOutputFailure.none();
            }
            if (message != null) {
                for (String reason : List.of(
                    "EMPTY_RESPONSE",
                    "MISSING_SEGMENT",
                    "DUPLICATE_INDEX",
                    "MISSING_TEXT",
                    "BLANK_TEXT",
                    "NON_STRING_TEXT",
                    "INCOMPLETE_JSON"
                )) {
                    if (message.startsWith(reason + " ")) {
                        return BatchOutputFailure.retryable(reason);
                    }
                }
            }
            current = current.getCause();
            depth++;
        }
        return BatchOutputFailure.none();
    }

    private JsonNode readSegments(String content) {
        try {
            JsonNode root = readBusinessJson(content);
            JsonNode segments = root.get("segments");
            if (segments == null) {
                throw validationFailure("UNEXPECTED_SCHEMA Translation response segments are invalid");
            }
            return segments;
        } catch (IOException ex) {
            String reason = isLikelyIncompleteJson(content) ? "INCOMPLETE_JSON" : "JSON_PARSE_ERROR";
            throw validationFailure(reason + " Translation response JSON is invalid");
        }
    }

    private JsonNode readBusinessJson(String content) throws IOException {
        JsonNode root = objectMapper.readTree(cleanJsonContent(content));
        if (!root.isTextual()) {
            return root;
        }
        return objectMapper.readTree(cleanJsonContent(root.asText()));
    }

    private static String cleanJsonContent(String content) {
        String trimmed = content == null ? "" : content.trim();
        if (!trimmed.startsWith("```")) {
            return trimmed;
        }
        int firstLineEnd = trimmed.indexOf('\n');
        int closingFence = trimmed.lastIndexOf("```");
        if (firstLineEnd < 0 || closingFence <= firstLineEnd) {
            return trimmed;
        }
        return trimmed.substring(firstLineEnd + 1, closingFence).trim();
    }

    private static boolean isLikelyIncompleteJson(String content) {
        String cleaned = cleanJsonContent(content);
        if (!cleaned.startsWith("{")) {
            return false;
        }
        int braces = 0;
        int brackets = 0;
        boolean quoted = false;
        boolean escaped = false;
        for (int index = 0; index < cleaned.length(); index++) {
            char ch = cleaned.charAt(index);
            if (quoted) {
                if (escaped) {
                    escaped = false;
                } else if (ch == '\\') {
                    escaped = true;
                } else if (ch == '"') {
                    quoted = false;
                }
            } else if (ch == '"') {
                quoted = true;
            } else if (ch == '{') {
                braces++;
            } else if (ch == '}') {
                braces--;
            } else if (ch == '[') {
                brackets++;
            } else if (ch == ']') {
                brackets--;
            }
        }
        return quoted || braces > 0 || brackets > 0;
    }

    private static SourceIndexes sourceIndexes(List<SubtitleSegment> sourceSegments) {
        if (sourceSegments == null || sourceSegments.isEmpty()) {
            throw validationFailure("Source subtitle segments are required");
        }
        List<SubtitleSegment> batchSources = List.copyOf(sourceSegments);
        Set<Integer> localIndexes = new HashSet<>();
        Set<Integer> originalIndexes = new HashSet<>();
        Map<Integer, Integer> localByOriginalIndex = new HashMap<>();
        for (int localIndex = 0; localIndex < batchSources.size(); localIndex++) {
            SubtitleSegment source = batchSources.get(localIndex);
            if (source == null || source.getSegmentIndex() == null || !originalIndexes.add(source.getSegmentIndex())) {
                throw validationFailure("Source subtitle segment is invalid");
            }
            localIndexes.add(localIndex);
            localByOriginalIndex.put(source.getSegmentIndex(), localIndex);
        }
        return new SourceIndexes(batchSources, localIndexes, originalIndexes, localByOriginalIndex);
    }

    private static IndexScheme resolveIndexScheme(Set<Integer> returnedIndexes, SourceIndexes sourceIndexes) {
        int expected = sourceIndexes.batchSources().size();
        if (returnedIndexes.size() < expected) {
            throw validationFailure("MISSING_SEGMENT Translation response segment indexes are incomplete");
        }
        if (returnedIndexes.size() > expected) {
            throw validationFailure("EXTRA_SEGMENT Translation response contains extra segment index");
        }
        if (returnedIndexes.equals(sourceIndexes.localIndexes())) {
            return IndexScheme.LOCAL;
        }
        if (returnedIndexes.equals(sourceIndexes.originalIndexes())) {
            return IndexScheme.ORIGINAL;
        }
        throw validationFailure("INCONSISTENT_INDEX Translation response segment indexes are inconsistent");
    }

    private static int readIndex(JsonNode node) {
        JsonNode indexNode = node == null ? null : node.get("index");
        if (indexNode == null || !indexNode.isIntegralNumber() || !indexNode.canConvertToInt() || indexNode.asInt() < 0) {
            throw validationFailure("INVALID_INDEX Translation response segment index is invalid");
        }
        return indexNode.asInt();
    }

    private static String readText(JsonNode node) {
        JsonNode textNode = node == null ? null : node.get("text");
        if (textNode == null) {
            throw validationFailure("MISSING_TEXT Translation response segment text is invalid");
        }
        if (!textNode.isTextual()) {
            throw validationFailure("NON_STRING_TEXT Translation response segment text is invalid");
        }
        if (textNode.asText().isBlank()) {
            throw validationFailure("BLANK_TEXT Translation response segment text is invalid");
        }
        String text = textNode.asText().strip();
        if (SubtitleSensitiveDataValidator.containsSensitiveData(text)) {
            throw validationFailure("SENSITIVE_TEXT Translation response segment text is invalid");
        }
        return text;
    }

    private static boolean isNonRetryableInfrastructureMessage(String message) {
        if (message == null || message.isBlank()) {
            return false;
        }
        String normalized = message.strip().toLowerCase(java.util.Locale.ROOT).replace('-', '_');
        return normalized.contains("timeout")
            || normalized.contains("unauthorized")
            || normalized.contains("forbidden")
            || normalized.contains("api_key")
            || normalized.contains("not configured")
            || normalized.contains("config");
    }

    private static BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    public record ParsedTranslationSegment(int segmentIndex, String text) {
    }

    record BatchOutputFailure(boolean retryable, String reason) {
        private static BatchOutputFailure none() {
            return new BatchOutputFailure(false, null);
        }

        private static BatchOutputFailure retryable(String reason) {
            return new BatchOutputFailure(true, reason);
        }
    }

    private record SourceIndexes(
        List<SubtitleSegment> batchSources,
        Set<Integer> localIndexes,
        Set<Integer> originalIndexes,
        Map<Integer, Integer> localByOriginalIndex
    ) {
    }

    private enum IndexScheme {
        LOCAL {
            @Override
            int returnedIndexFor(SubtitleSegment source, SourceIndexes indexes) {
                return indexes.localByOriginalIndex().get(source.getSegmentIndex());
            }
        },
        ORIGINAL {
            @Override
            int returnedIndexFor(SubtitleSegment source, SourceIndexes indexes) {
                return source.getSegmentIndex();
            }
        };

        abstract int returnedIndexFor(SubtitleSegment source, SourceIndexes indexes);
    }
}
