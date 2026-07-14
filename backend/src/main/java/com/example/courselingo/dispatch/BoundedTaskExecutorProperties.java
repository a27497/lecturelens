package com.example.courselingo.dispatch;

import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.dispatch.executor")
public record BoundedTaskExecutorProperties(
    int coreSize,
    int maxSize,
    int queueCapacity,
    long keepAliveSeconds,
    long taskTimeoutSeconds,
    long shutdownTimeoutSeconds
) {

    public BoundedTaskExecutorProperties() {
        this(2, 4, 32, 60, 14_400, 10);
    }
}
