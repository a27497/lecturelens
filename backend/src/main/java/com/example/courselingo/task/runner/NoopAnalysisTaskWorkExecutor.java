package com.example.courselingo.task.runner;

public class NoopAnalysisTaskWorkExecutor implements AnalysisTaskWorkExecutor {

    @Override
    public AnalysisTaskWorkResult execute(AnalysisTaskExecutionContext context) {
        return new AnalysisTaskWorkResult(false, "TASK_RUNNER_DISABLED", "Analysis pipeline is disabled");
    }
}
