package com.example.courselingo.media;

public record SceneDetectionPoint(long timestampMillis, double score) {

    public SceneDetectionPoint {
        timestampMillis = Math.max(0L, timestampMillis);
        score = Math.max(0.0d, Math.min(1.0d, score));
    }
}
