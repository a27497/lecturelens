package com.example.courselingo.mq;

public interface AnalysisTaskMessageConsumer {

    ConsumerProcessResult consume(RocketMqInboundMessage message);
}
