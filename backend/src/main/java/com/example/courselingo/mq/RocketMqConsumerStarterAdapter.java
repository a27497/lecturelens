package com.example.courselingo.mq;

import org.apache.rocketmq.client.apis.consumer.PushConsumer;

class RocketMqConsumerStarterAdapter implements RocketMqConsumerStarter {

    private final PushConsumer pushConsumer;

    RocketMqConsumerStarterAdapter(PushConsumer pushConsumer) {
        this.pushConsumer = pushConsumer;
    }

    PushConsumer pushConsumer() {
        return pushConsumer;
    }
}
