package com.example.courselingo.learning.service;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import com.example.courselingo.learning.dto.GlossaryItem;
import com.example.courselingo.learning.dto.KeyPointItem;
import com.example.courselingo.learning.dto.QaItem;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Component;

@Component
public class LearningPackageResponseParser {

    private static final Logger log = LoggerFactory.getLogger(LearningPackageResponseParser.class);
    private static final int MAX_TITLE_LENGTH = 255;
    private static final String DEFAULT_TITLE = "Learning Package";

    private final ObjectMapper objectMapper;

    public LearningPackageResponseParser() {
        this(new ObjectMapper());
    }

    LearningPackageResponseParser(ObjectMapper objectMapper) {
        this.objectMapper = objectMapper == null ? new ObjectMapper() : objectMapper;
    }

    public ParsedLearningPackage parse(String content) {
        if (content == null || content.isBlank()) {
            throw validationFailure("EMPTY_RESPONSE Learning package response is invalid");
        }
        JsonNode root = readRoot(content);
        String title = readOptionalText(root, "Learning package title is invalid", DEFAULT_TITLE, "title");
        if (title.length() > MAX_TITLE_LENGTH) {
            throw validationFailure("Learning package title is invalid");
        }
        String summary = readOptionalText(root, "Learning package summary is invalid", "", "summary");
        List<KeyPointItem> keyPoints = readKeyPoints(firstNode(root, "keyPoints", "key_points", "points", "mainPoints"));
        List<GlossaryItem> glossary = readGlossary(firstNode(root, "glossary", "terms", "vocabulary"));
        List<QaItem> qa = readQa(firstNode(root, "qa", "questions", "quiz", "qas"));
        return new ParsedLearningPackage(
            title,
            summary,
            writeJson(keyPoints),
            writeJson(glossary),
            writeJson(qa)
        );
    }

    private JsonNode readRoot(String content) {
        try {
            JsonNode root = objectMapper.readTree(cleanJsonContent(content));
            if (root == null || !root.isObject()) {
                throw validationFailure("UNEXPECTED_SCHEMA Learning package response is invalid");
            }
            return root;
        } catch (IOException ex) {
            throw validationFailure("JSON_PARSE_ERROR Learning package response JSON is invalid");
        }
    }

    private static String cleanJsonContent(String content) {
        String trimmed = content == null ? "" : content.trim();
        if (trimmed.startsWith("```")) {
            int firstLineEnd = trimmed.indexOf('\n');
            int closingFence = trimmed.lastIndexOf("```");
            if (firstLineEnd >= 0 && closingFence > firstLineEnd) {
                trimmed = trimmed.substring(firstLineEnd + 1, closingFence).trim();
            }
        }
        int firstObjectStart = trimmed.indexOf('{');
        int lastObjectEnd = trimmed.lastIndexOf('}');
        if (firstObjectStart >= 0 && lastObjectEnd > firstObjectStart) {
            return trimmed.substring(firstObjectStart, lastObjectEnd + 1).trim();
        }
        return trimmed;
    }

    private List<KeyPointItem> readKeyPoints(JsonNode node) {
        if (node == null || node.isNull()) {
            return List.of();
        }
        if (!node.isArray()) {
            throw validationFailure("Learning package key points are invalid");
        }
        List<KeyPointItem> items = new ArrayList<>();
        int fallbackIndex = 1;
        for (JsonNode item : node) {
            String scalarText = recoverableScalarText(item);
            if (scalarText != null) {
                items.add(new KeyPointItem(fallbackIndex++, scalarText));
                continue;
            }
            if (isBlankScalar(item)) {
                logItemDropped("keyPoint", "blank_key_point");
                continue;
            }
            if (item == null || !item.isObject()) {
                logItemDropped("keyPoint", "invalid_shape");
                continue;
            }
            JsonNode indexNode = item.get("index");
            int index = indexNode != null && indexNode.canConvertToInt() && indexNode.asInt() > 0
                ? indexNode.asInt()
                : fallbackIndex;
            String text = optionalSafeText(firstNode(item, "text"));
            if (text == null) {
                logItemDropped("keyPoint", "blank_key_point");
                continue;
            }
            items.add(new KeyPointItem(index, text));
            fallbackIndex++;
        }
        return items;
    }

    private List<GlossaryItem> readGlossary(JsonNode node) {
        if (node == null || node.isNull()) {
            return List.of();
        }
        if (!node.isArray()) {
            throw validationFailure("Learning package glossary is invalid");
        }
        List<GlossaryItem> items = new ArrayList<>();
        int index = 0;
        while (index < node.size()) {
            JsonNode item = node.get(index);
            String scalarTerm = recoverableScalarText(item);
            if (scalarTerm != null || isBlankScalar(item)) {
                String term = scalarTerm;
                String definition = "";
                JsonNode next = index + 1 < node.size() ? node.get(index + 1) : null;
                if (isValueNode(next)) {
                    String nextText = optionalSafeText(next);
                    definition = nextText == null ? "" : nextText;
                    index++;
                }
                if (term == null) {
                    logItemDropped("glossary", "blank_term");
                } else {
                    items.add(new GlossaryItem(term, definition, ""));
                }
                index++;
                continue;
            }
            if (item == null || !item.isObject()) {
                logItemDropped("glossary", "invalid_shape");
                index++;
                continue;
            }
            String term = optionalSafeText(firstNode(item, "term"));
            if (term == null) {
                logItemDropped("glossary", "blank_term");
                index++;
                continue;
            }
            items.add(new GlossaryItem(
                term,
                optionalSafeText(firstNode(item, "definition", "explanation", "meaning"), ""),
                optionalSafeText(item.get("translation"), "")
            ));
            index++;
        }
        return items;
    }

    private List<QaItem> readQa(JsonNode node) {
        if (node == null || node.isNull()) {
            return List.of();
        }
        if (!node.isArray()) {
            throw validationFailure("Learning package qa is invalid");
        }
        List<QaItem> items = new ArrayList<>();
        readQaItems(node, items);
        return items;
    }

    private static void readQaItems(JsonNode node, List<QaItem> items) {
        if (node == null || node.isNull()) {
            return;
        }
        if (node.isArray()) {
            for (JsonNode item : node) {
                readQaItems(item, items);
            }
            return;
        }
        String scalarText = recoverableScalarText(node);
        if (scalarText != null || isBlankScalar(node)) {
            logItemDropped("qa", scalarText == null ? "blank_question" : "blank_answer");
            return;
        }
        if (!node.isObject()) {
            logItemDropped("qa", "invalid_shape");
            return;
        }
        String question = optionalSafeText(firstNode(node, "question", "q"));
        if (question == null) {
            logItemDropped("qa", "blank_question");
            return;
        }
        String answer = optionalSafeText(firstNode(node, "answer", "a"));
        if (answer == null) {
            logItemDropped("qa", "blank_answer");
            return;
        }
        items.add(new QaItem(question, answer));
    }

    private static boolean isValueNode(JsonNode node) {
        return node != null && node.isValueNode() && !node.isNull();
    }

    private static boolean isBlankScalar(JsonNode node) {
        return isValueNode(node) && node.asText().isBlank();
    }

    private static String recoverableScalarText(JsonNode node) {
        if (!isValueNode(node)) {
            return null;
        }
        return optionalSafeText(node);
    }

    private static JsonNode firstNode(JsonNode root, String... fields) {
        if (root == null || fields == null) {
            return null;
        }
        for (String field : fields) {
            JsonNode node = root.get(field);
            if (node != null && !node.isNull()) {
                return node;
            }
        }
        return null;
    }

    private static String readRequiredText(JsonNode root, String message, String... fields) {
        JsonNode node = firstNode(root, fields);
        if (node == null || !node.isTextual() || node.asText().isBlank()) {
            throw validationFailure(message);
        }
        return requireSafeText(node.asText(), message);
    }

    private static String readOptionalText(JsonNode root, String message, String fallback, String... fields) {
        JsonNode node = firstNode(root, fields);
        if (node == null || node.isNull() || (node.isTextual() && node.asText().isBlank())) {
            return fallback;
        }
        if (!node.isTextual()) {
            throw validationFailure(message);
        }
        return requireSafeText(node.asText(), message);
    }

    private static String readOptionalText(JsonNode root, String field) {
        JsonNode node = root == null ? null : root.get(field);
        if (node == null || node.isNull()) {
            return "";
        }
        if (!node.isTextual()) {
            throw validationFailure("Learning package glossary item is invalid");
        }
        if (node.asText().isBlank()) {
            return "";
        }
        return requireSafeText(node.asText(), "Learning package glossary item is invalid");
    }

    private static String optionalSafeText(JsonNode node) {
        return optionalSafeText(node, null);
    }

    private static String optionalSafeText(JsonNode node, String fallback) {
        if (node == null || node.isNull()) {
            return fallback;
        }
        if (!node.isTextual() && !node.isValueNode()) {
            return fallback;
        }
        String text = node.asText();
        if (text == null || text.isBlank()) {
            return fallback;
        }
        String value = text.strip();
        if (LearningPackageSensitiveDataValidator.containsSensitiveData(value)) {
            return fallback;
        }
        return value;
    }

    private static String requireSafeText(String text, String message) {
        if (text == null || text.isBlank()) {
            throw validationFailure(message);
        }
        String value = text.strip();
        if (LearningPackageSensitiveDataValidator.containsSensitiveData(value)) {
            throw validationFailure(message);
        }
        return value;
    }

    private String writeJson(Object value) {
        try {
            return objectMapper.writeValueAsString(value);
        } catch (JsonProcessingException ex) {
            throw new BusinessException(ErrorCode.COMMON_INTERNAL_ERROR, "Learning package JSON serialization failed");
        }
    }

    private static BusinessException validationFailure(String message) {
        return new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED, message);
    }

    private static void logItemDropped(String itemType, String reason) {
        log.warn(
            "event=learning_package_item_dropped itemType={} reason={}",
            itemType,
            reason
        );
    }

    public record ParsedLearningPackage(
        String title,
        String summary,
        String keyPointsJson,
        String glossaryJson,
        String qaJson
    ) {
    }
}
