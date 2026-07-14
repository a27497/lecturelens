package com.example.courselingo.task.runner;

final class NoopPipelineAnalysisTaskStep implements PipelineAnalysisTaskStep {

    private final PipelineAnalysisTaskStepName name;

    NoopPipelineAnalysisTaskStep(PipelineAnalysisTaskStepName name) {
        this.name = name;
    }

    @Override
    public PipelineAnalysisTaskStepName name() {
        return name;
    }

    @Override
    public void execute(PipelineAnalysisTaskStepContext context) {
        // Intentionally empty: F1 only establishes the executable step boundary.
    }
}
