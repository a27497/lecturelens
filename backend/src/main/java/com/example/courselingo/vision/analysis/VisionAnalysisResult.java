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
    String errorMessage,
    @com.fasterxml.jackson.annotation.JsonInclude(com.fasterxml.jackson.annotation.JsonInclude.Include.NON_NULL)
    com.example.courselingo.ai.llm.LlmOutputDiagnostics outputDiagnostics
) {
    public VisionAnalysisResult(VisionAnalysisStatus status, String screenType, String summary,
        List<String> detectedElements, String provider, String model, Long durationMillis,
        String errorCode, String errorMessage) {
        this(status, screenType, summary, detectedElements, provider, model, durationMillis, errorCode, errorMessage, null);
    }

    public static VisionAnalysisResult failedOutput(String provider, String model, Long durationMillis,
        com.example.courselingo.ai.llm.TranslationFailure failure) {
        return new VisionAnalysisResult(VisionAnalysisStatus.FAILED, "", "", List.of(), provider, model,
            durationMillis, "VISION_OUTPUT_" + failure.reason().name(), "Vision provider output failed",
            com.example.courselingo.ai.llm.LlmOutputDiagnostics.from(failure));
    }
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
