package com.example.courselingo.learning.service;

import com.example.courselingo.ai.llm.LlmMessage;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmRole;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import com.example.courselingo.subtitle.domain.SubtitleTranslationSegment;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.stream.Collectors;

final class LearningPackagePromptFactory {

    private static final double TEMPERATURE = 0.2;
    private static final int MAX_TOKENS = 4096;

    private LearningPackagePromptFactory() {
    }

    static LlmRequest build(
        ValidatedLearningPackageCommand command,
        List<SubtitleSegment> sourceSegments,
        List<SubtitleTranslationSegment> translationSegments,
        Duration llmTimeout
    ) {
        return new LlmRequest(
            command.requestId(),
            command.taskId(),
            List.of(systemMessage(), userMessage(command, sourceSegments, translationSegments)),
            Objects.requireNonNull(llmTimeout, "llmTimeout must not be null"),
            TEMPERATURE,
            MAX_TOKENS,
            Map.of(
                "sourceLanguage", command.sourceLanguage(),
                "targetLanguage", command.targetLanguage(),
                "sourceSegmentCount", sourceSegments.size(),
                "translationSegmentCount", translationSegments.size()
            ),
            LlmResponseFormat.JSON_OBJECT
        );
    }

    static LlmRequest buildFromFullText(
        ValidatedLearningPackageCommand command,
        String sourceFullText,
        String translatedFullText,
        Duration llmTimeout
    ) {
        return new LlmRequest(
            command.requestId(),
            command.taskId(),
            List.of(systemMessage(), fullTextUserMessage(command, sourceFullText, translatedFullText)),
            Objects.requireNonNull(llmTimeout, "llmTimeout must not be null"),
            TEMPERATURE,
            MAX_TOKENS,
            Map.of(
                "sourceLanguage", command.sourceLanguage(),
                "targetLanguage", command.targetLanguage(),
                "promptSource", "fullText"
            ),
            LlmResponseFormat.JSON_OBJECT
        );
    }

    static LlmRequest buildRetry(
        ValidatedLearningPackageCommand command,
        List<SubtitleSegment> sourceSegments,
        List<SubtitleTranslationSegment> translationSegments,
        Duration llmTimeout
    ) {
        return new LlmRequest(
            command.requestId(),
            command.taskId(),
            List.of(retrySystemMessage(), userMessage(command, sourceSegments, translationSegments)),
            Objects.requireNonNull(llmTimeout, "llmTimeout must not be null"),
            0.0,
            MAX_TOKENS,
            Map.of(
                "sourceLanguage", command.sourceLanguage(),
                "targetLanguage", command.targetLanguage(),
                "sourceSegmentCount", sourceSegments.size(),
                "translationSegmentCount", translationSegments.size(),
                "promptVariant", "retry"
            ),
            LlmResponseFormat.JSON_OBJECT
        );
    }

    static LlmRequest buildRetryFromFullText(
        ValidatedLearningPackageCommand command,
        String sourceFullText,
        String translatedFullText,
        Duration llmTimeout
    ) {
        return new LlmRequest(
            command.requestId(),
            command.taskId(),
            List.of(retrySystemMessage(), fullTextUserMessage(command, sourceFullText, translatedFullText)),
            Objects.requireNonNull(llmTimeout, "llmTimeout must not be null"),
            0.0,
            MAX_TOKENS,
            Map.of(
                "sourceLanguage", command.sourceLanguage(),
                "targetLanguage", command.targetLanguage(),
                "promptSource", "fullText",
                "promptVariant", "retry"
            ),
            LlmResponseFormat.JSON_OBJECT
        );
    }

    private static LlmMessage systemMessage() {
        return new LlmMessage(
            LlmRole.SYSTEM,
            """
                Create a concise structured learning package.
                Return only a valid JSON object.
                Do not return Markdown.
                Do not wrap the output in ```json fences.
                Do not include explanations before or after JSON.
                Use exactly these top-level fields: summary, keyPoints, glossary, qa.
                Required shape: {"summary":"string","keyPoints":["string"],"glossary":[{"term":"string","definition":"string"}],"qa":[{"question":"string","answer":"string"}]}.
                For short videos, keep summary to 1-2 sentences, keyPoints to at most 3 items, glossary to 3-5 items, and qa to 2-3 items. Keep each value brief.
                """
        );
    }

    private static LlmMessage retrySystemMessage() {
        return new LlmMessage(
            LlmRole.SYSTEM,
            """
                Create a minimal learning package.
                Return exactly one valid JSON object with this shape: {"summary":"one short sentence","keyPoints":["..."],"glossary":[],"qa":[]}.
                keyPoints must have at most 3 short strings.
                glossary must have at most 3 objects and may be [].
                qa must have at most 2 objects and may be [].
                Each answer must have at most 20 words.
                Do not repeat text.
                Do not use nested arrays.
                Do not return Markdown.
                Do not wrap the output in ```json fences.
                Do not include explanations before or after JSON.
                """
        );
    }

    private static LlmMessage userMessage(
        ValidatedLearningPackageCommand command,
        List<SubtitleSegment> sourceSegments,
        List<SubtitleTranslationSegment> translationSegments
    ) {
        Map<Integer, SubtitleTranslationSegment> translationsByIndex = translationSegments.stream()
            .collect(Collectors.toMap(SubtitleTranslationSegment::getSegmentIndex, segment -> segment));
        StringBuilder payload = new StringBuilder();
        payload.append("Build a learning package from ")
            .append(command.sourceLanguage())
            .append(" source subtitles and ")
            .append(command.targetLanguage())
            .append(" translated subtitles. Segments JSON: {\"segments\":[");
        for (int i = 0; i < sourceSegments.size(); i++) {
            SubtitleSegment source = sourceSegments.get(i);
            SubtitleTranslationSegment translated = translationsByIndex.get(source.getSegmentIndex());
            if (i > 0) {
                payload.append(',');
            }
            payload.append("{\"index\":")
                .append(source.getSegmentIndex())
                .append(",\"startMillis\":")
                .append(source.getStartMillis())
                .append(",\"endMillis\":")
                .append(source.getEndMillis())
                .append(",\"sourceText\":\"")
                .append(escapeJson(source.getText()))
                .append("\",\"translatedText\":\"")
                .append(escapeJson(translated.getTranslatedText()))
                .append("\"}");
        }
        payload.append("]}");
        return new LlmMessage(LlmRole.USER, payload.toString());
    }

    private static LlmMessage fullTextUserMessage(
        ValidatedLearningPackageCommand command,
        String sourceFullText,
        String translatedFullText
    ) {
        String payload = "Build a learning package from this course transcript.\n\n"
            + "Source language: " + command.sourceLanguage() + "\n"
            + "Target language: " + command.targetLanguage() + "\n\n"
            + "Source transcript:\n" + sourceFullText + "\n\n"
            + "Translated transcript:\n" + translatedFullText;
        return new LlmMessage(LlmRole.USER, payload);
    }

    private static String escapeJson(String value) {
        if (value == null) {
            return "";
        }
        StringBuilder escaped = new StringBuilder();
        for (int i = 0; i < value.length(); i++) {
            char ch = value.charAt(i);
            switch (ch) {
                case '\\' -> escaped.append("\\\\");
                case '"' -> escaped.append("\\\"");
                case '\n' -> escaped.append("\\n");
                case '\r' -> escaped.append("\\r");
                case '\t' -> escaped.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        escaped.append(String.format("\\u%04x", (int) ch));
                    } else {
                        escaped.append(ch);
                    }
                }
            }
        }
        return escaped.toString();
    }
}
