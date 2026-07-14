package com.example.courselingo.vision.analysis;

public interface VisionModelProvider {

    String providerName();

    VisionAnalysisResult analyze(VisionAnalysisRequest request);
}
