package com.example.courselingo.ai.llm;

import com.fasterxml.jackson.databind.JsonNode;

/** Retains bounded failure metadata using the existing translation recovery contract. */
public final class LlmOutputGuard {
    private LlmOutputGuard() {}

    public static void rejectTruncated(JsonNode root, int httpStatus) {
        var choice = root.path("choices").path(0);
        // A valid JSON prefix or an empty content field cannot override provider-declared truncation.
        if ("length".equals(choice.path("finish_reason").asText())) {
            throw new TranslationFailure(TranslationFailure.Reason.TRUNCATED, httpStatus,
                LlmUsage.parse(root), "length", 0, TranslationFailure.Check.OUTPUT_TRUNCATED);
        }
    }

    public static void rejectEmpty(JsonNode root, int httpStatus) {
        var choice = root.path("choices").path(0);
        var content = choice.path("message").path("content");
        if (content.isNull() || content.isTextual() && content.asText().isBlank()) {
            throw new TranslationFailure(TranslationFailure.Reason.EMPTY_OUTPUT, httpStatus,
                LlmUsage.parse(root), choice.path("finish_reason").asText(null), 0,
                content.isNull() ? TranslationFailure.Check.CONTENT_NULL : TranslationFailure.Check.CONTENT_EMPTY);
        }
    }
}
