package com.example.courselingo.ai.llm;

public enum LlmProviderFailureCategory {
    AUTHENTICATION,
    MODEL_NOT_FOUND,
    RATE_LIMIT,
    TIMEOUT,
    NETWORK,
    UNSUPPORTED_RESPONSE_FORMAT,
    CONTEXT_TOO_LARGE,
    INVALID_REQUEST,
    SERVER_ERROR,
    OUTPUT_INVALID,
    UNKNOWN
}
