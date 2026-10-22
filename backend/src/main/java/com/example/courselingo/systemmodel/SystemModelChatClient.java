package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

final class SystemModelChatClient {
    private final OpenAiCompatibleLlmClient http;
    private final SystemModelUrlPolicy addresses;
    private final ObjectMapper json = new ObjectMapper();

    SystemModelChatClient(OpenAiCompatibleLlmClient http, SystemModelUrlPolicy addresses) {
        this.http = http;
        this.addresses = addresses;
    }

    LlmResult generate(LlmRequest request, SystemModelResolvedRoute route, String apiKey) {
        LlmRequestValidator.validate(request);
        long start = System.nanoTime();
        var uri = addresses.checkedChatEndpoint(route.baseUrl());
        long timeout =
                minimum(
                        route.timeoutMillis(),
                        request.timeout() == null ? null : request.timeout().toMillis(),
                        60000);
        int attempts =
                (int)
                        minimum(
                                route.maxAttempts() == null
                                        ? null
                                        : route.maxAttempts().longValue(),
                                request.maxAttempts() == null
                                        ? null
                                        : request.maxAttempts().longValue(),
                                1);
        attempts = Math.min(attempts, 3);
        var body = new LinkedHashMap<String, Object>();
        body.put("model", route.model());
        body.put(
                "messages",
                request.messages().stream()
                        .map(
                                m ->
                                        Map.of(
                                                "role",
                                                m.role().name().toLowerCase(Locale.ROOT),
                                                "content",
                                                m.content()))
                        .toList());
        body.put(
                "temperature",
                route.temperature() == null
                        ? (request.temperature() == null ? 0 : request.temperature())
                        : route.temperature());
        body.put(
                "max_tokens",
                minimum(
                        route.maxTokens() == null ? null : route.maxTokens().longValue(),
                        request.maxTokens() == null ? null : request.maxTokens().longValue(),
                        4096));
        body.put("stream", false);
        if (request.responseFormat() == LlmResponseFormat.JSON_OBJECT)
            body.put("response_format", Map.of("type", "json_object"));
        OpenAiCompatibleRequestOptionsAdapter.apply(body, route.model());
        String payload;
        try {
            payload = json.writeValueAsString(body);
        } catch (Exception ignored) {
            throw invalid();
        }
        for (int attempt = 0; attempt < attempts; attempt++) {
            long remaining = timeout - Duration.ofNanos(System.nanoTime() - start).toMillis();
            if (remaining <= 0)
                throw new SystemModelCallFailure(
                        "TIMEOUT", LlmProviderFailureCategory.TIMEOUT, null, true);
            try {
                var response =
                        http.complete(
                                new OpenAiCompatibleChatCompletionRequest(
                                        uri,
                                        Map.of("Authorization", "Bearer " + apiKey),
                                        "POST",
                                        "application/json",
                                        payload,
                                        Duration.ofMillis(remaining)));
                int status = response.statusCode();
                if (status < 200 || status >= 300) throw statusFailure(status);
                var root = json.readTree(response.body());
                var content = root.path("choices").path(0).path("message").path("content");
                if (!content.isTextual() || content.asText().isBlank()) throw invalid();
                if (request.responseFormat() == LlmResponseFormat.JSON_OBJECT
                        && !json.readTree(content.asText()).isObject()) throw invalid();
                var usage = root.path("usage");
                var metadata = new LinkedHashMap<String, Object>();
                metadata.put("systemModel.snapshotId", request.execution().snapshotId());
                metadata.put("systemModel.configVersion", request.execution().configVersion());
                metadata.put("systemModel.feature", route.feature());
                metadata.put("systemModel.finalUrl", uri.toString());
                metadata.put("providerRetryCount", attempt);
                return new LlmResult(
                        "openai-compatible",
                        route.model(),
                        content.asText(),
                        root.path("choices").path(0).path("finish_reason").asText(),
                        new LlmUsage(
                                integer(usage, "prompt_tokens"),
                                integer(usage, "completion_tokens"),
                                integer(usage, "total_tokens")),
                        Duration.ofNanos(System.nanoTime() - start),
                        metadata);
            } catch (SystemModelCallFailure safe) {
                if (!safe.details().retryable() || attempt + 1 >= attempts) throw safe;
            } catch (Exception ignored) {
                throw invalid();
            }
        }
        throw invalid();
    }

    private static Integer integer(com.fasterxml.jackson.databind.JsonNode root, String name) {
        var n = root.path(name);
        return n.isIntegralNumber() && n.canConvertToInt() && n.intValue() >= 0
                ? n.intValue()
                : null;
    }

    private static long minimum(Long configured, Long requested, long fallback) {
        return configured == null
                ? (requested == null ? fallback : requested)
                : requested == null ? configured : Math.min(configured, requested);
    }

    private static SystemModelCallFailure invalid() {
        return new SystemModelCallFailure(
                "OUTPUT_INVALID", LlmProviderFailureCategory.OUTPUT_INVALID, null, false);
    }

    private static SystemModelCallFailure statusFailure(int status) {
        var category =
                status == 401 || status == 403
                        ? LlmProviderFailureCategory.AUTHENTICATION
                        : status == 404
                                ? LlmProviderFailureCategory.MODEL_NOT_FOUND
                                : status == 429
                                        ? LlmProviderFailureCategory.RATE_LIMIT
                                        : status >= 500
                                                ? LlmProviderFailureCategory.SERVER_ERROR
                                                : LlmProviderFailureCategory.INVALID_REQUEST;
        return new SystemModelCallFailure(
                category.name(), category, status, status == 429 || status >= 500);
    }
}
