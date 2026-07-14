package com.example.courselingo.upload.service;

import java.time.Duration;
import org.springframework.boot.context.properties.ConfigurationProperties;

@ConfigurationProperties(prefix = "courselingo.upload.chunk-state")
public record UploadChunkStateProperties(
    long redisKeyTtlSeconds
) {

    public UploadChunkStateProperties {
        if (redisKeyTtlSeconds <= 0) {
            redisKeyTtlSeconds = 86400;
        }
    }

    public Duration redisKeyTtl() {
        return Duration.ofSeconds(redisKeyTtlSeconds);
    }
}
