package com.example.courselingo.ai.asr;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;

public class MockAsrProvider implements SpeechToTextProvider {

    public static final String PROVIDER_NAME = "mock";
    private static final String METADATA_SOURCE = "mock-asr";

    private final MockAsrProperties properties;

    public MockAsrProvider(MockAsrProperties properties) {
        this.properties = properties;
    }

    @Override
    public SpeechToTextResult transcribe(SpeechToTextRequest request) {
        SpeechToTextRequestValidator.validate(request);
        long segmentDurationMillis = validateSegmentDuration();
        String fullText = transcriptText(request.audioFile());
        TranscribedSegment segment = new TranscribedSegment(0, 0, segmentDurationMillis, fullText);

        return new SpeechToTextResult(
            providerName(),
            request.language(),
            fullText,
            List.of(segment),
            Duration.ZERO,
            segmentDurationMillis,
            metadata(request.audioFile())
        );
    }

    @Override
    public String providerName() {
        return PROVIDER_NAME;
    }

    private long validateSegmentDuration() {
        long segmentDurationMillis = properties.getSegmentDurationMillis();
        if (segmentDurationMillis <= 0) {
            throw new SpeechToTextProviderException(
                "Mock ASR configuration is invalid: segment duration must be positive"
            );
        }
        return segmentDurationMillis;
    }

    private String transcriptText(Path audioFile) {
        String configuredText = properties.getDefaultText();
        String text = configuredText == null ? "" : configuredText.strip();
        if (text.isBlank()) {
            text = "Mock ASR transcript for " + audioFile.getFileName();
        }
        if (AsrErrorSanitizer.containsSensitiveData(text)) {
            throw new SpeechToTextProviderException("Mock ASR configuration is invalid: default text is not safe");
        }
        return text;
    }

    private Map<String, Object> metadata(Path audioFile) {
        return Map.of(
            "mock", true,
            "source", METADATA_SOURCE,
            "audioFileName", audioFile.getFileName().toString()
        );
    }
}
