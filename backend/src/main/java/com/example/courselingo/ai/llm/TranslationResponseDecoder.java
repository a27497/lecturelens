package com.example.courselingo.ai.llm;

import com.example.courselingo.ai.llm.*;
import com.fasterxml.jackson.databind.*;
import java.net.URI;
import java.util.*;
import static com.example.courselingo.ai.llm.TranslationFailure.Reason.*;

public final class TranslationResponseDecoder {
    private static final ObjectMapper JSON = new ObjectMapper();
    private TranslationResponseDecoder() {}

    public static boolean enabled(LlmRequest request) {
        return Boolean.TRUE.equals(request.metadata().get("translationV2"))
            && "TRANSLATION_FULL_TEXT".equals(request.metadata().get("modelRouting.stage"));
    }
    public static void applyOptions(Map<String, Object> body, String baseUrl, String model, LlmRequest request) {
        if (enabled(request) && "api.deepseek.com".equalsIgnoreCase(URI.create(baseUrl).getHost())
            && "deepseek-flash".equals(model)) body.put("thinking", Map.of("type", "disabled"));
    }
    public static LlmResult decode(OpenAiCompatibleClientResponse response, String model, Map<String, Object> metadata) {
        JsonNode root = null;
        try { root = JSON.readTree(response.body()); } catch (Exception ignored) { }
        var usageNode = root == null ? JSON.createObjectNode() : root.path("usage");
        var usage = LlmUsage.parse(root);
        int status = response.statusCode();
        if (status < 200 || status >= 300) {
            var reason = status == 401 || status == 403 ? AUTHENTICATION : status == 404 ? MODEL_NOT_FOUND
                : status == 408 ? TIMEOUT : status == 429 ? RATE_LIMITED : status >= 500 ? UPSTREAM_5XX : INVALID_REQUEST;
            throw new TranslationFailure(reason, status, usage, null, retryAfter(response));
        }
        if (root == null || !root.isObject()) throw new TranslationFailure(FORMAT_INVALID, status, usage, null, 0,TranslationFailure.Check.ENVELOPE_JSON_INVALID);
        var choice = root.path("choices").path(0);
        String finish = choice.path("finish_reason").asText("");
        if ("length".equals(finish)) throw new TranslationFailure(TRUNCATED, status, usage, finish, 0,TranslationFailure.Check.OUTPUT_TRUNCATED);
        var content = choice.path("message").path("content");
        if (content.isMissingNode()) throw new TranslationFailure(FORMAT_INVALID,status,usage,finish,0,TranslationFailure.Check.CONTENT_MISSING);
        if (content.isNull() || content.isTextual() && content.asText().isBlank())
            throw new TranslationFailure(EMPTY_OUTPUT, status, usage, finish, 0,
                content.isNull()?TranslationFailure.Check.CONTENT_NULL:TranslationFailure.Check.CONTENT_EMPTY);
        if (!content.isTextual()) throw new TranslationFailure(FORMAT_INVALID,status,usage,finish,0,TranslationFailure.Check.CONTENT_NON_STRING);
        if (!"stop".equals(finish)) throw new TranslationFailure(FORMAT_INVALID,status,usage,finish,0,TranslationFailure.Check.FINISH_REASON);
        try {
            var value = JSON.readTree(content.asText());
            if (value == null || !value.isObject()) throw new IllegalArgumentException();
        } catch (Exception ignored) { throw new TranslationFailure(FORMAT_INVALID, status, usage, finish, 0,TranslationFailure.Check.CONTENT_JSON_INVALID); }
        return new LlmResult("openai-compatible", model, content.asText(), finish, usage, response.duration(), metadata);
    }
    private static Integer number(JsonNode n, String field) {
        var v = n.path(field);
        return v.isIntegralNumber() && v.canConvertToInt() && v.intValue() >= 0 ? v.intValue() : null;
    }
    private static long retryAfter(OpenAiCompatibleClientResponse response) {
        try {
            String text = response.headers().entrySet().stream().filter(e -> e.getKey().equalsIgnoreCase("retry-after"))
                .map(Map.Entry::getValue).flatMap(Collection::stream).findFirst().orElse("0");
            try {
                long seconds = Long.parseLong(text);
                return seconds < 0 ? 0 : Math.min(seconds, 86400) * 1000;
            } catch (NumberFormatException ignored) {
                var instant = java.time.ZonedDateTime.parse(text,java.time.format.DateTimeFormatter.RFC_1123_DATE_TIME).toInstant();
                return Math.min(86400000,Math.max(0,java.time.Duration.between(java.time.Instant.now(),instant).toMillis()));
            }
        } catch (Exception ignored) { return 0; }
    }
}
