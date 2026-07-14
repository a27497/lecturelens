package com.example.courselingo.vision.keyframe;

import java.nio.file.Path;

public record SelectedKeyframe(
    int frameIndex,
    long timestampMillis,
    Path imageFile,
    double changeScore,
    KeyframeSelectionReason reason
) {
}
