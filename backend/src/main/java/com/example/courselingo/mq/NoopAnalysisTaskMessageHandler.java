package com.example.courselingo.mq;

class NoopAnalysisTaskMessageHandler implements AnalysisTaskMessageHandler {

    @Override
    public void handle(AnalysisTaskMessageTag tag, AnalysisTaskMessage message) {
        // C4 only validates and dispatches messages. Real task execution is introduced in C5.
    }
}
