package com.example.courselingo.task.events;

import com.example.courselingo.common.error.ErrorCode;
import com.example.courselingo.common.exception.BusinessException;
import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.task.events")
public record TaskEventStreamProperties(
    long sseTimeoutSeconds,
    long heartbeatIntervalSeconds,
    long pollIntervalMillis,
    int workerThreads
) {

    public TaskEventStreamProperties {
        if (sseTimeoutSeconds <= 0
            || heartbeatIntervalSeconds <= 0
            || pollIntervalMillis <= 0
            || workerThreads <= 0) {
            throw new BusinessException(ErrorCode.COMMON_VALIDATION_FAILED);
        }
    }

    public Duration sseTimeout() {
        return Duration.ofSeconds(sseTimeoutSeconds);
    }

    public Duration heartbeatInterval() {
        return Duration.ofSeconds(heartbeatIntervalSeconds);
    }

    public Duration pollInterval() {
        return Duration.ofMillis(pollIntervalMillis);
    }
}
