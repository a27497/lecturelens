package com.example.courselingo.ai.asr;

public class SpeechToTextProviderException extends RuntimeException {

    public SpeechToTextProviderException(String message) {
        super(AsrErrorSanitizer.sanitize(message));
    }

    public SpeechToTextProviderException(String message, Throwable cause) {
        super(AsrErrorSanitizer.sanitize(message), cause);
    }
}
