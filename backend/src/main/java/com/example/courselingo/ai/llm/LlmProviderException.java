package com.example.courselingo.ai.llm;

public class LlmProviderException extends RuntimeException {

    public LlmProviderException(String message) {
        super(LlmErrorSanitizer.sanitize(message));
    }

    public LlmProviderException(String message, Throwable cause) {
        super(LlmErrorSanitizer.sanitize(message), cause);
    }
}
