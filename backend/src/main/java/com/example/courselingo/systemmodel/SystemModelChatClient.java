package com.example.courselingo.systemmodel;

import com.example.courselingo.subtitle.diagnostic.TranslationCallDiagnostics;

import com.example.courselingo.ai.llm.*;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Duration;
import java.util.LinkedHashMap;
import java.util.Locale;
import java.util.Map;

final class SystemModelChatClient {
    private final OpenAiCompatibleLlmClient http;
    private final SystemModelUrlPolicy addresses;
    private final TranslationCallDiagnostics diagnostics;
    private final ObjectMapper json = new ObjectMapper();

    SystemModelChatClient(OpenAiCompatibleLlmClient http, SystemModelUrlPolicy addresses) {
        this(http, addresses, null);
    }

    SystemModelChatClient(OpenAiCompatibleLlmClient http, SystemModelUrlPolicy addresses,
            TranslationCallDiagnostics diagnostics) {
        this.diagnostics = diagnostics;
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
        boolean translationV2 = com.example.courselingo.ai.llm.TranslationResponseDecoder.enabled(request);
        if (translationV2) attempts = 1;
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
        com.example.courselingo.ai.llm.TranslationResponseDecoder.applyOptions(body,route.baseUrl(),route.model(),request);
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
            String diagnosticId = diagnostics != null && request.execution() != null
                    && "TRANSLATION_FULL_TEXT".equals(route.feature()) ? java.util.UUID.randomUUID().toString() : null;
            String observedBody = null;
            Integer observedStatus = null;
            com.fasterxml.jackson.databind.JsonNode observedRoot = null;
            String observedReason = "TRANSPORT";
            long attemptStarted = System.nanoTime();
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
                observedBody = response.body();
                int status = response.statusCode();
                observedStatus = status;
                if (translationV2) {
                    try { observedRoot = json.readTree(response.body()); } catch (Exception ignored) { }
                    var metadata = new LinkedHashMap<String,Object>();
                    metadata.put("systemModel.snapshotId",request.execution().snapshotId());
                    metadata.put("systemModel.configVersion",request.execution().configVersion());
                    metadata.put("systemModel.feature",route.feature());
                    metadata.put("systemModel.finalUrl",uri.toString());
                    metadata.put("providerRetryCount",0);
                    if (diagnosticId != null) metadata.put(TranslationCallDiagnostics.RESULT_ID,diagnosticId);
                    var result = com.example.courselingo.ai.llm.TranslationResponseDecoder.decode(response,route.model(),metadata);
                    observedReason="PASSED";
                    return result;
                }
                observedReason = "HTTP_STATUS";
                if (status < 200 || status >= 300) throw statusFailure(status);
                observedReason = "ENVELOPE_JSON_INVALID";
                var root = json.readTree(response.body());
                observedRoot = root;
                observedReason = "CONTENT_FIELD_INVALID";
                var content = root.path("choices").path(0).path("message").path("content");
                if (!content.isTextual() || content.asText().isBlank()) {
                    observedReason = content.isMissingNode() ? "CONTENT_MISSING"
                            : content.isNull() ? "CONTENT_NULL" : content.isTextual() ? "CONTENT_EMPTY" : "CONTENT_NON_STRING";
                    throw invalid();
                }
                if (request.responseFormat() == LlmResponseFormat.JSON_OBJECT) {
                    observedReason = "CONTENT_JSON_INVALID";
                    if (!json.readTree(content.asText()).isObject()) {
                        observedReason = "CONTENT_NOT_OBJECT";
                        throw invalid();
                    }
                }
                observedReason = "PASSED";
                var usage = root.path("usage");
                var metadata = new LinkedHashMap<String, Object>();
                metadata.put("systemModel.snapshotId", request.execution().snapshotId());
                metadata.put("systemModel.configVersion", request.execution().configVersion());
                metadata.put("systemModel.feature", route.feature());
                metadata.put("systemModel.finalUrl", uri.toString());
                metadata.put("providerRetryCount", attempt);
                if (diagnosticId != null) metadata.put(
                        TranslationCallDiagnostics.RESULT_ID, diagnosticId);
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
            } catch (com.example.courselingo.ai.llm.TranslationFailure safe) {
                observedReason = safe.observationReason();
                throw safe;
            } catch (SystemModelCallFailure safe) {
                if (!"OUTPUT_INVALID".equals(safe.category())) observedReason = safe.category();
                if (!safe.details().retryable() || attempt + 1 >= attempts) throw safe;
            } catch (Exception ignored) {
                if (translationV2) {
                    var safe = com.example.courselingo.ai.llm.TranslationFailure.from(ignored);
                    observedReason = safe.reason().name();
                    throw safe;
                }
                throw invalid();
            } finally {
                if (diagnosticId != null) diagnostics.provider(diagnosticId, request, route.model(), attempt + 1,
                        observedStatus, observedBody, apiKey, observedRoot, observedReason,
                        Duration.ofNanos(System.nanoTime() - attemptStarted).toMillis());
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
