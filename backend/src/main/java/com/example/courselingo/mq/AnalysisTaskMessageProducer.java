package com.example.courselingo.mq;

public interface AnalysisTaskMessageProducer {

    void send(AnalysisTaskMessageTag tag, AnalysisTaskMessage message);
}
