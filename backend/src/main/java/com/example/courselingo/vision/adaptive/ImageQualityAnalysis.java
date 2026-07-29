package com.example.courselingo.vision.adaptive;

import java.util.Map;

/** Explainable, low-cost image quality measurements used by frame selection. */
public record ImageQualityAnalysis(
    int width,
    int height,
    double laplacianVariance,
    double meanBrightness,
    double brightnessVariance,
    boolean black,
    boolean blank,
    double edgeDensity,
    long perceptualHash,
    String contentFingerprint,
    double stability,
    double sceneChangeScore,
    double totalScore,
    Map<String, Double> scoreComponents,
    String explanation
) {

    public ImageQualityAnalysis {
        scoreComponents = scoreComponents == null ? Map.of() : Map.copyOf(scoreComponents);
        explanation = explanation == null ? "" : explanation;
        contentFingerprint = contentFingerprint == null ? "" : contentFingerprint;
    }

    public boolean acceptable() {
        return !black && !blank && totalScore > 0.0;
    }
}
