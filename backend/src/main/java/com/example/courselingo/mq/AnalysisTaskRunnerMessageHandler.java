package com.example.courselingo.mq;

import com.example.courselingo.task.runner.AnalysisTaskRunner;
import org.springframework.stereotype.Component;

@Component
class AnalysisTaskRunnerMessageHandler implements AnalysisTaskMessageHandler {

    private final AnalysisTaskRunner runner;

    AnalysisTaskRunnerMessageHandler(AnalysisTaskRunner runner) {
        this.runner = runner;
    }

    @Override
    public void handle(AnalysisTaskMessageTag tag, AnalysisTaskMessage message) {
        switch (tag) {
            case ANALYSIS_CREATED -> runner.run(message);
            case ANALYSIS_RETRY -> runner.retry(message);
            case ANALYSIS_CANCEL -> runner.cancel(message);
        }
    }
}
