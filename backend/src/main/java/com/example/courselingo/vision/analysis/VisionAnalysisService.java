package com.example.courselingo.vision.analysis;

@FunctionalInterface
public interface VisionAnalysisService {

    VisionAnalysisScanResult scan(String taskId, Long userId);
}
