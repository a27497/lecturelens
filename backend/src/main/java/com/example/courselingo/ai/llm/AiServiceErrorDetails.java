package com.example.courselingo.ai.llm;

public record AiServiceErrorDetails(
    String errorCode,
    LlmProviderFailureCategory errorCategory,
    boolean retryable,
    String stage,
    String userMessage
) {
}
