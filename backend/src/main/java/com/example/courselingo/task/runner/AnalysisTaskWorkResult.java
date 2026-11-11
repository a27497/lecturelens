package com.example.courselingo.task.runner;

public record AnalysisTaskWorkResult(
    boolean success,
    String errorCode,
    String errorMessage
) {

    static final String DEGRADED_ASR_ONLY = "PIPELINE_DEGRADED_ASR_ONLY";
    static final String DEGRADED_VISUAL_ONLY = "PIPELINE_DEGRADED_VISUAL_ONLY";
    static final String DEGRADED_BACKGROUND = "PIPELINE_DEGRADED_BACKGROUND";

    public static AnalysisTaskWorkResult failure(String errorCode, String errorMessage) {
        return new AnalysisTaskWorkResult(false, errorCode, errorMessage);
    }

    static AnalysisTaskWorkResult degradedAsrOnly() {
        return new AnalysisTaskWorkResult(true, DEGRADED_ASR_ONLY, "Visual preprocessing unavailable; ASR pipeline completed");
    }

    static AnalysisTaskWorkResult degradedBackground() {
        return new AnalysisTaskWorkResult(true, DEGRADED_BACKGROUND, "Course learnable; a background stage failed and only its feature is unavailable");
    }

    static AnalysisTaskWorkResult degradedVisualOnly() {
        return new AnalysisTaskWorkResult(true, DEGRADED_VISUAL_ONLY, "ASR unavailable; visual pipeline completed without subtitles");
    }
}
