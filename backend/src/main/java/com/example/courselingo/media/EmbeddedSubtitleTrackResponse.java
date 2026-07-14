package com.example.courselingo.media;

public record EmbeddedSubtitleTrackResponse(
    int streamIndex,
    String codecName,
    String language,
    String title,
    boolean defaultTrack,
    boolean supported,
    String unsupportedReason
) {
}
