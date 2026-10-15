package com.example.courselingo.modelrouting;

import java.time.Duration;
import java.util.Set;

public record AiModelRoute(
    AiModelStage stage,
    String profileCode,
    String displayName,
    String providerType,
    String baseUrl,
    String modelName,
    String apiKeyEnvName,
    Set<ModelCapability> capabilities,
    Double temperature,
    Integer maxTokens,
    Duration timeout,
    Integer maxAttempts,
        com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {

    public AiModelRoute {
        capabilities = capabilities == null ? Set.of() : Set.copyOf(capabilities);
    }

    public AiModelRoute(
            AiModelStage stage,
            String profileCode,
            String displayName,
            String providerType,
            String baseUrl,
            String modelName,
            String apiKeyEnvName,
            Set<ModelCapability> capabilities,
            Double temperature,
            Integer maxTokens,
            Duration timeout,
            Integer maxAttempts) {
        this(
                stage,
                profileCode,
                displayName,
                providerType,
                baseUrl,
                modelName,
                apiKeyEnvName,
                capabilities,
                temperature,
                maxTokens,
                timeout,
                maxAttempts,
                null);
    }
}
