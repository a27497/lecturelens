package com.example.courselingo.ai.llm;

import java.util.Optional;

public class OpenAiCompatibleLlmException extends LlmProviderException {

    private final boolean retryable;
    private final Integer statusCode;
    private final LlmProviderFailureType failureType;
    private final String provider;
    private final String model;
    private final String endpoint;
    private final Long elapsedMs;
    private final String providerTraceId;
    private final String responseBodySummary;
    private final String exceptionClass;
    private final String rootCauseMessage;

    public OpenAiCompatibleLlmException(String message, boolean retryable) {
        this(message, inferFailureType(message, null, retryable), retryable, null, null, null, null, null, null, null, null, null);
    }

    public OpenAiCompatibleLlmException(String message, boolean retryable, Integer statusCode) {
        this(message, classifyStatus(statusCode), retryable, statusCode, null, null, null, null, null, null, null, null);
    }

    public OpenAiCompatibleLlmException(String message, boolean retryable, Throwable cause) {
        this(
            message,
            inferFailureType(message, cause, retryable),
            retryable,
            null,
            cause,
            null,
            null,
            null,
            null,
            null,
            exceptionClass(cause),
            rootCauseMessage(cause)
        );
    }

    public OpenAiCompatibleLlmException(String message, boolean retryable, Integer statusCode, Throwable cause) {
        this(
            message,
            classifyStatus(statusCode),
            retryable,
            statusCode,
            cause,
            null,
            null,
            null,
            null,
            null,
            exceptionClass(cause),
            rootCauseMessage(cause)
        );
    }

    public OpenAiCompatibleLlmException(
        String message,
        LlmProviderFailureType failureType,
        boolean retryable,
        Integer statusCode,
        Throwable cause,
        String provider,
        String model,
        String endpoint,
        Long elapsedMs,
        String providerTraceId,
        String exceptionClass,
        String rootCauseMessage
    ) {
        this(message, failureType, retryable, statusCode, cause, provider, model, endpoint, elapsedMs, providerTraceId, null,
            exceptionClass, rootCauseMessage);
    }

    public OpenAiCompatibleLlmException(
        String message,
        LlmProviderFailureType failureType,
        boolean retryable,
        Integer statusCode,
        Throwable cause,
        String provider,
        String model,
        String endpoint,
        Long elapsedMs,
        String providerTraceId,
        String responseBodySummary,
        String exceptionClass,
        String rootCauseMessage
    ) {
        super(message, cause);
        this.retryable = retryable;
        this.statusCode = statusCode;
        this.failureType = failureType == null ? LlmProviderFailureType.HTTP_ERROR : failureType;
        this.provider = blankToNull(provider);
        this.model = blankToNull(model);
        this.endpoint = blankToNull(endpoint);
        this.elapsedMs = elapsedMs;
        this.providerTraceId = blankToNull(providerTraceId);
        this.responseBodySummary = blankToNull(responseBodySummary);
        this.exceptionClass = blankToNull(exceptionClass);
        this.rootCauseMessage = blankToNull(rootCauseMessage);
    }

    public boolean retryable() {
        return retryable;
    }

    public LlmProviderFailureType failureType() {
        return failureType;
    }

    public Optional<Integer> statusCode() {
        return Optional.ofNullable(statusCode);
    }

    public Optional<String> provider() {
        return Optional.ofNullable(provider);
    }

    public Optional<String> model() {
        return Optional.ofNullable(model);
    }

    public Optional<String> endpoint() {
        return Optional.ofNullable(endpoint);
    }

    public Optional<Long> elapsedMs() {
        return Optional.ofNullable(elapsedMs);
    }

    public Optional<String> providerTraceId() {
        return Optional.ofNullable(providerTraceId);
    }

    public Optional<String> responseBodySummary() {
        return Optional.ofNullable(responseBodySummary);
    }

    public Optional<String> exceptionClass() {
        return Optional.ofNullable(exceptionClass);
    }

    public Optional<String> rootCauseMessage() {
        return Optional.ofNullable(rootCauseMessage);
    }

    private static LlmProviderFailureType classifyStatus(Integer statusCode) {
        if (statusCode != null && (statusCode == 401 || statusCode == 403)) {
            return LlmProviderFailureType.PROVIDER_AUTH_FAILED;
        }
        if (statusCode != null && statusCode == 429) {
            return LlmProviderFailureType.PROVIDER_RATE_LIMIT;
        }
        return LlmProviderFailureType.HTTP_ERROR;
    }

    private static LlmProviderFailureType inferFailureType(String message, Throwable cause, boolean retryable) {
        String text = ((message == null ? "" : message) + " " + (cause == null ? "" : cause.getClass().getName()))
            .toLowerCase(java.util.Locale.ROOT);
        if (text.contains("timeout") || text.contains("timed out")) {
            return LlmProviderFailureType.TIMEOUT;
        }
        if (retryable) {
            return LlmProviderFailureType.CONNECTION_ERROR;
        }
        return LlmProviderFailureType.HTTP_ERROR;
    }

    private static String exceptionClass(Throwable cause) {
        return cause == null ? null : cause.getClass().getName();
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

    private static String blankToNull(String value) {
        if (value == null || value.isBlank()) {
            return null;
        }
        return LlmErrorSanitizer.sanitize(value.strip());
    }
}
