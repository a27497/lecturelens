package com.example.courselingo.mq;

public record RocketMqInboundMessage(
    String topic,
    String tag,
    String key,
    byte[] body
) {
}
