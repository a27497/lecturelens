package com.example.courselingo.ai.llm;

import com.example.courselingo.modelrouting.AiModelRoutedLlmRequestFactory;
import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.URISyntaxException;
import java.time.Duration;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Optional;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

public class OpenAiCompatibleLlmProvider implements LlmProvider {

    private static final Logger log = LoggerFactory.getLogger(OpenAiCompatibleLlmProvider.class);
    public static final String PROVIDER_NAME = "openai-compatible";
    static final String CHAT_COMPLETIONS_PATH = "/chat/completions";
    private static final String DEFAULT_API_PATH_PREFIX = "/v1";
    private static final int MAX_MODEL_LENGTH = 128;
    private static final int MAX_RESPONSE_SUMMARY_LENGTH = 1000;
    private static final int MAX_ATTEMPTS = 2;

    private final OpenAiCompatibleLlmProperties properties;
    private final OpenAiCompatibleLlmClient client;
    private final ObjectMapper objectMapper;

    public OpenAiCompatibleLlmProvider(OpenAiCompatibleLlmProperties properties, OpenAiCompatibleLlmClient client) {
        this(properties, client, new ObjectMapper());
    }

    OpenAiCompatibleLlmProvider(
        OpenAiCompatibleLlmProperties properties,
        OpenAiCompatibleLlmClient client,
        ObjectMapper objectMapper
    ) {
        this.properties = properties;
        this.client = client;
        this.objectMapper = objectMapper;
    }

    @Override
    public LlmResult generate(LlmRequest request) {
        LlmRequestValidator.validate(request);
        ValidatedSettings settings = validateSettings(request);
        OpenAiCompatibleClientResponse response = callClient(request, settings);
        handleErrorStatus(response, settings);
        return mapSuccessResponse(response, settings, request.responseFormat());
    }

    @Override
    public String providerName() {
        return PROVIDER_NAME;
    }

    @Override
    public String modelNameForDiagnostics() {
        return properties == null ? "" : textOrDefault(properties.getModel(), "");
    }

    private OpenAiCompatibleClientResponse callClient(LlmRequest request, ValidatedSettings settings) {
        OpenAiCompatibleChatCompletionRequest clientRequest = new OpenAiCompatibleChatCompletionRequest(
            settings.uri(),
            Map.of("Authorization", "Bearer " + settings.apiKey()),
            "POST",
            "application/json",
            jsonBody(request, settings),
            settings.requestTimeout()
        );
        int maxAttempts = request.maxAttempts() == null ? MAX_ATTEMPTS : request.maxAttempts();
        for (int attempt = 1; attempt <= maxAttempts; attempt++) {
            try {
                OpenAiCompatibleClientResponse response = client.complete(clientRequest);
                if (isRetryableStatus(response.statusCode()) && attempt < maxAttempts) {
                    logRetry(request, settings, attempt, maxAttempts, response, null);
                    continue;
                }
                return response;
            } catch (OpenAiCompatibleLlmException exception) {
                OpenAiCompatibleLlmException diagnostic = withSettings(request, settings, exception);
                if (diagnostic.retryable() && attempt < maxAttempts) {
                    logRetry(request, settings, attempt, maxAttempts, null, diagnostic);
                    continue;
                }
                throw diagnostic;
            } catch (RuntimeException exception) {
                OpenAiCompatibleLlmException diagnostic = connectionError(request, settings, exception);
                if (attempt < maxAttempts) {
                    logRetry(request, settings, attempt, maxAttempts, null, diagnostic);
                    continue;
                }
                throw diagnostic;
            }
        }
        throw connectionError(request, settings, null);
    }

    private String jsonBody(LlmRequest request, ValidatedSettings settings) {
        List<Map<String, String>> messages = request.messages().stream()
            .map(message -> Map.of(
                "role", message.role().name().toLowerCase(Locale.ROOT),
                "content", message.content()
            ))
            .toList();

        Map<String, Object> body = new HashMap<>();
        body.put("model", settings.model());
        body.put("messages", messages);
        body.put("temperature", settings.temperature());
        body.put("max_tokens", settings.maxTokens());
        if (request.responseFormat() == LlmResponseFormat.JSON_OBJECT) {
            body.put("response_format", Map.of("type", "json_object"));
        }
        if ("qwen/qwen3-8b".equals(settings.model().toLowerCase(Locale.ROOT))) {
            body.put("enable_thinking", false);
        }
        body.put("stream", false);
        try {
            return objectMapper.writeValueAsString(body);
        } catch (JsonProcessingException exception) {
            throw new OpenAiCompatibleLlmException(
                "OpenAI-compatible LLM request JSON cannot be created",
                LlmProviderFailureType.JSON_PARSE_ERROR,
                false,
                null,
                exception,
                providerName(),
                settings.model(),
                settings.uri().toString(),
                null,
                null,
                exception.getClass().getName(),
                exception.getMessage()
            );
        }
    }

    private LlmResult mapSuccessResponse(
        OpenAiCompatibleClientResponse response,
        ValidatedSettings settings,
        LlmResponseFormat responseFormat
    ) {
        OpenAiCompatibleChatCompletionResponse payload;
        try {
            payload = objectMapper.readValue(response.body(), OpenAiCompatibleChatCompletionResponse.class);
        } catch (JsonProcessingException exception) {
            throw responseException(
                "OpenAI-compatible LLM response JSON is invalid",
                LlmProviderFailureType.MALFORMED_RESPONSE,
                false,
                response,
                settings,
                exception
            );
        }

        List<OpenAiCompatibleChatCompletionResponse.Choice> choices = payload.choices();
        if (choices == null || choices.isEmpty()) {
            throw responseException(
                "OpenAI-compatible LLM response does not contain choices",
                LlmProviderFailureType.MALFORMED_RESPONSE,
                false,
                response,
                settings,
                null
            );
        }
        OpenAiCompatibleChatCompletionResponse.Choice choice = choices.getFirst();
        OpenAiCompatibleChatCompletionResponse.Message message = choice.message();
        if (message == null || message.content() == null) {
            throw responseException(
                "OpenAI-compatible LLM response content path is invalid",
                LlmProviderFailureType.MALFORMED_RESPONSE,
                false,
                response,
                settings,
                null
            );
        }
        String content = responseFormat == LlmResponseFormat.TEXT ? message.content().strip() : message.content();
        if (content.isBlank()) {
            throw responseException(
                "OpenAI-compatible LLM response content is empty",
                LlmProviderFailureType.MALFORMED_RESPONSE,
                false,
                response,
                settings,
                null,
                content
            );
        }
        OpenAiCompatibleChatCompletionResponse.Usage usage = payload.usage();

        Map<String, Object> metadata = new HashMap<>();
        traceId(response).ifPresent(traceId -> metadata.put("providerTraceId", traceId));

        return new LlmResult(
            providerName(),
            textOrDefault(payload.model(), settings.model()),
            content,
            choice.finishReason(),
            usage == null
                ? new LlmUsage(null, null, null)
                : new LlmUsage(usage.promptTokens(), usage.completionTokens(), usage.totalTokens()),
            response.duration(),
            metadata
        );
    }

    private void handleErrorStatus(OpenAiCompatibleClientResponse response, ValidatedSettings settings) {
        if (response.statusCode() >= 200 && response.statusCode() < 300) {
            return;
        }
        boolean retryable = isRetryableStatus(response.statusCode());
        throw responseException(
            "OpenAI-compatible LLM request failed",
            failureType(response.statusCode()),
            retryable,
            response,
            settings,
            null
        );
    }

    private ValidatedSettings validateSettings(LlmRequest request) {
        String apiKey = requireText(properties.getApiKey(), "API key is required");
        String model = requireText(
            metadataText(request, AiModelRoutedLlmRequestFactory.METADATA_MODEL_NAME).orElse(properties.getModel()),
            "model is required"
        );
        if (model.length() > MAX_MODEL_LENGTH) {
            throw invalid("model is too long");
        }
        String baseUrl = metadataText(request, AiModelRoutedLlmRequestFactory.METADATA_BASE_URL)
            .orElse(properties.getBaseUrl());
        Duration requestTimeout = request.timeout() == null
            ? positiveDuration(properties.getRequestTimeout(), "request timeout must be positive")
            : request.timeout();
        Double temperature = request.temperature() == null ? properties.getTemperature() : request.temperature();
        Integer maxTokens = request.maxTokens() == null ? properties.getMaxTokens() : request.maxTokens();
        validateProviderDefaults(temperature, maxTokens);
        return new ValidatedSettings(
            apiKey,
            model,
            fixedChatCompletionsUri(baseUrl),
            requestTimeout,
            temperature,
            maxTokens
        );
    }

    private static Optional<String> metadataText(LlmRequest request, String key) {
        if (request == null || key == null || request.metadata() == null) {
            return Optional.empty();
        }
        Object value = request.metadata().get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            return Optional.empty();
        }
        return Optional.of(text.strip());
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

    private URI fixedChatCompletionsUri(String baseUrl) {
        String trimmed = requireText(baseUrl, "base URL is required");
        try {
            URI baseUri = new URI(trimmed);
            String scheme = baseUri.getScheme();
            if (scheme == null || (!scheme.equalsIgnoreCase("http") && !scheme.equalsIgnoreCase("https"))) {
                throw invalid("base URL must use http or https");
            }
            if (baseUri.getRawAuthority() == null || baseUri.getRawAuthority().isBlank()) {
                throw invalid("base URL host is required");
            }
            String basePath = baseUri.getRawPath();
            if (basePath == null || basePath.isBlank() || "/".equals(basePath)) {
                basePath = DEFAULT_API_PATH_PREFIX;
            }
            String normalizedBasePath = basePath.endsWith("/")
                ? basePath.substring(0, basePath.length() - 1)
                : basePath;
            return new URI(
                scheme.toLowerCase(Locale.ROOT),
                baseUri.getRawAuthority(),
                normalizedBasePath + CHAT_COMPLETIONS_PATH,
                null,
                null
            );
        } catch (URISyntaxException exception) {
            throw new OpenAiCompatibleLlmException("base URL is invalid", false, exception);
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

    private static OpenAiCompatibleLlmException invalid(String message) {
        return new OpenAiCompatibleLlmException("OpenAI-compatible LLM configuration is invalid: " + message, false);
    }

    private static boolean isRetryableStatus(int statusCode) {
        return statusCode == 429 || statusCode >= 500;
    }

    private static LlmProviderFailureType failureType(int statusCode) {
        if (statusCode == 401 || statusCode == 403) {
            return LlmProviderFailureType.PROVIDER_AUTH_FAILED;
        }
        if (statusCode == 429) {
            return LlmProviderFailureType.PROVIDER_RATE_LIMIT;
        }
        return LlmProviderFailureType.HTTP_ERROR;
    }

    private static String textOrDefault(String value, String fallback) {
        return value == null || value.isBlank() ? fallback : value.strip();
    }

    private static Optional<String> traceId(OpenAiCompatibleClientResponse response) {
        return response.headers().entrySet().stream()
            .filter(entry -> "x-request-id".equalsIgnoreCase(entry.getKey()))
            .flatMap(entry -> entry.getValue().stream())
            .map(String::strip)
            .filter(value -> !value.isBlank())
            .filter(value -> !LlmErrorSanitizer.containsSensitiveData(value))
            .findFirst();
    }

    private static String traceIdOrNull(OpenAiCompatibleClientResponse response) {
        return traceId(response).orElse(null);
    }

    private OpenAiCompatibleLlmException responseException(
        String message,
        LlmProviderFailureType failureType,
        boolean retryable,
        OpenAiCompatibleClientResponse response,
        ValidatedSettings settings,
        Throwable cause
    ) {
        return responseException(message, failureType, retryable, response, settings, cause, null);
    }

    private OpenAiCompatibleLlmException responseException(
        String message,
        LlmProviderFailureType failureType,
        boolean retryable,
        OpenAiCompatibleClientResponse response,
        ValidatedSettings settings,
        Throwable cause,
        String extractedContent
    ) {
        Integer statusCode = response == null ? null : response.statusCode();
        String summary = response == null ? null : summary(response.body());
        String contentSummary = summary(extractedContent);
        String detail = diagnosticMessage(
            message,
            failureType,
            null,
            statusCode,
            settings,
            response,
            summary,
            contentSummary,
            cause
        );
        return new OpenAiCompatibleLlmException(
            detail,
            failureType,
            retryable,
            statusCode,
            cause,
            providerName(),
            settings.model(),
            settings.uri().toString(),
            elapsedMs(response),
            response == null ? null : traceIdOrNull(response),
            summary,
            cause == null ? null : cause.getClass().getName(),
            rootCauseMessage(cause)
        );
    }

    private OpenAiCompatibleLlmException withSettings(
        LlmRequest request,
        ValidatedSettings settings,
        OpenAiCompatibleLlmException exception
    ) {
        String detail = diagnosticMessage(
            exception.getMessage(),
            exception.failureType(),
            request,
            exception.statusCode().orElse(null),
            settings,
            null,
            exception.responseBodySummary().orElse(null),
            null,
            exception
        );
        return new OpenAiCompatibleLlmException(
            detail,
            exception.failureType(),
            exception.retryable(),
            exception.statusCode().orElse(null),
            exception,
            providerName(),
            settings.model(),
            settings.uri().toString(),
            exception.elapsedMs().orElse(null),
            exception.providerTraceId().orElse(null),
            exception.responseBodySummary().orElse(null),
            exception.exceptionClass().orElse(exception.getClass().getName()),
            exception.rootCauseMessage().orElse(rootCauseMessage(exception))
        );
    }

    private OpenAiCompatibleLlmException connectionError(
        LlmRequest request,
        ValidatedSettings settings,
        RuntimeException exception
    ) {
        LlmProviderFailureType failureType = isTimeout(exception)
            ? LlmProviderFailureType.TIMEOUT
            : LlmProviderFailureType.CONNECTION_ERROR;
        String detail = diagnosticMessage(
            "OpenAI-compatible LLM network call failed",
            failureType,
            request,
            null,
            settings,
            null,
            null,
            null,
            exception
        );
        return new OpenAiCompatibleLlmException(
            detail,
            failureType,
            true,
            null,
            exception,
            providerName(),
            settings.model(),
            settings.uri().toString(),
            null,
            null,
            exception == null ? null : exception.getClass().getName(),
            rootCauseMessage(exception)
        );
    }

    private static String diagnosticMessage(
        String message,
        LlmProviderFailureType failureType,
        LlmRequest request,
        Integer statusCode,
        ValidatedSettings settings,
        OpenAiCompatibleClientResponse response,
        String responseSummary,
        String extractedContentSummary,
        Throwable cause
    ) {
        return String.format(
            Locale.ROOT,
            "%s type=%s taskId=%s provider=%s model=%s endpoint=%s httpStatus=%s elapsedMs=%s providerTraceId=%s responseBody=%s extractedContent=%s exceptionClass=%s rootCause=%s",
            message,
            failureType,
            request == null ? "" : request.taskId(),
            PROVIDER_NAME,
            settings == null ? "" : settings.model(),
            settings == null ? "" : settings.uri(),
            statusCode == null ? "" : statusCode,
            elapsedMs(response) == null ? "" : elapsedMs(response),
            response == null ? "" : traceIdOrNull(response),
            responseSummary == null ? "" : responseSummary,
            extractedContentSummary == null ? "" : extractedContentSummary,
            cause == null ? "" : cause.getClass().getName(),
            rootCauseMessage(cause) == null ? "" : rootCauseMessage(cause)
        );
    }

    private static void logRetry(
        LlmRequest request,
        ValidatedSettings settings,
        int attempt,
        int maxAttempts,
        OpenAiCompatibleClientResponse response,
        OpenAiCompatibleLlmException exception
    ) {
        LlmProviderFailureType type = exception == null
            ? failureType(response.statusCode())
            : exception.failureType();
        Integer status = exception == null ? Integer.valueOf(response.statusCode()) : exception.statusCode().orElse(null);
        log.warn(
            "event=llm_provider_retry taskId={} provider={} model={} endpoint={} failureType={} httpStatus={} attempt={} maxAttempts={} elapsedMs={} providerTraceId={} responseBody={} exceptionClass={} rootCause={}",
            request.taskId(),
            providerNameStatic(),
            settings.model(),
            settings.uri(),
            type,
            status == null ? "" : status,
            attempt,
            maxAttempts,
            exception == null ? elapsedMs(response) : exception.elapsedMs().orElse(null),
            exception == null ? traceIdOrNull(response) : exception.providerTraceId().orElse(null),
            exception == null ? summary(response.body()) : exception.responseBodySummary().orElse(null),
            exception == null ? "" : exception.exceptionClass().orElse(exception.getClass().getName()),
            exception == null ? "" : exception.rootCauseMessage().orElse(null)
        );
    }

    private static String providerNameStatic() {
        return PROVIDER_NAME;
    }

    private static Long elapsedMs(OpenAiCompatibleClientResponse response) {
        return response == null || response.duration() == null ? null : response.duration().toMillis();
    }

    private static String summary(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        String sanitized = LlmErrorSanitizer.sanitize(value.replaceAll("\\s+", " ").strip());
        if (sanitized.length() <= MAX_RESPONSE_SUMMARY_LENGTH) {
            return sanitized;
        }
        return sanitized.substring(0, MAX_RESPONSE_SUMMARY_LENGTH);
    }

    private static boolean isTimeout(Throwable throwable) {
        Throwable current = throwable;
        while (current != null) {
            String name = current.getClass().getName().toLowerCase(Locale.ROOT);
            String message = current.getMessage() == null ? "" : current.getMessage().toLowerCase(Locale.ROOT);
            if (name.contains("timeout") || message.contains("timeout") || message.contains("timed out")) {
                return true;
            }
            current = current.getCause();
        }
        return false;
    }

    private static String rootCauseMessage(Throwable cause) {
        if (cause == null) {
            return null;
        }
        Throwable root = cause;
        while (root.getCause() != null) {
            root = root.getCause();
        }
        return LlmErrorSanitizer.sanitize(root.getMessage());
    }

    private record ValidatedSettings(
        String apiKey,
        String model,
        URI uri,
        Duration requestTimeout,
        Double temperature,
        Integer maxTokens
    ) {
    }
}
