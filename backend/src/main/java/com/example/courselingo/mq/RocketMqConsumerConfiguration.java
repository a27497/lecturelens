package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.util.Map;
import org.apache.rocketmq.client.apis.ClientConfiguration;
import org.apache.rocketmq.client.apis.ClientServiceProvider;
import org.apache.rocketmq.client.apis.consumer.FilterExpression;
import org.apache.rocketmq.client.apis.consumer.FilterExpressionType;
import org.apache.rocketmq.client.apis.consumer.PushConsumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.boot.context.properties.EnableConfigurationProperties;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

@Configuration
@EnableConfigurationProperties(RocketMqConsumerProperties.class)
public class RocketMqConsumerConfiguration {

    private static final Logger log = LoggerFactory.getLogger(RocketMqConsumerConfiguration.class);
    private static final String ANALYSIS_TAG_EXPRESSION =
        "ANALYSIS_CREATED||ANALYSIS_RETRY||ANALYSIS_CANCEL";

    @Bean
    RocketMqConsumerStarter rocketMqConsumerStarter(
        RocketMqConsumerProperties properties,
        RocketMqMessageListener listener
    ) {
        properties.validate();
        if (!properties.enabled()) {
            return new DisabledRocketMqConsumerStarter();
        }
        try {
            ClientServiceProvider provider = ClientServiceProvider.loadService();
            ClientConfiguration configuration = ClientConfiguration.newBuilder()
                .setEndpoints(properties.endpoint())
                .setRequestTimeout(properties.consumeTimeout())
                .enableSsl(properties.sslEnabled())
                .build();
            PushConsumer consumer = provider.newPushConsumerBuilder()
                .setClientConfiguration(configuration)
                .setConsumerGroup(properties.consumerGroup())
                .setSubscriptionExpressions(Map.of(
                    properties.analysisTopic(),
                    new FilterExpression(ANALYSIS_TAG_EXPRESSION, FilterExpressionType.TAG)
                ))
                .setMessageListener(listener)
                .build();
            return new RocketMqConsumerStarterAdapter(consumer);
        } catch (Exception exception) {
            log.error(
                "event=rocketmq_consumer_configuration_failed endpoint={} topic={} group={} outcome=failure errorCode={}",
                safeValue(properties.endpoint()),
                safeValue(properties.analysisTopic()),
                safeValue(properties.consumerGroup()),
                ErrorCode.MQ_CONFIGURATION_INVALID.code(),
                exception
            );
            throw new BusinessException(
                ErrorCode.MQ_CONFIGURATION_INVALID,
                "RocketMQ consumer configuration is invalid: endpoint="
                    + safeValue(properties.endpoint())
                    + ", topic="
                    + safeValue(properties.analysisTopic())
                    + ", group="
                    + safeValue(properties.consumerGroup()),
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
