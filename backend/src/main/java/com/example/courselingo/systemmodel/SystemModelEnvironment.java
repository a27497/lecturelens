package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.OpenAiCompatibleLlmProperties;
import com.example.courselingo.modelrouting.AiModelRouter;
import com.example.courselingo.modelrouting.AiModelStage;

import org.springframework.core.env.Environment;

import java.util.LinkedHashMap;
import java.util.Map;
import java.util.Set;
import java.util.stream.Collectors;

final class SystemModelEnvironment {
    record Captured(
            Map<String, SystemModelStoredConfig.Default> defaults,
            String fingerprint,
            boolean fullText) {}

    private final Environment environment;
    private final AiModelRouter router;
    private final OpenAiCompatibleLlmProperties text;
    private final SystemModelSecretCipher cipher;

    SystemModelEnvironment(
            Environment environment,
            AiModelRouter router,
            OpenAiCompatibleLlmProperties text,
            SystemModelSecretCipher cipher) {
        this.environment = environment;
        this.router = router;
        this.text = text;
        this.cipher = cipher;
    }

    Captured capture() {
        var defaults = new LinkedHashMap<String, SystemModelStoredConfig.Default>();
        StringBuilder identity = new StringBuilder();
        boolean fullText =
                environment.getProperty(
                        "courselingo.subtitle.translation.full-text.enabled", Boolean.class, true);
        identity.append(fullText);
        for (AiModelStage stage : AiModelStage.values()) {
            if (!stage.active() && stage != AiModelStage.VISION_FRAME_ANALYSIS) continue;
            boolean vision = stage == AiModelStage.VISION_FRAME_ANALYSIS;
            String source =
                    text.isEnabled() || vision
                            ? "ENV"
                            : environment.getProperty(
                                            "courselingo.ai.llm.demo-mock.enabled",
                                            Boolean.class,
                                            false)
                                    ? "MOCK"
                                    : "UNCONFIGURED";
            String base = text.getBaseUrl(), model = text.getModel(), key = text.getApiKey();
            Double temperature = text.getTemperature();
            Integer maxTokens = text.getMaxTokens(), attempts = 2;
            Long timeout = text.getRequestTimeout().toMillis();
            Set<String> capabilities =
                    stage.requiredCapabilities().stream()
                            .map(Enum::name)
                            .collect(Collectors.toSet());
            if (router.enabled()) {
                try {
                    var route = router.route(stage);
                    base = route.baseUrl();
                    model = route.modelName();
                    if (route.temperature() != null) temperature = route.temperature();
                    if (route.maxTokens() != null) maxTokens = route.maxTokens();
                    if (route.timeout() != null) timeout = route.timeout().toMillis();
                    if (route.maxAttempts() != null) attempts = route.maxAttempts();
                    if (vision) key = environment.getProperty(route.apiKeyEnvName(), "");
                } catch (RuntimeException failure) {
                    if (!vision) throw failure;
                    source = "UNCONFIGURED";
                    key = "";
                }
            } else if (vision) {
                source = "UNCONFIGURED";
                key = "";
            }
            String credentialId = "env-" + stage.name();
            boolean hasKey = key != null && !key.isBlank();
            var encrypted = hasKey ? cipher.encrypt(credentialId, key) : null;
            var route =
                    new SystemModelResolvedRoute(
                            stage.name(),
                            source,
                            SystemModelProtocol.OPENAI_CHAT,
                            credentialId,
                            null,
                            null,
                            base,
                            model,
                            capabilities,
                            temperature,
                            maxTokens,
                            timeout,
                            attempts,
                            hasKey,
                            encrypted == null ? null : encrypted.keyLast4());
            defaults.put(
                    stage.name(),
                    new SystemModelStoredConfig.Default(
                            route, encrypted == null ? null : encrypted.ciphertext()));
            identity.append('\n').append(route).append('\n').append(key == null ? "" : key);
        }
        captureAsr(defaults, identity);
        return new Captured(
                Map.copyOf(defaults), SystemModelConfigCodec.sha256(identity.toString()), fullText);
    }

    private void captureAsr(
            Map<String, SystemModelStoredConfig.Default> defaults, StringBuilder identity) {
        var binder = org.springframework.boot.context.properties.bind.Binder.get(environment);
        var bailian =
                binder.bind(
                                "courselingo.ai.asr.bailian",
                                com.example.courselingo.ai.asr.BailianAsrProperties.class)
                        .orElseGet(com.example.courselingo.ai.asr.BailianAsrProperties::new);
        var silicon =
                binder.bind(
                                "courselingo.ai.asr.silicon-flow",
                                com.example.courselingo.ai.asr.SiliconFlowAsrProperties.class)
                        .orElseGet(com.example.courselingo.ai.asr.SiliconFlowAsrProperties::new);
        var mock =
                binder.bind(
                                "courselingo.ai.asr.mock",
                                com.example.courselingo.ai.asr.MockAsrProperties.class)
                        .orElseGet(com.example.courselingo.ai.asr.MockAsrProperties::new);
        String selected = com.example.courselingo.ai.asr.AsrProviderSelection.selected(environment);
        boolean isBailian = selected.equals("bailian"), isSilicon = selected.equals("siliconflow");
        String key = isBailian ? bailian.getApiKey() : isSilicon ? silicon.getApiKey() : "";
        String credentialId = "env-ASR_TRANSCRIPTION";
        var encrypted = key != null && !key.isBlank() ? cipher.encrypt(credentialId, key) : null;
        var route =
                new SystemModelResolvedRoute(
                        "ASR_TRANSCRIPTION",
                        isBailian || isSilicon
                                ? "ENV"
                                : selected.equals("mock") ? "MOCK" : "UNCONFIGURED",
                        isBailian
                                ? SystemModelProtocol.BAILIAN_ASR
                                : isSilicon ? SystemModelProtocol.SILICONFLOW_ASR : null,
                        credentialId,
                        null,
                        null,
                        isBailian ? bailian.getEndpoint() : isSilicon ? silicon.getBaseUrl() : null,
                        isBailian ? bailian.getModel() : isSilicon ? silicon.getModel() : null,
                        Set.of("ASR"),
                        null,
                        null,
                        isBailian
                                ? bailian.getRequestTimeout().toMillis()
                                : silicon.getRequestTimeout().toMillis(),
                        null,
                        encrypted != null,
                        encrypted == null ? null : encrypted.keyLast4(),
                        com.example.courselingo.ai.asr.AsrConfigurationSnapshot.capture(
                                bailian, silicon, mock));
        defaults.put(
                "ASR_TRANSCRIPTION",
                new SystemModelStoredConfig.Default(
                        route, encrypted == null ? null : encrypted.ciphertext()));
        // Stable map ordering prevents identical vocabulary from creating another startup version.
        identity.append('\n')
                .append(route)
                .append('\n')
                .append(new java.util.TreeMap<>(route.asr().vocabulary()))
                .append('\n')
                .append(key == null ? "" : key);
    }
}
