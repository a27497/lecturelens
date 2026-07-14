package com.example.courselingo.task.claim;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.task.claim")
public record RedisTaskClaimProperties(
    long redisKeyTtlSeconds
) {

    public RedisTaskClaimProperties {
        if (redisKeyTtlSeconds <= 0) {
            redisKeyTtlSeconds = 900;
        }
    }

    public Duration redisKeyTtl() {
        return Duration.ofSeconds(redisKeyTtlSeconds);
    }
}
