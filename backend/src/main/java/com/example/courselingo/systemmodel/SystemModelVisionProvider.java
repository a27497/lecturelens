package com.example.courselingo.systemmodel;

import com.example.courselingo.ai.llm.*;
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
        long started = System.nanoTime();
        var ref = request.route().execution();
        var resolved = executions.route(ref, "VISION_FRAME_ANALYSIS");
        String key = resolved.hasKey() ? executions.credential(ref, "VISION_FRAME_ANALYSIS") : null;
        boolean database = "DATABASE".equals(resolved.source());
        OpenAiCompatibleLlmClient client;
        if (database) {
            urls.normalize(resolved.baseUrl());
            long budget = (resolved.timeoutMillis() == null
                    ? properties.getTimeout() : Duration.ofMillis(resolved.timeoutMillis())).toNanos();
            int limit = resolved.maxAttempts() == null ? 1 : resolved.maxAttempts();
            var attempts = new java.util.concurrent.atomic.AtomicInteger();
            // The legacy adapter can restart its retry loop after an exception. Database
            // routes must keep one frozen attempt count and deadline across that loop.
            client = r -> {
                long remaining = Math.min(r.timeout().toNanos(), budget - (System.nanoTime() - started));
                if (remaining <= 0 || Thread.currentThread().isInterrupted())
                    throw new SystemModelCallFailure("TIMEOUT",
                            LlmProviderFailureCategory.TIMEOUT, null, false);
                if (attempts.incrementAndGet() > limit)
                    throw new SystemModelCallFailure("ATTEMPTS_EXHAUSTED",
                            LlmProviderFailureCategory.INVALID_REQUEST, null, false);
                // The protected transport owns DNS validation within this remaining budget.
                return http.complete(new OpenAiCompatibleChatCompletionRequest(
                        r.uri(), r.headers(), r.method(), r.contentType(), r.body(), Duration.ofNanos(remaining)));
            };
        } else {
            client = new JavaHttpOpenAiCompatibleLlmClient(Duration.ofSeconds(5));
        }
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
                r.capabilities().stream()
                        .map(
                                value ->
                                        value.equals("ASR")
                                                ? ModelCapability.AUDIO_TRANSCRIPTION
                                                : ModelCapability.valueOf(value))
                        .collect(Collectors.toSet()),
                r.temperature(),
                r.maxTokens(),
                r.timeoutMillis() == null ? null : Duration.ofMillis(r.timeoutMillis()),
                r.maxAttempts(),
                ref);
    }
}
