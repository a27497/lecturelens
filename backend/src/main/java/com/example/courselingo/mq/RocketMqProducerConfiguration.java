package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import org.apache.rocketmq.client.apis.ClientConfiguration;
import org.apache.rocketmq.client.apis.ClientServiceProvider;
import org.apache.rocketmq.client.apis.message.MessageBuilder;
import org.apache.rocketmq.client.apis.producer.Producer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(RocketMqProducerProperties.class)
public class RocketMqProducerConfiguration {

    private static final Logger log = LoggerFactory.getLogger(RocketMqProducerConfiguration.class);

    @Bean
    RocketMqMessageSender rocketMqMessageSender(RocketMqProducerProperties properties) throws Exception {
        properties.validate();
        if (!properties.enabled()) {
            return new DisabledRocketMqMessageSender();
        }
        try {
            ClientServiceProvider provider = ClientServiceProvider.loadService();
            ClientConfiguration configuration = ClientConfiguration.newBuilder()
                .setEndpoints(properties.endpoint())
                .setRequestTimeout(properties.sendTimeout())
                .enableSsl(properties.sslEnabled())
                .build();
            Producer producer = provider.newProducerBuilder()
                .setClientConfiguration(configuration)
                .setTopics(properties.analysisTopic())
                .build();
            MessageBuilder messageBuilder = provider.newMessageBuilder();
            return new RocketMqMessageSenderAdapter(producer, messageBuilder);
        } catch (Exception exception) {
            log.error(
                "event=rocketmq_producer_configuration_failed endpoint={} topic={} group={} outcome=failure errorCode={}",
                safeValue(properties.endpoint()),
                safeValue(properties.analysisTopic()),
                safeValue(properties.producerGroup()),
                ErrorCode.MQ_CONFIGURATION_INVALID.code(),
                exception
            );
            throw new BusinessException(
                ErrorCode.MQ_CONFIGURATION_INVALID,
                "RocketMQ producer configuration is invalid: endpoint="
                    + safeValue(properties.endpoint())
                    + ", topic="
                    + safeValue(properties.analysisTopic())
                    + ", group="
                    + safeValue(properties.producerGroup()),
                exception
            );
        }
    }

    private static String safeValue(String value) {
        if (value == null || value.isBlank()) {
            return "<blank>";
        }
        return value.replaceAll("[\\r\\n\\t]", "_");
    }
}
