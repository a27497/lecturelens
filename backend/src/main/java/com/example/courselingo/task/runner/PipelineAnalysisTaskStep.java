package com.example.courselingo.task.runner;

public interface PipelineAnalysisTaskStep {

    PipelineAnalysisTaskStepName name();

    void execute(PipelineAnalysisTaskStepContext context);
}
