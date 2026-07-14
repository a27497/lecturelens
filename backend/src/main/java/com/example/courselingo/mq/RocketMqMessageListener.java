package com.example.courselingo.mq;

import java.nio.ByteBuffer;
import java.util.Collection;
import org.apache.rocketmq.client.apis.consumer.ConsumeResult;
import org.apache.rocketmq.client.apis.consumer.MessageListener;
import org.apache.rocketmq.client.apis.message.MessageView;
import org.springframework.stereotype.Component;

@Component
class RocketMqMessageListener implements MessageListener {

    private final AnalysisTaskMessageConsumer consumer;

    RocketMqMessageListener(AnalysisTaskMessageConsumer consumer) {
        this.consumer = consumer;
    }

    @Override
    public ConsumeResult consume(MessageView messageView) {
        ConsumerProcessResult result = consumer.consume(new RocketMqInboundMessage(
            messageView.getTopic(),
            messageView.getTag().orElse(null),
            firstKey(messageView.getKeys()),
            bytes(messageView.getBody())
        ));
        if (result.status() == ConsumerProcessResult.Status.SUCCESS) {
            return ConsumeResult.SUCCESS;
        }
        return ConsumeResult.FAILURE;
    }

    private static String firstKey(Collection<String> keys) {
        if (keys == null || keys.isEmpty()) {
            return null;
        }
        return keys.iterator().next();
    }

    private static byte[] bytes(ByteBuffer body) {
        if (body == null) {
            return new byte[0];
        }
        ByteBuffer duplicate = body.asReadOnlyBuffer();
        byte[] result = new byte[duplicate.remaining()];
        duplicate.get(result);
        return result;
    }
}
