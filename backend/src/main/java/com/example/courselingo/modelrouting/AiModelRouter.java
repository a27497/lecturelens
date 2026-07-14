package com.example.courselingo.modelrouting;

import java.time.Duration;
import java.util.Locale;
import java.util.Map;
import java.util.Set;

public class AiModelRouter {

    private final AiModelRoutingProperties properties;

    public AiModelRouter(AiModelRoutingProperties properties) {
        this.properties = properties == null ? new AiModelRoutingProperties() : properties;
        validateActiveRoutes();
    }

    public boolean enabled() {
        return properties.isEnabled();
    }

    public AiModelRoute route(AiModelStage stage) {
        if (!properties.isEnabled()) {
            throw new ModelRoutingException("AI model routing is disabled");
        }
        if (stage == null) {
            throw new ModelRoutingException("AI model routing stage is required");
        }
        String profileCode = clean(properties.getRoutes().get(stage));
        if (profileCode == null) {
            throw new ModelRoutingException("AI model route is missing for stage " + stage.name());
        }
        AiModelProfile profile = properties.getProfiles().get(profileCode);
        if (profile == null) {
            throw new ModelRoutingException("AI model profile is missing: " + profileCode);
        }
        validateProfile(stage, profileCode, profile);
        return toRoute(stage, profileCode, profile);
    }

    private void validateActiveRoutes() {
        if (!properties.isEnabled()) {
            return;
        }
        for (AiModelStage stage : AiModelStage.activeStages()) {
            route(stage);
        }
    }

    private static void validateProfile(AiModelStage stage, String profileCode, AiModelProfile profile) {
        if (!profile.isEnabled()) {
            throw new ModelRoutingException("AI model profile is disabled: " + profileCode + " stage=" + stage.name());
        }
        requireText(profile.getProviderType(), "provider type", profileCode, stage);
        requireText(profile.getBaseUrl(), "base URL", profileCode, stage);
        requireText(profile.getModelName(), "model name", profileCode, stage);
        requireText(profile.getApiKeyEnvName(), "API key env name", profileCode, stage);
        validateCapabilities(stage, profileCode, profile.getCapabilities());
        validateTuning(profileCode, stage, profile);
    }

    private static void validateCapabilities(AiModelStage stage, String profileCode, Set<ModelCapability> capabilities) {
        Set<ModelCapability> configured = capabilities == null ? Set.of() : capabilities;
        for (ModelCapability capability : stage.requiredCapabilities()) {
            if (!configured.contains(capability)) {
                throw new ModelRoutingException(
                    "AI model profile " + profileCode + " for stage " + stage.name()
                        + " is missing capability " + capability.name()
                );
            }
        }
    }

    private static void validateTuning(String profileCode, AiModelStage stage, AiModelProfile profile) {
        Double temperature = profile.getTemperature();
        if (temperature != null && (temperature < 0.0d || temperature > 2.0d)) {
            throw invalid(profileCode, stage, "temperature must be between 0 and 2");
        }
        Integer maxTokens = profile.getMaxTokens();
        if (maxTokens != null && maxTokens <= 0) {
            throw invalid(profileCode, stage, "max tokens must be positive");
        }
        Duration timeout = profile.getTimeout();
        if (timeout != null && (timeout.isZero() || timeout.isNegative())) {
            throw invalid(profileCode, stage, "timeout must be positive");
        }
        Integer maxAttempts = profile.getMaxAttempts();
        if (maxAttempts != null && maxAttempts <= 0) {
            throw invalid(profileCode, stage, "max attempts must be positive");
        }
    }

    private static AiModelRoute toRoute(AiModelStage stage, String profileCode, AiModelProfile profile) {
        return new AiModelRoute(
            stage,
            profileCode,
            clean(profile.getDisplayName()),
            clean(profile.getProviderType()).toLowerCase(Locale.ROOT),
            clean(profile.getBaseUrl()),
            clean(profile.getModelName()),
            clean(profile.getApiKeyEnvName()),
            profile.getCapabilities(),
            profile.getTemperature(),
            profile.getMaxTokens(),
            profile.getTimeout(),
            profile.getMaxAttempts()
        );
    }

    private static String requireText(String value, String field, String profileCode, AiModelStage stage) {
        String cleaned = clean(value);
        if (cleaned == null) {
            throw invalid(profileCode, stage, field + " is required");
        }
        return cleaned;
    }

    private static ModelRoutingException invalid(String profileCode, AiModelStage stage, String reason) {
        return new ModelRoutingException(
            "AI model profile is invalid: " + reason + " profile=" + profileCode + " stage=" + stage.name()
        );
    }

    private static String clean(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return value.strip();
    }
}
