package com.example.courselingo.ai.asr;

import java.util.Optional;

public class SiliconFlowAsrException extends SpeechToTextProviderException {

    private final boolean retryable;
    private final Integer statusCode;

    public SiliconFlowAsrException(String message, boolean retryable) {
        this(message, retryable, null, null);
    }

    public SiliconFlowAsrException(String message, boolean retryable, Integer statusCode) {
        this(message, retryable, statusCode, null);
    }

    public SiliconFlowAsrException(String message, boolean retryable, Throwable cause) {
        this(message, retryable, null, cause);
    }

    public SiliconFlowAsrException(String message, boolean retryable, Integer statusCode, Throwable cause) {
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
