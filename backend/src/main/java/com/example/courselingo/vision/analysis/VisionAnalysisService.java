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

    default VisionAnalysisScanResult scan(
            String taskId,
            Long userId,
            Path sourceVideo,
            Path workspace,
            String language,
            com.example.courselingo.systemmodel.SystemModelExecutionRef execution) {
        return scan(taskId, userId, sourceVideo, workspace, language);
    }
}
