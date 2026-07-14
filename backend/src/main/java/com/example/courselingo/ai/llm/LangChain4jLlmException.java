package com.example.courselingo.ai.llm;

import java.util.Optional;

public class LangChain4jLlmException extends LlmProviderException {

    private final boolean retryable;
    private final Integer statusCode;

    public LangChain4jLlmException(String message, boolean retryable) {
        this(message, retryable, null, null);
    }

    public LangChain4jLlmException(String message, boolean retryable, Integer statusCode) {
        this(message, retryable, statusCode, null);
    }

    public LangChain4jLlmException(String message, boolean retryable, Throwable cause) {
        this(message, retryable, null, cause);
    }

    public LangChain4jLlmException(String message, boolean retryable, Integer statusCode, Throwable cause) {
        super(message, cause);
        this.retryable = retryable;
        this.statusCode = statusCode;
    }

    public boolean retryable() {
        return retryable;
    }

    public Optional<Integer> statusCode() {
        return Optional.ofNullable(statusCode);
    }
}
