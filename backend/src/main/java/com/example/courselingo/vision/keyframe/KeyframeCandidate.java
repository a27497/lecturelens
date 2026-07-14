package com.example.courselingo.vision.keyframe;

import java.nio.file.Path;

public record KeyframeCandidate(
    int frameIndex,
    long timestampMillis,
    Path imageFile,
    FrameChangeScore changeScore
) {
}
