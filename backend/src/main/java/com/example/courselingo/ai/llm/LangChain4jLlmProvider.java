package com.example.courselingo.ai.llm;

import java.net.URI;
import java.net.URISyntaxException;
import java.time.Duration;

public class LangChain4jLlmProvider implements LlmProvider {

    public static final String PROVIDER_NAME = "langchain4j-openai-compatible";
    private static final int MAX_MODEL_LENGTH = 128;

    private final LangChain4jLlmProperties properties;
    private final LangChain4jChatModelClient client;

    public LangChain4jLlmProvider(LangChain4jLlmProperties properties, LangChain4jChatModelClient client) {
        this.properties = properties;
        this.client = client;
    }

    @Override
    public LlmResult generate(LlmRequest request) {
        LlmRequestValidator.validate(request);
        ValidatedSettings settings = validateSettings(request);
        LangChain4jClientResponse response = callClient(request, settings);
        return LangChain4jResultMapper.toLlmResult(providerName(), settings.model(), response);
    }

    @Override
    public String providerName() {
        return PROVIDER_NAME;
    }

    private LangChain4jClientResponse callClient(LlmRequest request, ValidatedSettings settings) {
        LangChain4jClientRequest clientRequest = new LangChain4jClientRequest(
            LangChain4jMessageMapper.toLangChain4jMessages(request),
            settings.model(),
            settings.requestTimeout(),
            settings.temperature(),
            settings.maxTokens()
        );
        try {
            return client.complete(clientRequest);
        } catch (LangChain4jLlmException exception) {
            throw exception;
        } catch (RuntimeException exception) {
            throw new LangChain4jLlmException("LangChain4j LLM network call failed", true, exception);
        }
    }

    private ValidatedSettings validateSettings(LlmRequest request) {
        requireText(properties.getApiKey(), "API key is required");
        String model = requireText(properties.getModel(), "model is required");
        if (model.length() > MAX_MODEL_LENGTH) {
            throw invalid("model is too long");
        }
        validateBaseUrl(properties.getBaseUrl());
        positiveDuration(properties.getConnectTimeout(), "connect timeout must be positive");
        Duration requestTimeout = request.timeout() == null
            ? positiveDuration(properties.getRequestTimeout(), "request timeout must be positive")
            : request.timeout();
        Double temperature = request.temperature() == null ? properties.getTemperature() : request.temperature();
        Integer maxTokens = request.maxTokens() == null ? properties.getMaxTokens() : request.maxTokens();
        validateProviderDefaults(temperature, maxTokens);
        return new ValidatedSettings(model, requestTimeout, temperature, maxTokens);
    }

    private void validateBaseUrl(String baseUrl) {
        String trimmed = requireText(baseUrl, "base URL is required");
        try {
            URI uri = new URI(trimmed);
            String scheme = uri.getScheme();
            if (scheme == null || (!scheme.equalsIgnoreCase("http") && !scheme.equalsIgnoreCase("https"))) {
                throw invalid("base URL must use http or https");
            }
            if (uri.getRawAuthority() == null || uri.getRawAuthority().isBlank()) {
                throw invalid("base URL host is required");
            }
        } catch (URISyntaxException exception) {
            throw new LangChain4jLlmException("LangChain4j LLM configuration is invalid: base URL is invalid", false, exception);
        }
    }

    private void validateProviderDefaults(Double temperature, Integer maxTokens) {
        if (temperature == null || temperature < 0.0 || temperature > 2.0) {
            throw invalid("temperature must be between 0 and 2");
        }
        if (maxTokens == null || maxTokens <= 0) {
            throw invalid("max completion count must be positive");
        }
        if (maxTokens > LlmRequestValidator.MAX_TOKENS) {
            throw invalid("max completion count exceeds limit");
        }
    }

    private static String requireText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw invalid(message);
        }
        return value.strip();
    }

    private static Duration positiveDuration(Duration duration, String message) {
        if (duration == null || duration.isZero() || duration.isNegative()) {
            throw invalid(message);
        }
        return duration;
    }

    private static LangChain4jLlmException invalid(String message) {
        return new LangChain4jLlmException(
            "LangChain4j LLM configuration is invalid: " + message,
            false
        );
    }

    private record ValidatedSettings(
        String model,
        Duration requestTimeout,
        Double temperature,
        Integer maxTokens
    ) {
    }
}
