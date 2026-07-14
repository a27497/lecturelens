package com.example.courselingo.task.runner;

import com.example.courselingo.common.logging.SafeLogSanitizer;

public class PipelineAnalysisTaskStepException extends RuntimeException {

    private final PipelineAnalysisTaskStepName stepName;

    public PipelineAnalysisTaskStepException(PipelineAnalysisTaskStepName stepName, Throwable cause) {
        super(message(stepName, cause), cause);
        this.stepName = stepName;
    }

    public PipelineAnalysisTaskStepName stepName() {
        return stepName;
    }

    private static String message(PipelineAnalysisTaskStepName stepName, Throwable cause) {
        String detail = cause == null ? null : cause.getMessage();
        if (detail == null || detail.isBlank()) {
            detail = cause == null ? "unknown error" : cause.getClass().getSimpleName();
        }
        return "Pipeline step " + stepName + " failed: "
            + SafeLogSanitizer.sanitizeAndLimit(detail, 512);
    }
}
