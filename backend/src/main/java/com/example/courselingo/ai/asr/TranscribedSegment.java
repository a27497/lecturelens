package com.example.courselingo.ai.asr;

public record TranscribedSegment(
    int index,
    long startMillis,
    long endMillis,
    String text
) {

    public TranscribedSegment {
        if (index < 0) {
            throw new SpeechToTextProviderException("ASR segment is invalid: segment index must not be negative");
        }
        if (startMillis < 0) {
            throw new SpeechToTextProviderException("ASR segment is invalid: segment start must not be negative");
        }
        if (endMillis < startMillis) {
            throw new SpeechToTextProviderException("ASR segment is invalid: segment end must not be before start");
        }
        if (text == null || text.isBlank()) {
            throw new SpeechToTextProviderException("ASR segment is invalid: segment text is required");
        }
        text = text.strip();
    }
}
