package com.example.courselingo.infrastructure;

import java.time.Duration;
import java.time.temporal.ChronoUnit;
import org.springframework.boot.context.properties.ConfigurationProperties;
import org.springframework.boot.convert.DurationUnit;

@ConfigurationProperties(prefix = "courselingo.redis")
public record RedisProperties(
    boolean enabled,
    String host,
    int port,
    String password,
    int database,
    @DurationUnit(ChronoUnit.MILLIS) Duration timeoutMs
) {

    public RedisProperties {
        if (host == null || host.isBlank()) {
            host = "localhost";
        }
        if (port <= 0) {
            port = 6379;
        }
        if (database < 0) {
            database = 0;
        }
        if (timeoutMs == null || timeoutMs.isNegative() || timeoutMs.isZero()) {
            timeoutMs = Duration.ofMillis(2000);
        }
    }
}
