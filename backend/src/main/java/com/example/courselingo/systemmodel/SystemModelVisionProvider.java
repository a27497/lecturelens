package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.JavaHttpOpenAiCompatibleLlmClient;
import com.example.courselingo.ai.llm.OpenAiCompatibleLlmClient;
import com.example.courselingo.modelrouting.*;
import com.example.courselingo.vision.analysis.*;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.time.Duration;
import java.util.stream.Collectors;

final class SystemModelVisionProvider implements VisionModelProvider {
    private final SystemModelExecutionService executions;
    private final OpenAiCompatibleLlmClient http;
    private final VisionAnalysisProperties properties;
    private final SystemModelUrlPolicy urls;

    SystemModelVisionProvider(
            SystemModelExecutionService executions,
            OpenAiCompatibleLlmClient http,
            VisionAnalysisProperties properties,
            SystemModelUrlPolicy urls) {
        this.executions = executions;
        this.http = http;
        this.properties = properties;
        this.urls = urls;
    }

    @Override
    public String providerName() {
        return "system-model-vision";
    }

    @Override
    public VisionAnalysisResult analyze(VisionAnalysisRequest request) {
        var ref = request.route().execution();
        var resolved = executions.route(ref, "VISION_FRAME_ANALYSIS");
        String key = resolved.hasKey() ? executions.credential(ref, "VISION_FRAME_ANALYSIS") : null;
        boolean database = "DATABASE".equals(resolved.source());
        OpenAiCompatibleLlmClient client =
                database
                        ? r -> {
                            urls.checkDestination(r.uri());
                            return http.complete(r);
                        }
                        : new JavaHttpOpenAiCompatibleLlmClient(Duration.ofSeconds(5));
        var provider =
                new OpenAiCompatibleVisionProvider(
                        properties, client, ignored -> key, new ObjectMapper(), database);
        return provider.analyze(request);
    }

    static AiModelRoute route(SystemModelExecutionService executions, SystemModelExecutionRef ref) {
        var r = executions.route(ref, "VISION_FRAME_ANALYSIS");
        return new AiModelRoute(
                AiModelStage.VISION_FRAME_ANALYSIS,
                "system-" + ref.configVersion(),
                "System vision",
                "openai-compatible",
                r.baseUrl(),
                r.model(),
                "system-version-credential",
                r.capabilities().stream().map(ModelCapability::valueOf).collect(Collectors.toSet()),
                r.temperature(),
                r.maxTokens(),
                r.timeoutMillis() == null ? null : Duration.ofMillis(r.timeoutMillis()),
                r.maxAttempts(),
                ref);
    }
}
