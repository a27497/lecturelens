package com.example.courselingo.media;

import com.example.courselingo.ai.asr.TranscribedSegment;
import java.util.List;

public record EmbeddedSubtitleTranscript(
    String language,
    List<TranscribedSegment> segments,
    double coverage,
    int streamIndex
) {
    public EmbeddedSubtitleTranscript {
        language = language == null || language.isBlank() ? "auto" : language.strip();
        segments = segments == null ? List.of() : List.copyOf(segments);
    }
}
