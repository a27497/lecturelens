package com.example.courselingo.task.progress;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.task.progress")
public record TaskProgressProperties(
    long redisKeyTtlSeconds
) {

    public TaskProgressProperties {
        if (redisKeyTtlSeconds <= 0) {
            redisKeyTtlSeconds = 86400;
        }
    }

    public Duration redisKeyTtl() {
        return Duration.ofSeconds(redisKeyTtlSeconds);
    }
}
