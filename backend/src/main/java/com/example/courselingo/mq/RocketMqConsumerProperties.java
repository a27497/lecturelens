package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.mq.rocketmq")
public record RocketMqConsumerProperties(
    String nameServer,
    String endpoint,
    String analysisTopic,
    String consumerGroup,
    long consumeTimeoutMs,
    boolean sslEnabled,
    boolean enabled
) {

    public void validate() {
        if (consumeTimeoutMs <= 0) {
            throw new BusinessException(ErrorCode.MQ_CONFIGURATION_INVALID);
        }
        if (!enabled) {
            return;
        }
        if (isBlank(endpoint) || isBlank(analysisTopic) || isBlank(consumerGroup)) {
            throw new BusinessException(ErrorCode.MQ_CONFIGURATION_INVALID);
        }
    }

    Duration consumeTimeout() {
        return Duration.ofMillis(consumeTimeoutMs);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
