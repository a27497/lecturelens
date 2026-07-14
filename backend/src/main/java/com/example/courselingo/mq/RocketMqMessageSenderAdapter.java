package com.example.courselingo.mq;

import org.apache.rocketmq.client.apis.message.Message;
import org.apache.rocketmq.client.apis.message.MessageBuilder;
import org.apache.rocketmq.client.apis.producer.Producer;

class RocketMqMessageSenderAdapter implements RocketMqMessageSender {

    private final Producer producer;
    private final MessageBuilder messageBuilder;

    RocketMqMessageSenderAdapter(Producer producer, MessageBuilder messageBuilder) {
        this.producer = producer;
        this.messageBuilder = messageBuilder;
    }

    @Override
    public void send(String topic, String tag, String key, byte[] body) throws Exception {
        Message message = messageBuilder
            .setTopic(topic)
            .setTag(tag)
            .setKeys(key)
            .setBody(body)
            .build();
        producer.send(message);
    }
}
