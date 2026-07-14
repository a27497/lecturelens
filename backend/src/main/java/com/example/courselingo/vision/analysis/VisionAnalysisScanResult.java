package com.example.courselingo.vision.analysis;

public record VisionAnalysisScanResult(
    int saved,
    int succeeded,
    int empty,
    int failed,
    int skipped
) {
}
