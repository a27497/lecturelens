package com.example.courselingo.ai.asr;

import java.nio.file.Files;
import java.time.Duration;

public final class SpeechToTextRequestValidator {

    private static final int MAX_LANGUAGE_LENGTH = 32;

    private SpeechToTextRequestValidator() {
    }

    public static void validate(SpeechToTextRequest request) {
        if (request == null) {
            throw invalid("request is required");
        }
        validateAudioFile(request);
        validateLanguage(request.language());
        validateRequiredText(request.requestId(), "request id is required");
        validateRequiredText(request.taskId(), "task id is required");
        validateTimeout(request.timeout());
    }

    private static void validateAudioFile(SpeechToTextRequest request) {
        if (request.audioFile() == null) {
            throw invalid("audio file is required");
        }
        if (!Files.exists(request.audioFile())) {
            throw invalid("audio file does not exist");
        }
        if (!Files.isRegularFile(request.audioFile())) {
            throw invalid("audio file must be a regular file");
        }
    }

    private static void validateLanguage(String language) {
        validateRequiredText(language, "language is required");
        if (language.strip().length() > MAX_LANGUAGE_LENGTH) {
            throw invalid("language is too long");
        }
    }

    private static void validateRequiredText(String value, String message) {
        if (value == null || value.isBlank()) {
            throw invalid(message);
        }
    }

    private static void validateTimeout(Duration timeout) {
        if (timeout == null || timeout.isZero() || timeout.isNegative()) {
            throw invalid("timeout must be positive");
        }
    }

    private static SpeechToTextProviderException invalid(String reason) {
        return new SpeechToTextProviderException("ASR request is invalid: " + reason);
    }
}
