package com.example.courselingo.ai.llm;

public enum LlmProviderFailureType {
    HTTP_ERROR,
    TIMEOUT,
    CONNECTION_ERROR,
    EMPTY_RESPONSE,
    MALFORMED_RESPONSE,
    JSON_PARSE_ERROR,
    UNEXPECTED_SCHEMA,
    PROVIDER_RATE_LIMIT,
    PROVIDER_AUTH_FAILED
}
