package com.example.courselingo.ai.asr;

/** Compatibility type for existing SiliconFlow clients. */
public class SiliconFlowAsrException extends AsrProviderException {
    public SiliconFlowAsrException(String message, boolean retryable) {
        super(message, retryable);
    }
    public SiliconFlowAsrException(String message, boolean retryable, Integer statusCode) {
        super(message, retryable, statusCode);
    }
    public SiliconFlowAsrException(String message, boolean retryable, Throwable cause) {
        super(message, retryable, cause);
    }
    public SiliconFlowAsrException(String message, boolean retryable, Integer statusCode, Throwable cause) {
        super(message, retryable, statusCode, cause);
    }
}
