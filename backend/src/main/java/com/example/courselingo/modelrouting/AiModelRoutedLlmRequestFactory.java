package com.example.courselingo.modelrouting;

import com.example.courselingo.ai.llm.LlmRequest;
import java.util.LinkedHashMap;
import java.util.Map;

public class AiModelRoutedLlmRequestFactory {

    public static final String METADATA_STAGE = "modelRouting.stage";
    public static final String METADATA_PROFILE_CODE = "modelRouting.profileCode";
    public static final String METADATA_PROVIDER_TYPE = "modelRouting.providerType";
    public static final String METADATA_MODEL_NAME = "modelRouting.modelName";
    public static final String METADATA_BASE_URL = "modelRouting.baseUrl";

    private final AiModelRouter router;
    private final com.example.courselingo.systemmodel.SystemModelExecutionService executions;

    public AiModelRoutedLlmRequestFactory(AiModelRouter router) {
        this(router, null);
    }

    public AiModelRoutedLlmRequestFactory(
            AiModelRouter router,
            com.example.courselingo.systemmodel.SystemModelExecutionService executions) {
        this.router = router;
        this.executions = executions;
    }

    public LlmRequest apply(AiModelStage stage, LlmRequest request) {
        if (request != null && request.execution() != null) {
            if (executions == null)
                throw new com.example.courselingo.common.exception.BusinessException(
                        com.example.courselingo.common.error.ErrorCode.SYSTEM_MODEL_DISABLED);
            var resolved = executions.route(request.execution(), stage.name());
            Map<String, Object> metadata = new LinkedHashMap<>(request.metadata());
            metadata.put(METADATA_STAGE, stage.name());
            metadata.put(METADATA_MODEL_NAME, resolved.model());
            metadata.put(METADATA_BASE_URL, resolved.baseUrl());
            metadata.put("systemModel.source", resolved.source());
            return new LlmRequest(
                    request.requestId(),
                    request.taskId(),
                    request.messages(),
                    request.timeout() == null && resolved.timeoutMillis() != null
                            ? java.time.Duration.ofMillis(resolved.timeoutMillis())
                            : request.timeout(),
                    request.temperature() == null ? resolved.temperature() : request.temperature(),
                    request.maxTokens() == null ? resolved.maxTokens() : request.maxTokens(),
                    request.maxAttempts() == null ? resolved.maxAttempts() : request.maxAttempts(),
                    metadata,
                    request.responseFormat(),
                    request.execution());
        }
        if (request == null || router == null || !router.enabled()) {
            return request;
        }
        AiModelRoute route = router.route(stage);
        Map<String, Object> metadata = new LinkedHashMap<>(request.metadata());
        metadata.put(METADATA_STAGE, route.stage().name());
        metadata.put(METADATA_PROFILE_CODE, route.profileCode());
        metadata.put(METADATA_PROVIDER_TYPE, route.providerType());
        metadata.put(METADATA_MODEL_NAME, route.modelName());
        metadata.put(METADATA_BASE_URL, route.baseUrl());
        return new LlmRequest(
            request.requestId(),
            request.taskId(),
            request.messages(),
            request.timeout() == null ? route.timeout() : request.timeout(),
            request.temperature() == null ? route.temperature() : request.temperature(),
            request.maxTokens() == null ? route.maxTokens() : request.maxTokens(),
            request.maxAttempts() == null ? route.maxAttempts() : request.maxAttempts(),
            metadata,
            request.responseFormat()
        );
    }
}
