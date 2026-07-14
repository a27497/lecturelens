package com.example.courselingo.subtitle.service;

import com.example.courselingo.ai.llm.LlmMessage;
import com.example.courselingo.ai.llm.LlmResponseFormat;
import com.example.courselingo.ai.llm.LlmRequest;
import com.example.courselingo.ai.llm.LlmRole;
import com.example.courselingo.subtitle.domain.SubtitleSegment;
import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;

final class SubtitleTranslationPromptFactory {

    private static final Duration SUBTITLE_TIMEOUT = Duration.ofSeconds(60);
    private static final double TEMPERATURE = 0.1;
    private static final int SUBTITLE_MAX_TOKENS = 4096;

    private SubtitleTranslationPromptFactory() {
    }

    static LlmRequest build(ValidatedTranslationCommand command, SubtitleSegment sourceSegment) {
        return new LlmRequest(
            command.requestId(),
            command.taskId(),
            List.of(systemMessage(), userMessage(command, sourceSegment)),
            SUBTITLE_TIMEOUT,
            TEMPERATURE,
            SUBTITLE_MAX_TOKENS,
            Map.of(
                "sourceLanguage", command.sourceLanguage(),
                "targetLanguage", command.targetLanguage(),
                "segmentIndex", sourceSegment.getSegmentIndex()
            ),
            LlmResponseFormat.TEXT
        );
    }

    static LlmRequest buildAlignedBatch(
        ValidatedTranslationCommand command,
        List<SubtitleSegment> sourceSegments,
        Duration requestTimeout,
        int maxTokens,
        int maxAttempts
    ) {
        return buildAlignedBatchRequest(
            command,
            sourceSegments,
            requestTimeout,
            maxTokens,
            maxAttempts,
            1,
            false,
            null
        );
    }

    static LlmRequest buildAlignedBatchSemanticRetry(
        ValidatedTranslationCommand command,
        List<SubtitleSegment> sourceSegments,
        Duration requestTimeout,
        int maxTokens,
        int maxAttempts,
        int semanticAttempt,
        String semanticRetryReason
    ) {
        return buildAlignedBatchRequest(
            command,
            sourceSegments,
            requestTimeout,
            maxTokens,
            maxAttempts,
            semanticAttempt,
            true,
            semanticRetryReason
        );
    }

    private static LlmMessage systemMessage() {
        return new LlmMessage(
            LlmRole.SYSTEM,
            "You translate subtitle text. Translate only the subtitle text provided by the user. Return only the translated plain text. Do not return JSON. Do not return Markdown. Do not include explanations. Do not include numbering."
        );
    }

    private static LlmMessage userMessage(ValidatedTranslationCommand command, SubtitleSegment sourceSegment) {
        StringBuilder payload = new StringBuilder();
        payload.append("Translate this subtitle text from ")
            .append(command.sourceLanguage())
            .append(" to ")
            .append(command.targetLanguage())
            .append(".\n\n")
            .append(sourceSegment.getText());
        return new LlmMessage(LlmRole.USER, payload.toString());
    }

    private static LlmRequest buildAlignedBatchRequest(
        ValidatedTranslationCommand command,
        List<SubtitleSegment> sourceSegments,
        Duration requestTimeout,
        int maxTokens,
        int maxAttempts,
        int semanticAttempt,
        boolean semanticRetry,
        String semanticRetryReason
    ) {
        Map<String, Object> metadata = new LinkedHashMap<>();
        metadata.put("sourceLanguage", command.sourceLanguage());
        metadata.put("targetLanguage", command.targetLanguage());
        metadata.put("translationMode", "alignedBatch");
        metadata.put("semanticAttempt", semanticAttempt);
        metadata.put("semanticRetry", semanticRetry);
        if (semanticRetryReason != null && !semanticRetryReason.isBlank()) {
            metadata.put("semanticRetryReason", semanticRetryReason);
        }
        metadata.put("sourceSegmentCount", sourceSegments.size());
        return new LlmRequest(
            command.requestId(),
            command.taskId(),
            List.of(
                semanticRetry
                    ? alignedBatchSemanticRetrySystemMessage(command.targetLanguage())
                    : alignedBatchSystemMessage(command.targetLanguage()),
                alignedBatchUserMessage(command, sourceSegments)
            ),
            requestTimeout,
            TEMPERATURE,
            maxTokens,
            maxAttempts,
            metadata,
            LlmResponseFormat.JSON_OBJECT
        );
    }

    private static LlmMessage alignedBatchSystemMessage(String targetLanguage) {
        String target = languageDisplayName(targetLanguage);
        String targetName = languageName(targetLanguage);
        return new LlmMessage(
            LlmRole.SYSTEM,
            """
                Target language is %s.
                Translate all normal prose into natural %s.
                Do not copy complete English sentences from the source.
                Only established technical terms, product names, API names, class names and code identifiers may remain in English.
                Do not summarize, omit or merge segments.
                Return only one valid JSON object with this exact shape: {"segments":[{"index":0,"text":"translated text"}]}.
                Use each input segment's batch-local index in the response. Return exactly one non-empty text item for every input segment.
                Do not return sourceSegmentIndex, source text, Markdown, code fences, explanations, or additional fields.
                """.formatted(target, targetName)
        );
    }

    private static LlmMessage alignedBatchSemanticRetrySystemMessage(String targetLanguage) {
        String target = languageDisplayName(targetLanguage);
        String targetName = languageName(targetLanguage);
        return new LlmMessage(
            LlmRole.SYSTEM,
            """
                The previous JSON structure was valid, but the translated text did not satisfy the requested target language.
                Return the complete batch again.
                Target language is %s.
                All normal prose must be natural %s.
                Do not copy the English source.
                Technical terms and code identifiers may remain in English.
                Return exactly one item for every input segment.
                Return only one valid JSON object with this exact shape: {"segments":[{"index":0,"text":"translated text"}]}.
                Use each input segment's batch-local index. Do not summarize, omit or merge segments.
                Do not return sourceSegmentIndex, source text, Markdown, code fences, explanations, or additional fields.
                """.formatted(target, targetName)
        );
    }

    private static LlmMessage alignedBatchUserMessage(
        ValidatedTranslationCommand command,
        List<SubtitleSegment> sourceSegments
    ) {
        StringBuilder payload = new StringBuilder();
        payload.append("Translate these subtitle segments from ")
            .append(languageDisplayName(command.sourceLanguage()))
            .append(" to ")
            .append(languageDisplayName(command.targetLanguage()))
            .append(". Input JSON: {\"segments\":[");
        for (int index = 0; index < sourceSegments.size(); index++) {
            SubtitleSegment segment = sourceSegments.get(index);
            if (index > 0) {
                payload.append(',');
            }
            payload.append("{\"index\":")
                .append(index)
                .append(",\"sourceSegmentIndex\":")
                .append(segment.getSegmentIndex())
                .append(",\"text\":\"")
                .append(jsonEscape(segment.getText()))
                .append("\"}");
        }
        payload.append("]}");
        return new LlmMessage(LlmRole.USER, payload.toString());
    }

    private static String languageDisplayName(String languageCode) {
        if (languageCode == null || languageCode.isBlank()) {
            return "unknown";
        }
        String code = languageCode.strip();
        String name = languageName(code);
        return name.equals(code) ? code : name + " (" + code + ")";
    }

    private static String languageName(String languageCode) {
        if (languageCode == null || languageCode.isBlank()) {
            return "unknown";
        }
        String code = languageCode.strip();
        return switch (code.replace('_', '-').toLowerCase(Locale.ROOT)) {
            case "zh-cn", "zh-hans" -> "Simplified Chinese";
            case "zh-tw", "zh-hant" -> "Traditional Chinese";
            case "en", "en-us", "en-gb" -> "English";
            case "ja" -> "Japanese";
            case "ko" -> "Korean";
            default -> code;
        };
    }

    private static String jsonEscape(String value) {
        StringBuilder escaped = new StringBuilder();
        for (int index = 0; index < value.length(); index++) {
            char ch = value.charAt(index);
            switch (ch) {
                case '\\' -> escaped.append("\\\\");
                case '"' -> escaped.append("\\\"");
                case '\b' -> escaped.append("\\b");
                case '\f' -> escaped.append("\\f");
                case '\n' -> escaped.append("\\n");
                case '\r' -> escaped.append("\\r");
                case '\t' -> escaped.append("\\t");
                default -> {
                    if (ch < 0x20) {
                        escaped.append(String.format(java.util.Locale.ROOT, "\\u%04x", (int) ch));
                    } else {
                        escaped.append(ch);
                    }
                }
            }
        }
        return escaped.toString();
    }

}
