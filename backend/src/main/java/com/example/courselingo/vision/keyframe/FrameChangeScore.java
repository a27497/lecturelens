package com.example.courselingo.vision.keyframe;

public record FrameChangeScore(
    double averagePixelDelta,
    double changedPixelRatio
) {

    public static FrameChangeScore none() {
        return new FrameChangeScore(0.0, 0.0);
    }

    public double normalizedScore() {
        return Math.max(changedPixelRatio, Math.min(1.0, averagePixelDelta / 255.0));
    }
}
