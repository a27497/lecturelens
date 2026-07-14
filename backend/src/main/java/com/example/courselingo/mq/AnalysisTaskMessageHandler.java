package com.example.courselingo.mq;

public interface AnalysisTaskMessageHandler {

    void handle(AnalysisTaskMessageTag tag, AnalysisTaskMessage message);
}
