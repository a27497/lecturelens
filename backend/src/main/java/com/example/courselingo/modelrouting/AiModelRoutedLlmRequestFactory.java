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

    public AiModelRoutedLlmRequestFactory(AiModelRouter router) {
        this.router = router;
    }

    public LlmRequest apply(AiModelStage stage, LlmRequest request) {
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
