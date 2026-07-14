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
    Integer maxAttempts
) {

    public AiModelRoute {
        capabilities = capabilities == null ? Set.of() : Set.copyOf(capabilities);
    }
}
