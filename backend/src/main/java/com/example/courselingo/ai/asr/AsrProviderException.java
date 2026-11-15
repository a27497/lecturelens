package com.example.courselingo.ai.asr;

import java.util.Optional;

public class AsrProviderException extends SpeechToTextProviderException {

    private final boolean retryable;
    private final Integer statusCode;
    private final long retryAfterMillis;

    public AsrProviderException(String message, boolean retryable, Integer statusCode, long retryAfterMillis) {
        super(message);
        this.retryable=retryable;this.statusCode=statusCode;this.retryAfterMillis=Math.max(0,retryAfterMillis);
    }

    public AsrProviderException(String message, boolean retryable) {
        this(message, retryable, null, null);
    }

    public AsrProviderException(String message, boolean retryable, Integer statusCode) {
        this(message, retryable, statusCode, null);
    }

    public AsrProviderException(String message, boolean retryable, Throwable cause) {
        this(message, retryable, null, cause);
    }

    public AsrProviderException(String message, boolean retryable, Integer statusCode, Throwable cause) {
        // Provider/HTTP/parser causes can contain credentials or request bodies.
        // Retry and HTTP status are explicit; never retain an unsafe cause chain.
        super(message);
        this.retryable = retryable;
        this.statusCode = statusCode;
        this.retryAfterMillis = 0;
    }

    public boolean retryable() {
        return retryable;
    }

    public Optional<Integer> statusCode() {
        return Optional.ofNullable(statusCode);
    }
    public long retryAfterMillis() { return retryAfterMillis; }
}
