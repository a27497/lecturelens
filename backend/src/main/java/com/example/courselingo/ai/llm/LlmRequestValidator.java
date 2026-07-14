package com.example.courselingo.ai.llm;

import java.time.Duration;

public final class LlmRequestValidator {

    public static final int MAX_TOKENS = 32768;

    private LlmRequestValidator() {
    }

    public static void validate(LlmRequest request) {
        if (request == null) {
            throw invalid("request is required");
        }
        validateRequiredText(request.requestId(), "request id is required");
        validateRequiredText(request.taskId(), "task id is required");
        if (request.messages().isEmpty()) {
            throw invalid("messages are required");
        }
        request.messages().forEach(LlmRequestValidator::validateMessage);
        validateTimeout(request.timeout());
        validateTemperature(request.temperature());
        validateMaxTokens(request.maxTokens());
        validateMaxAttempts(request.maxAttempts());
    }

    private static void validateMessage(LlmMessage message) {
        if (message == null) {
            throw invalid("message is required");
        }
        if (message.role() == null) {
            throw invalid("message role is required");
        }
        validateRequiredText(message.content(), "message content is required");
    }

    private static void validateRequiredText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw invalid(message);
        }
    }

    private static void validateTimeout(Duration timeout) {
        if (timeout != null && (timeout.isZero() || timeout.isNegative())) {
            throw invalid("timeout must be positive");
        }
    }

    private static void validateTemperature(Double temperature) {
        if (temperature != null && (temperature < 0.0 || temperature > 2.0)) {
            throw invalid("temperature must be between 0 and 2");
        }
    }

    private static void validateMaxTokens(Integer maxTokens) {
        if (maxTokens == null) {
            return;
        }
        if (maxTokens <= 0) {
            throw invalid("max completion count must be positive");
        }
        if (maxTokens > MAX_TOKENS) {
            throw invalid("max completion count exceeds limit");
        }
    }

    private static void validateMaxAttempts(Integer maxAttempts) {
        if (maxAttempts != null && maxAttempts <= 0) {
            throw invalid("max attempts must be positive");
        }
    }

    private static LlmProviderException invalid(String reason) {
        return new LlmProviderException("LLM request is invalid: " + reason);
    }
}
