package com.example.courselingo.media;

import java.util.List;

public record EmbeddedSubtitleProbeResponse(
    EmbeddedSubtitleStatus status,
    List<EmbeddedSubtitleTrackResponse> tracks,
    Integer selectedStreamIndex
) {
}
