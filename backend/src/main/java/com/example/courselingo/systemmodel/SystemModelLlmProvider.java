package com.example.courselingo.systemmodel;

import com.example.courselingo.subtitle.diagnostic.TranslationCallDiagnostics;

import com.example.courselingo.ai.llm.*;
import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;

import java.time.Duration;
import java.util.LinkedHashMap;

public final class SystemModelLlmProvider implements LlmProvider {
    private final SystemModelExecutionService executions;
    private final SystemModelChatClient chat;
    private final OpenAiCompatibleLlmClient legacy;

    SystemModelLlmProvider(
            SystemModelExecutionService executions,
            OpenAiCompatibleLlmClient http,
            SystemModelUrlPolicy addresses,
            OpenAiCompatibleLlmClient legacy) {
        this(executions, http, addresses, legacy, null);
    }

    SystemModelLlmProvider(SystemModelExecutionService executions, OpenAiCompatibleLlmClient http,
            SystemModelUrlPolicy addresses, OpenAiCompatibleLlmClient legacy,
            TranslationCallDiagnostics diagnostics) {
        this.executions = executions;
        this.chat = new SystemModelChatClient(http, addresses, diagnostics);
        this.legacy = legacy;
    }

    @Override
    public String providerName() {
        return "system-model-router";
    }

    @Override
    public LlmResult generate(LlmRequest request) {
        long started = System.nanoTime();
        String outcome = "FAILED", category = "UNKNOWN";
        try (var ignored=com.example.courselingo.ai.llm.ModelCallScope.open(request==null?null:new com.example.courselingo.ai.llm.ModelCallScope.Context(
                request.execution(),(String)request.metadata().get(AiModelRoutedLlmRequestFactory.METADATA_STAGE),null,
                (String)request.metadata().get("translationAttemptId"),request.requestId(),null,null,null))) {
            LlmResult result = generateFrozen(request);
            outcome = "SUCCEEDED";
            category = "NONE";
            return result;
        } catch (com.example.courselingo.ai.llm.TranslationFailure failure) {
            category = failure.reason().name();
            throw failure;
        } catch (SystemModelCallFailure failure) {
            category = failure.category();
            throw failure;
        } catch (com.example.courselingo.common.exception.BusinessException failure) {
            category = failure.errorCode().code();
            throw failure;
        } finally {
            var ref = request == null ? null : request.execution();
            org.slf4j.LoggerFactory.getLogger(getClass())
                    .info(
                            "event=system_model_call_completed taskId={} snapshotId={}"
                                + " configVersion={} outcome={} category={} durationMillis={}",
                            ref == null ? null : ref.taskId(),
                            ref == null ? null : ref.snapshotId(),
                            ref == null ? null : ref.configVersion(),
                            outcome,
                            category,
                            Duration.ofNanos(System.nanoTime() - started).toMillis());
        }
    }

    private LlmResult generateFrozen(LlmRequest request) {
        if (request == null)
            throw new SystemModelCallFailure(
                    "REQUEST_INVALID", LlmProviderFailureCategory.INVALID_REQUEST, null, false);
        if (request.execution() == null || !request.taskId().equals(request.execution().taskId()))
            throw new SystemModelCallFailure(
                    "SNAPSHOT_REQUIRED", LlmProviderFailureCategory.INVALID_REQUEST, null, false);
        String feature =
                (String) request.metadata().get(AiModelRoutedLlmRequestFactory.METADATA_STAGE);
        var route = executions.route(request.execution(), feature);
        if ("DATABASE".equals(route.source()))
            return chat.generate(
                    request, route, executions.credential(request.execution(), feature));
        if ("MOCK".equals(route.source())) return new DemoMockLlmProvider().generate(request);
        if (!"ENV".equals(route.source()))
            throw new SystemModelCallFailure(
                    "NOT_CONFIGURED", LlmProviderFailureCategory.INVALID_REQUEST, null, false);
        var properties = new OpenAiCompatibleLlmProperties();
        String apiKey = executions.credential(request.execution(), feature);
        properties.setApiKey(apiKey);
        properties.setBaseUrl(route.baseUrl());
        properties.setModel(route.model());
        properties.setTemperature(route.temperature());
        properties.setMaxTokens(route.maxTokens());
        properties.setRequestTimeout(Duration.ofMillis(route.timeoutMillis()));
        try {
            LlmResult result =
                    new OpenAiCompatibleLlmProvider(properties, this::safeLegacyResponse)
                            .generate(request);
            var metadata = new LinkedHashMap<>(result.metadata());
            metadata.put("systemModel.snapshotId", request.execution().snapshotId());
            metadata.put("systemModel.configVersion", request.execution().configVersion());
            metadata.put("systemModel.feature", feature);
            return new LlmResult(
                    result.provider(),
                    result.model(),
                    result.content(),
                    result.finishReason(),
                    result.usage(),
                    result.duration(),
                    metadata);
        } catch (com.example.courselingo.ai.llm.TranslationFailure failure) {
            throw failure;
        } catch (RuntimeException failure) {
            var details = LlmProviderFailureClassifier.from(failure);
            throw new SystemModelCallFailure(
                    details.category().name(),
                    details.category(),
                    details.httpStatus(),
                    details.retryable());
        }
    }

    private OpenAiCompatibleClientResponse safeLegacyResponse(
            OpenAiCompatibleChatCompletionRequest request) {
        OpenAiCompatibleClientResponse result;
        try {
            result = legacy.complete(request);
        } catch (com.example.courselingo.ai.llm.TranslationFailure safe) {
            throw safe;
        } catch (RuntimeException failure) {
            var details = LlmProviderFailureClassifier.from(failure);
            var category =
                    details.category() == LlmProviderFailureCategory.UNKNOWN
                            ? LlmProviderFailureCategory.NETWORK
                            : details.category();
            throw new SystemModelCallFailure(
                    category.name(), category, details.httpStatus(), details.retryable());
        }
        var headers = new java.util.LinkedHashMap<String, java.util.List<String>>();
        result.headers()
                .forEach(
                        (name, values) -> {
                            if (name.equalsIgnoreCase("retry-after"))
                                headers.put(
                                        name,
                                        values.stream()
                                                .filter(v -> v.matches("[0-9]{1,3}"))
                                                .toList());
                        });
        String body = result.body();
        if (result.statusCode() < 200 || result.statusCode() >= 300) {
            var category =
                    LlmProviderFailureClassifier.classify(result.statusCode(), body, null)
                            .category();
            body =
                    category == LlmProviderFailureCategory.UNSUPPORTED_RESPONSE_FORMAT
                            ? "{\"error\":{\"code\":\"UNSUPPORTED_RESPONSE_FORMAT\",\"message\":\"response_format"
                                  + " unsupported\"}}"
                            : "{\"error\":{\"code\":\"" + category.name() + "\"}}";
        }
        return new OpenAiCompatibleClientResponse(
                result.statusCode(), body, headers, result.duration());
    }
}
