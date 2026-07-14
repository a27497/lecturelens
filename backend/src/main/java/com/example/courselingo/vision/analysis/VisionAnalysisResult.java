package com.example.courselingo.vision.analysis;

import java.util.List;

public record VisionAnalysisResult(
    VisionAnalysisStatus status,
    String screenType,
    String summary,
    List<String> detectedElements,
    String provider,
    String model,
    Long durationMillis,
    String errorCode,
    String errorMessage
) {
    public VisionAnalysisResult {
        detectedElements = detectedElements == null ? List.of() : List.copyOf(detectedElements);
    }

    public static VisionAnalysisResult empty(String provider, String model, Long durationMillis) {
        return new VisionAnalysisResult(
            VisionAnalysisStatus.EMPTY,
            "",
            "",
            List.of(),
            provider,
            model,
            durationMillis,
            null,
            null
        );
    }

    public static VisionAnalysisResult failed(
        String provider,
        String model,
        Long durationMillis,
        String errorCode,
        String errorMessage
    ) {
        return new VisionAnalysisResult(
            VisionAnalysisStatus.FAILED,
            "",
            "",
            List.of(),
            provider,
            model,
            durationMillis,
            errorCode,
            errorMessage
        );
    }
}
