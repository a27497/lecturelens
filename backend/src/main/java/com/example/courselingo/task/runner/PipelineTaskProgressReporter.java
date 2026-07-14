package com.example.courselingo.task.runner;

public interface PipelineTaskProgressReporter {

    PipelineTaskProgressReporter NOOP = new PipelineTaskProgressReporter() {
    };

    default void stepStarted(PipelineAnalysisTaskStepName stepName, PipelineAnalysisTaskStepContext context) {
    }

    default void stepCompleted(
        PipelineAnalysisTaskStepName stepName,
        PipelineAnalysisTaskStepContext context,
        long durationMillis
    ) {
    }
}
