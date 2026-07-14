package com.example.courselingo.task.runner;

import com.example.courselingo.mq.AnalysisTaskMessage;

public interface AnalysisTaskRunner {

    void run(AnalysisTaskMessage message);

    void retry(AnalysisTaskMessage message);

    void cancel(AnalysisTaskMessage message);
}
