package com.example.courselingo.mq;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.mq.rocketmq")
public record RocketMqProducerProperties(
    String nameServer,
    String endpoint,
    String producerGroup,
    String analysisTopic,
    long sendTimeoutMs,
    boolean sslEnabled,
    boolean enabled
) {

    public void validate() {
        if (sendTimeoutMs <= 0) {
            throw new BusinessException(ErrorCode.MQ_CONFIGURATION_INVALID);
        }
        if (!enabled) {
            return;
        }
        if (isBlank(endpoint) || isBlank(producerGroup) || isBlank(analysisTopic)) {
            throw new BusinessException(ErrorCode.MQ_CONFIGURATION_INVALID);
        }
    }

    Duration sendTimeout() {
        return Duration.ofMillis(sendTimeoutMs);
    }

    private static boolean isBlank(String value) {
        return value == null || value.isBlank();
    }
}
