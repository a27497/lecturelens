package com.example.courselingo.vision.analysis;

import java.nio.file.Path;

@FunctionalInterface
public interface VisionAnalysisService {

    VisionAnalysisScanResult scan(String taskId, Long userId);

    default VisionAnalysisScanResult scan(
        String taskId,
        Long userId,
        Path sourceVideo,
        Path analysisWorkspace,
        String targetLanguage
    ) {
        return scan(taskId, userId);
    }
}
