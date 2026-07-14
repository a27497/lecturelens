package com.example.courselingo.ai.asr;

import java.time.Duration;
import java.util.List;
import java.util.Map;

public record SpeechToTextResult(
    String provider,
    String language,
    String fullText,
    List<TranscribedSegment> segments,
    Duration duration,
    long audioDurationMillis,
    Map<String, Object> metadata
) {

    public SpeechToTextResult {
        if (segments == null) {
            throw new SpeechToTextProviderException("ASR result is invalid: segments are required");
        }
        if (audioDurationMillis < 0) {
            throw new SpeechToTextProviderException("ASR result is invalid: audio duration must not be negative");
        }
        provider = provider == null ? "" : provider.strip();
        language = language == null ? "" : language.strip();
        fullText = fullText == null ? "" : fullText;
        duration = duration == null ? Duration.ZERO : duration;
        segments = List.copyOf(segments);
        metadata = sanitizeMetadata(metadata);
    }

    private static Map<String, Object> sanitizeMetadata(Map<String, Object> metadata) {
        if (metadata == null || metadata.isEmpty()) {
            return Map.of();
        }
        for (Map.Entry<String, Object> entry : metadata.entrySet()) {
            String key = String.valueOf(entry.getKey());
            Object value = entry.getValue();
            if (AsrErrorSanitizer.containsSensitiveData(key) || containsSensitiveValue(value)) {
                throw new SpeechToTextProviderException("ASR result is invalid: metadata contains sensitive data");
            }
        }
        return Map.copyOf(metadata);
    }

    private static boolean containsSensitiveValue(Object value) {
        return value instanceof String text && AsrErrorSanitizer.containsSensitiveData(text);
    }
}
